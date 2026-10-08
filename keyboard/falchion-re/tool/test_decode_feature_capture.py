#!/usr/bin/env python3
"""Tests for the feature-capture decodes quoted in logs 135-137.

The fixtures are the preserved evidence itself: Macro03.GMAC and a raw AC
profile copy from snapshots/, and the 54 upload bytes exactly as log 135 s6.3
quotes them from captures/03b-features.pcap. No capture is parsed here, so the
suite needs no tshark; the CLI's tshark paths were run against the real
captures when the module was added (see FINDINGS.md, logs 135-137).

No device access. Every fixture file is opened read-only and its sha256 is
asserted against the value recorded in the logs or its SHA256SUMS.txt.
"""
import hashlib
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decode_feature_capture as dfc

ROOT = Path(__file__).resolve().parent.parent
MACRO03 = ROOT / "snapshots/03b-features-macros/Macro03.GMAC"
MACRO03_SHA = "6b0c11cf4c15f44347a3b580848428522062ae1f39ee8b91c9e7f753d33bea88"
PROFILE = ROOT / "snapshots/03b-features-before-raw/fp_1_config_024080600167.xml"
PROFILE_SUMS = ROOT / "snapshots/03b-features-before-raw/SHA256SUMS.txt"

# 03b 05:02:00.253, Macro03 -> Z, as quoted in log 135 s6.1/s6.3.
UPLOAD_03B = ("54000d002e00000000"
              "1f027700" "1f01a801" "20026300" "20011e02" "21024100" "21017d0b"
              "1f026a00" "1f018001" "32026a00" "3201b201" "30026100" "30010000"
              "ff").ljust(128, "0")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frame(payload_hex, epoch=0.0):
    return {"direction": "OUT", "payload": payload_hex.ljust(128, "0"), "epoch": epoch}


class EvidenceUnchanged(unittest.TestCase):
    def test_macro03_matches_log_135(self):
        self.assertEqual(sha256(MACRO03), MACRO03_SHA)

    def test_profile_matches_its_manifest(self):
        want = next(line.split()[0] for line in PROFILE_SUMS.read_text(encoding="utf-8-sig").splitlines()
                    if line.rstrip().endswith("fp_1_config_024080600167.xml"))
        self.assertEqual(sha256(PROFILE), want)


class MacroUpload(unittest.TestCase):
    def test_log_135_upload_matches_its_gmac_record_by_record(self):
        records, assigned = dfc.upload_records([frame(UPLOAD_03B)])
        events = dfc.parse_gmac(MACRO03.read_text(encoding="utf-8"))
        rows, ok = dfc.compare_macro(records, events)
        self.assertTrue(ok)
        self.assertEqual(assigned, 46)                       # Z
        self.assertEqual(len(records), 12)                   # 13 in byte 2, minus ff
        self.assertEqual([r[2] for r in records],
                         [119, 424, 99, 542, 65, 2941, 106, 384, 106, 434, 97, 0])
        self.assertEqual([dfc.key_name(r[0]) for r in records if r[1] == dfc.PRESS],
                         ["A", "S", "D", "A", "B", "C"])

    def test_one_changed_delay_is_reported(self):
        records, _ = dfc.upload_records([frame(UPLOAD_03B)])
        records[1] = (records[1][0], records[1][1], records[1][2] + 1)
        rows, ok = dfc.compare_macro(records, dfc.parse_gmac(MACRO03.read_text(encoding="utf-8")))
        self.assertFalse(ok)
        self.assertEqual([r[6] for r in rows].count(False), 1)

    def test_press_release_swap_is_reported(self):
        records, _ = dfc.upload_records([frame(UPLOAD_03B)])
        records[0] = (records[0][0], dfc.RELEASE, records[0][2])
        _, ok = dfc.compare_macro(records, dfc.parse_gmac(MACRO03.read_text(encoding="utf-8")))
        self.assertFalse(ok)

    def test_changed_key_cannot_match_even_with_identical_timing(self):
        records, _ = dfc.upload_records([frame(UPLOAD_03B)])
        events = dfc.parse_gmac(MACRO03.read_text(encoding="utf-8"))
        for key in (32, 200):
            changed = [(key, records[0][1], records[0][2]), *records[1:]]
            rows, ok = dfc.compare_macro(changed, events)
            self.assertFalse(ok)
            self.assertIsNot(rows[0][6], True)

    def test_missing_or_extra_events_cannot_match(self):
        records, _ = dfc.upload_records([frame(UPLOAD_03B)])
        events = dfc.parse_gmac(MACRO03.read_text(encoding="utf-8"))
        for changed in (records[:-1], records + records[:1]):
            self.assertFalse(dfc.compare_macro(changed, events)[1])

    def test_observed_macro_aliases(self):
        records = [(42, 2, 64), (108, 2, 84), (53, 2, 89)]
        events = [("Press", "\\", 64), ("Press", "Enter", 84), ("Press", "Comma", 89)]
        self.assertTrue(dfc.compare_macro(records, events)[1])
        self.assertFalse(dfc.compare_macro([(43, 2, 84)], events[1:2])[1])

    def test_only_observed_mouse_encoding_is_supported(self):
        event = [("Press", "Left Click", None)]
        self.assertTrue(dfc.compare_macro([(0xf0, 0x12, 0)], event)[1])
        for record, events in [((0xf0, 0x11, 0), [("Release", "Left Click", None)]),
                               ((0xf1, 0x12, 0), event),
                               ((31, 2, 0), [("Press", "Scroll Down", None)])]:
            rows, ok = dfc.compare_macro([record], events)
            self.assertFalse(ok)
            self.assertIsNone(rows[0][6])

    def test_known_keyboard_and_mouse_events_differ_without_being_unsupported(self):
        rows, ok = dfc.compare_macro([(31, 2, 0)], [("Press", "Left Click", None)])
        self.assertFalse(ok)
        self.assertIs(rows[0][6], False)

    def test_continuation_frames_join_one_upload(self):
        # log 136 s3.4: byte 3 = 00 starts an upload, 01 continues it;
        # byte 2 counts THIS frame's records, terminator included.
        first = "54000200" + "4b00000000" + "11020a00" + "11010b00"
        cont = "54000201" + "4b00000000" + "12020c00" + "ff"
        again = "54000200" + "1000000000" + "1f020100" + "ff"
        uploads = dfc.split_uploads([frame(first), frame(cont), frame(again)])
        self.assertEqual([len(u) for u in uploads], [2, 1])
        records, assigned = dfc.upload_records(uploads[0])
        self.assertEqual(assigned, 75)                       # Ins
        self.assertEqual(records, [(17, 2, 10), (17, 1, 11), (18, 2, 12)])

    def test_byte_2_bounds_the_records_read(self):
        # Padding after the counted records must not be read as more events.
        payload = "54000200" + "2e00000000" + "1f020100" + "ff" + "20020200"
        records, _ = dfc.upload_records([frame(payload)])
        self.assertEqual(records, [(31, 2, 1)])


class Lever(unittest.TestCase):
    def test_on_off_and_other_reports(self):
        self.assertEqual(dfc.lever_state("0376000001" + "00" * 16), 1)
        self.assertEqual(dfc.lever_state("0376000000" + "00" * 16), 0)
        self.assertIsNone(dfc.lever_state("0371000000" + "00" * 16))   # key bitmap
        self.assertIsNone(dfc.lever_state("0376"))


class RequestReplies(unittest.TestCase):
    @staticmethod
    def report(direction, payload, **scope):
        return {"direction": direction, "payload": payload, **scope}

    def test_capture_03_wrong_command_reply_is_not_reused(self):
        # Header sequence at frames 102363..105536 of capture 03.
        reports = [self.report("OUT", "510000000300") for _ in range(3)]
        reports += [self.report("OUT", "121402000000"), self.report("IN", "121402003032")]
        results = dfc.request_reply_results(reports)
        self.assertEqual([r[2] for r in results], ["unanswered"] * 3 + ["matched"])
        self.assertEqual(sum(r[1] is not None for r in results), 1)

    def test_retries_are_ambiguous(self):
        # Capture 03 frames 107185, 108173, 108212.
        reports = [self.report("OUT", "510000000100"),
                   self.report("OUT", "510000000100"),
                   self.report("IN", "510000000100")]
        self.assertEqual([r[2] for r in dfc.request_reply_results(reports)],
                         ["ambiguous", "ambiguous"])
        self.assertTrue(all(reply is None for _, reply in dfc.request_reply_pairs(reports)))

    def test_unique_profile_echo_retires_other_pending_profiles(self):
        reports = [self.report("OUT", "510000000300") for _ in range(3)]
        reports += [self.report("OUT", "510000000200"),
                    self.report("IN", "510000000200"),
                    self.report("OUT", "510000000100"),
                    self.report("IN", "510000000200")]
        results = dfc.request_reply_results(reports)
        self.assertEqual([r[2] for r in results], ["unanswered"] * 3 + ["matched"] * 2)
        self.assertIs(results[3][1], reports[4])
        self.assertIs(results[4][1], reports[6])
        self.assertEqual(dfc.reply_warning(results[4][0], results[4][1]),
                         "profile differs: requested 01, reply 02")

    def test_same_profile_echoes_remain_ambiguous(self):
        reports = [self.report("OUT", "510000000300"),
                   self.report("OUT", "510000000200"),
                   self.report("OUT", "510000000200"),
                   self.report("IN", "510000000200")]
        self.assertEqual([r[2] for r in dfc.request_reply_results(reports)],
                         ["unanswered", "ambiguous", "ambiguous"])

    def test_no_profile_echo_keeps_competing_requests_ambiguous(self):
        reports = [self.report("OUT", "510000000100"),
                   self.report("OUT", "510000000300"),
                   self.report("IN", "510000000200")]
        self.assertEqual([r[2] for r in dfc.request_reply_results(reports)],
                         ["ambiguous", "ambiguous"])

    def test_profile_warning_compares_raw_bytes(self):
        request = self.report("OUT", "510000000100")
        self.assertIsNone(dfc.reply_warning(request, self.report("IN", "510000000100")))
        self.assertEqual(dfc.reply_warning(request, self.report("IN", "510000000200")),
                         "profile differs: requested 01, reply 02")
        # Raw 00 and 06 may represent the same internal profile, but the
        # decoder reports the bytes without silently normalizing them.
        self.assertEqual(dfc.reply_warning(self.report("OUT", "510000000000"),
                                           self.report("IN", "510000000600")),
                         "profile differs: requested 00, reply 06")

    def test_short_profile_reports_do_not_supply_an_echo(self):
        reports = [self.report("OUT", "510000000100"),
                   self.report("OUT", "510000000200"), self.report("IN", "5100")]
        self.assertEqual([r[2] for r in dfc.request_reply_results(reports)],
                         ["ambiguous", "ambiguous"])
        self.assertIsNone(dfc.reply_warning(reports[0], reports[2]))

    def test_other_commands_do_not_use_profile_byte(self):
        reports = [self.report("OUT", "515000000100"),
                   self.report("OUT", "515000000200"),
                   self.report("IN", "515000000200")]
        self.assertEqual([r[2] for r in dfc.request_reply_results(reports)],
                         ["ambiguous", "ambiguous"])
        self.assertIsNone(dfc.reply_warning(reports[0], reports[2]))

    def test_pairs_cli_prints_profile_warning(self):
        reports = [self.report("OUT", "510000000100", epoch=0),
                   self.report("IN", "510000000200", epoch=0)]
        output = StringIO()
        with patch.object(dfc.dc, "reports", return_value=reports), redirect_stdout(output):
            self.assertEqual(dfc.cmd_pairs(SimpleNamespace(capture="unused", op=None,
                                                           utc_offset=-6)), 0)
        self.assertIn("[WARNING: profile differs: requested 01, reply 02]", output.getvalue())

    def test_reply_must_belong_to_same_device_scope(self):
        for field in ("interface", "bus", "address"):
            reports = [self.report("OUT", "5150", **{field: 1}),
                       self.report("IN", "5150", **{field: 2}),
                       self.report("IN", "5150", **{field: 1})]
            self.assertIs(dfc.request_reply_results(reports)[0][1], reports[2])

    def test_query_success_branch_and_competing_modes(self):
        reports = [self.report("OUT", "1212"), self.report("IN", "1213")]
        self.assertEqual(dfc.request_reply_results(reports)[0][2], "matched")
        reports.insert(1, self.report("OUT", "1213"))
        self.assertEqual([r[2] for r in dfc.request_reply_results(reports)],
                         ["ambiguous", "ambiguous"])

    def test_unrelated_commands_can_be_interleaved(self):
        reports = [self.report("OUT", "5150"), self.report("OUT", "1214"),
                   self.report("IN", "1214"), self.report("IN", "5150")]
        results = dfc.request_reply_results(reports)
        self.assertIs(results[0][1], reports[3])
        self.assertIs(results[1][1], reports[2])


class Profiles(unittest.TestCase):
    def test_decode_of_the_preserved_profile(self):
        config = dfc.decode_profile_xml(PROFILE.read_text(encoding="utf-8"))
        trigger = config["button"]["analogTrigger"]
        # log 135 s4: the 03b "before" state
        self.assertEqual(trigger["actuation"], 28)
        self.assertEqual(trigger["preKeyRapidTriggerList"],
                         ["1793", "1794", "769", "1538", "1795", "1024"])

    def test_identical_copies_have_no_changes(self):
        folder = PROFILE.parent
        self.assertTrue(all(not c for c in dfc.profile_changes(folder, folder).values()))


class KeyNames(unittest.TestCase):
    def test_at101_positions_from_log_137(self):
        for number, name in [(15, "Backspace"), (31, "A"), (61, "Space"), (75, "Ins"),
                             (89, "Right"), (110, "Esc")]:
            self.assertEqual(dfc.key_name(number), name)
        self.assertEqual(dfc.key_name(200), "?200")


if __name__ == "__main__":
    unittest.main()
