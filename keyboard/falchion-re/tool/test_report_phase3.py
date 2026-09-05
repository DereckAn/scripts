#!/usr/bin/env python3
"""Offline tests for the Phase 3 report generator.

Guards the two things that matter about a generated, committed artifact: that a
fresh render is byte-identical to what is on disk, and that the complete mapping
really is complete. No device access, no writes.
"""
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match_functions as mf
import report_phase3 as rp

INVENTORIES = Path(rp.INVENTORIES)


@unittest.skipUnless((INVENTORIES / "vendor_a.txt").exists(),
                     "run the Ghidra inventory step first")
class Artifacts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rendered = rp.render()

    def test_every_declared_artifact_is_rendered(self):
        self.assertEqual(sorted(self.rendered), sorted(rp.ARTIFACTS))

    def test_render_is_deterministic(self):
        self.assertEqual(self.rendered, rp.render())

    def test_the_artifacts_on_disk_are_current(self):
        stale = [name for name, text in self.rendered.items()
                 if not (rp.NOTES / name).exists()
                 or (rp.NOTES / name).read_text() != text]
        self.assertEqual(stale, [],
                         "run python3 tool/report_phase3.py to refresh these")

    def test_the_markdown_carries_every_pairing(self):
        text = self.rendered["vendor-to-installed-functions.md"]
        for tag in ("a", "b"):
            payload = json.loads(
                self.rendered[f"vendor-to-installed-functions-app-{tag}.json"])
            rows = len(payload["matches"])
            self.assertIn(f"{rows} pairings", text)
            for match in payload["matches"]:
                anchor = match["vendor"] or match["installed"]
                self.assertIn(f"`0x{anchor['entry']:08x}`", text)

    def test_the_json_records_real_body_ranges(self):
        payload = json.loads(
            self.rendered["vendor-to-installed-functions-app-b.json"])
        self.assertGreater(payload["discontiguous_bodies"]["vendor"], 0)
        # Equal counts are reported as equal counts, never as alignment.
        self.assertTrue(payload["uncovered_span_counts_equal"])
        self.assertFalse(payload["uncovered_spans_fully_compared"],
                         "Candidate B has spans that could not be paired, so "
                         "it must not report as fully compared")
        self.assertNotIn("uncovered_spans_aligned", payload)

    def test_the_load_map_json_covers_every_active_record(self):
        payload = json.loads(self.rendered["installed-record-load-map.json"])
        self.assertTrue(payload["ok"])
        spans = [(item["source_lo"], item["source_hi"])
                 for item in payload["slices"]]
        self.assertIn((0x21000, 0x3F780), spans)
        self.assertIn((0x11000, 0x168AC), spans)

    def test_check_mode_reports_current(self):
        buffer = io.StringIO()
        stdout, sys.stdout = sys.stdout, buffer
        try:
            code = rp.main(["--check"])
        finally:
            sys.stdout = stdout
        self.assertEqual(code, 0)
        self.assertIn("RESULT reports_current=True", buffer.getvalue())
        self.assertNotIn("STALE", buffer.getvalue())

    def test_totals_match_the_matcher(self):
        _extraction, reports = rp.load_reports()
        body, data, total = rp.totals(reports["a"])
        # The invariant is the total: it must equal log 96's raw count for
        # Candidate A, which did not move. How it splits between bodies and data
        # shifts every time the analysed function set grows, so the split is
        # reported rather than pinned.
        self.assertEqual(total, 131,
                         "Candidate A's aligned total must equal log 96's raw "
                         "131 differing bytes")
        self.assertEqual(body + data, total)
        body, data, total = rp.totals(reports["b"])
        self.assertGreater(body, 0)
        self.assertGreater(data, 0)
        self.assertLess(total, 5000,
                        "far below log 96's 101,112 raw differing bytes")
        self.assertEqual(mf.tally(reports["a"]).get("unmatched", 0), 0)
        self.assertEqual(mf.tally(reports["b"]).get("unmatched", 0), 0)

    def test_the_markdown_corrects_the_single_insertion_claim(self):
        text = self.rendered["vendor-to-installed-functions.md"]
        self.assertIn("distributed, not a single insertion", text)
        self.assertIn("corrects logs 98 and 99", text)
        self.assertIn("lower bound", text)


if __name__ == "__main__":
    unittest.main()
