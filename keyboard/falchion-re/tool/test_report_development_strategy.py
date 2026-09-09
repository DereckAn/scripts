#!/usr/bin/env python3
"""Offline tests for the Phase 6 development-strategy ADR.

Two jobs. First, keep the ADR a DECISION RECORD: it must contain no device
command framing, and the test for that has to be able to fail, so a companion
test feeds it known-bad text. Second, pin the load-bearing claims — that every
cited log exists and still hashes to what SHA256SUMS records, and that the
decision and its blockers are not quietly softened later. No device access, no
writes outside a temporary directory.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report_development_strategy as ds

READY = (ds.LOGS / "SHA256SUMS").exists()


class NoRunbook(unittest.TestCase):
    """The ADR must never become something a reader can follow."""

    @unittest.skipUnless(READY, "logs not present")
    def test_the_adr_contains_no_device_command_framing(self):
        hits = ds.command_framing_hits(ds.markdown())
        self.assertEqual(hits, (), f"the ADR matched {hits}")

    def test_the_detector_actually_detects(self):
        """A detector that never fires would make the test above vacuous."""
        for bad in ("$ python3 tool/backup_firmware.py --run",
                    "open /dev/hidraw6 and write the report",
                    "then flash the image with dfu-util",
                    "run the following to program the device",
                    "sudo chmod 666 the node",
                    "d.write(report)"):
            self.assertNotEqual(ds.command_framing_hits(bad), (), bad)

    def test_ordinary_flash_layout_prose_is_not_flagged(self):
        """The document is about flash layout; the ban is on instructions,
        not on the word."""
        for fine in ("the application region of flash is writable over the "
                     "vendor channel",
                     "a patch must fit inside an existing flash record",
                     "the flash offset 0x7bffc holds the word-sum"):
            self.assertEqual(ds.command_framing_hits(fine), (), fine)

    @unittest.skipUnless(READY, "logs not present")
    def test_the_adr_says_it_authorises_nothing(self):
        text = ds.markdown()
        self.assertIn("Nothing here authorises touching the device", text)
        self.assertIn("does not authorise", text.replace(
            "Nothing in this decision authorises", "does not authorise"))

    @unittest.skipUnless(READY, "logs not present")
    def test_no_json_field_carries_a_command(self):
        self.assertEqual(
            ds.command_framing_hits(json.dumps(ds.to_dict())), ())


@unittest.skipUnless(READY, "logs not present")
class Citations(unittest.TestCase):

    def test_every_cited_log_exists(self):
        for name in ds.CITED_LOGS:
            self.assertTrue((ds.LOGS / name).exists(), name)

    def test_every_cited_log_matches_its_recorded_hash(self):
        recorded = ds.recorded_digests()
        for name, digest in ds.cited_log_digests().items():
            self.assertIn(name, recorded, name)
            self.assertEqual(recorded[name], digest, name)

    def test_a_missing_cited_log_fails_closed(self):
        original = ds.LOGS
        with tempfile.TemporaryDirectory() as directory:
            ds.LOGS = Path(directory)
            try:
                with self.assertRaises(ds.StrategyError):
                    ds.cited_log_digests()
            finally:
                ds.LOGS = original

    def test_the_citations_span_the_phases_the_adr_reasons_about(self):
        """An ADR that cited only one phase would not be reasoning from the
        evidence it claims to."""
        names = " ".join(ds.CITED_LOGS)
        for marker in ("101-", "105-", "107-", "109-", "110-", "111-",
                       "112-", "113-", "114-"):
            self.assertIn(marker, names, marker)


class Decision(unittest.TestCase):

    @unittest.skipUnless(READY, "logs not present")
    def test_the_decision_is_path_a_first_and_decided(self):
        payload = ds.to_dict()
        self.assertEqual(payload["decision"], "path-a-first")
        self.assertEqual(payload["status"], "decided")

    @unittest.skipUnless(READY, "logs not present")
    def test_path_b_is_recorded_as_unable_to_type(self):
        """The single most important claim in the document."""
        verdict = ds.to_dict()["path_b"]["blocking_verdict"]
        self.assertIn("CANNOT produce a typing keyboard", verdict)
        self.assertIn("released forever", verdict)

    @unittest.skipUnless(READY, "logs not present")
    def test_path_a_admits_it_is_not_our_own_firmware(self):
        text = ds.to_dict()["path_a"]["vendor_derived_code"]
        self.assertIn("Nearly all of it", text)
        self.assertIn("does not produce our own firmware", text)

    @unittest.skipUnless(READY, "logs not present")
    def test_the_default_is_confirmed_not_merely_inherited(self):
        text = ds.markdown()
        self.assertIn("confirmed", text)
        self.assertIn("could have overturned it and did", text)


class Targets(unittest.TestCase):

    def test_every_target_has_a_verdict_from_the_closed_set(self):
        for target in ds.CANDIDATE_TARGETS:
            self.assertIn(target.verdict, ("passes", "fails"), target.key)

    def test_every_failing_target_names_phase8_criteria_only(self):
        for target in ds.CANDIDATE_TARGETS:
            if target.verdict != "fails":
                continue
            self.assertTrue(target.failing_criteria, target.key)
            for criterion in target.failing_criteria:
                self.assertIn(criterion, ds.PHASE8_CRITERIA, target.key)

    def test_a_passing_target_names_no_failing_criteria(self):
        for target in ds.CANDIDATE_TARGETS:
            if target.verdict == "passes":
                self.assertEqual(target.failing_criteria, (), target.key)

    def test_the_vid_pid_target_fails_on_recovery(self):
        """The one that looks safe and is not."""
        target, = [t for t in ds.CANDIDATE_TARGETS if t.key == "usb_vid_pid"]
        self.assertEqual(target.verdict, "fails")
        self.assertIn("recovery effect", " ".join(target.failing_criteria))
        self.assertIn("NOT ESTABLISHED", target.reasoning)

    def test_the_actuation_threshold_fails_on_understanding(self):
        target, = [t for t in ds.CANDIDATE_TARGETS
                   if t.key == "actuation_threshold"]
        self.assertEqual(target.verdict, "fails")
        self.assertIn("fully understood control/data path",
                      " ".join(target.failing_criteria))

    def test_the_bootloader_target_is_excluded_absolutely(self):
        target, = [t for t in ds.CANDIDATE_TARGETS
                   if t.key == "bootloader_region"]
        self.assertEqual(target.verdict, "fails")
        self.assertGreaterEqual(len(target.failing_criteria), 2)

    def test_every_target_cites_a_log(self):
        for target in ds.CANDIDATE_TARGETS:
            self.assertTrue(target.evidence, target.key)


class Gates(unittest.TestCase):

    def test_the_hall_gate_is_named_largest(self):
        gate, = [g for g in ds.PATH_B_GATES if g.key == "hall_acquisition"]
        self.assertIn("LARGEST GATE", gate.what_would_satisfy_it)

    def test_every_gate_states_what_would_satisfy_it(self):
        for gate in ds.PATH_B_GATES:
            self.assertGreater(len(gate.what_would_satisfy_it), 80, gate.key)
            self.assertTrue(gate.evidence, gate.key)

    def test_the_gates_cover_the_three_unresolved_services(self):
        keys = {gate.key for gate in ds.PATH_B_GATES}
        for expected in ("hall_acquisition", "clock_frequency"):
            self.assertIn(expected, keys)


@unittest.skipUnless(READY, "logs not present")
class Artifacts(unittest.TestCase):

    def test_every_check_passes(self):
        for item in ds.verify():
            self.assertTrue(item["ok"], item["name"])

    def test_json_is_deterministic(self):
        self.assertEqual(ds.bodies(), ds.bodies())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in ds.bodies().items()
                 if not (ds.NOTES / name).exists()
                 or (ds.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/report_development_strategy.py "
                         "--write")

    def test_the_adr_declares_itself_generated(self):
        self.assertIn("Do not edit by hand", ds.markdown())


if __name__ == "__main__":
    unittest.main()
