#!/usr/bin/env python3
"""Offline regressions against the preserved Windows evidence; no device access."""
from collections import Counter
import hashlib
from pathlib import Path
import re
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import decode_feature_capture as dfc
import map_vendor_commands as commands

ROOT = Path(__file__).resolve().parent.parent


class EvidenceBytes(unittest.TestCase):
    def test_all_feature_snapshot_files_match_original_manifests(self):
        checked = 0
        for manifest in ROOT.glob("snapshots/03*/**/SHA256SUMS.txt"):
            for line in manifest.read_text(encoding="utf-8-sig").splitlines():
                expected, size, date, time, name = line.split(None, 4)
                path = manifest.parent / name.replace("\\", "/")
                with self.subTest(path=str(path.relative_to(ROOT))):
                    data = path.read_bytes()
                    self.assertEqual(len(data), int(size))
                    self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
                checked += 1
        self.assertEqual(checked, 68)

    def test_evidence_paths_quoted_in_feature_logs_keep_their_hashes(self):
        checked = 0
        for path in ROOT.glob("logs/13[567]-*.txt"):
            for expected, name in re.findall(
                    r"^\s*([0-9a-f]{64})\s+((?:captures|snapshots)/\S+)",
                    path.read_text(), re.M):
                with self.subTest(log=path.name, evidence=name):
                    self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), expected)
                checked += 1
        self.assertGreaterEqual(checked, 15)


@unittest.skipUnless(shutil.which("tshark"), "tshark is needed for capture regressions")
class FeatureCaptures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = {name: dfc.dc.reports(ROOT / "captures" / f"{name}.pcap")
                       for name, _, _ in commands.FEATURE_CAPTURES}

    def test_reply_pairing_in_all_four_captures(self):
        for name, records in self.records.items():
            with self.subTest(capture=name):
                results = dfc.request_reply_results(records)
                self.assertEqual(len(results), sum(r["direction"] == "OUT" for r in records))
                replies = [reply for _, reply, _ in results if reply]
                self.assertEqual(len(replies), len({r["frame"] for r in replies}))
                for request, reply, _ in results:
                    if reply:
                        self.assertEqual(request["opcode"], reply["opcode"])
                if name != "03-features":
                    self.assertTrue(all(status == "matched" for _, _, status in results))
        results = {r["frame"]: (reply, status)
                   for r, reply, status in dfc.request_reply_results(self.records["03-features"])}
        # Profile 02's unique echo resolves frame 106057, leaving the three
        # earlier profile 03 requests unanswered. Identical 01 retries remain
        # ambiguous. No elapsed-time cutoff is used.
        for number in (102363, 103199, 104069):
            self.assertEqual(results[number], (None, "unanswered"))
        for number in (107185, 108173):
            self.assertEqual(results[number], (None, "ambiguous"))
        self.assertEqual(results[106057][0]["frame"], 106067)
        self.assertEqual(results[106237][0]["frame"], 106277)
        request = next(r for r in self.records["03-features"] if r["frame"] == 106237)
        self.assertEqual(dfc.reply_warning(request, results[106237][0]),
                         "profile differs: requested 01, reply 02")
        self.assertEqual(Counter(status for _, status in results.values()),
                         {"matched": 232, "unanswered": 3, "ambiguous": 2})
        self.assertEqual(results[105533][0]["frame"], 105536)

    def test_preserved_macros_match_keys_actions_and_delays(self):
        cases = [
            ("03b-features", 0, "03b-features-macros/Macro03.GMAC"),
            ("03b-features", 1, "03b-features-macros/Macro04.GMAC"),
            ("03c-deep", 0, "03c-deep-after-raw/macros/Macro04.GMAC"),
            ("03c-deep", 1, "03c-deep-after-raw/macros/ROWS.GMAC"),
            ("03d-finish", 0, "03d-finish-after-raw/macros/KEYS2.GMAC"),
        ]
        for name, index, macro in cases:
            with self.subTest(capture=name, macro=macro):
                uploads = dfc.split_uploads(dfc.macro_frames(self.records[name]))
                records, assigned = dfc.upload_records(uploads[index])
                events = dfc.parse_gmac((ROOT / "snapshots" / macro).read_text())
                rows, ok = dfc.compare_macro(records, events)
                self.assertTrue(ok, rows)

    def test_two_actuation_writes_share_one_commit(self):
        # 03d 06:21:33, selecting P and L together (log 137 section 1).
        records = [r for r in self.records["03d-finish"] if r["direction"] == "OUT"
                   and 250438 <= r["frame"] <= 250511]
        self.assertEqual([r["opcode"] for r in records], ["514f", "514f", "5055"])

    def test_feature_opcodes_are_observed_in_their_captures(self):
        observed = Counter(r["opcode"] for records in self.records.values()
                           for r in records if r["direction"] == "OUT")
        for command in commands.FEATURE_WIRE:
            prefix = command.replace(" ", "")
            self.assertTrue(any(op.startswith(prefix) for op in observed), command)
        self.assertNotIn("5159", observed)


if __name__ == "__main__":
    unittest.main()
