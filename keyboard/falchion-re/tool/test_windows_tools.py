#!/usr/bin/env python3
"""Offline tests for the Windows capture and trace guard rules.

The rules run here; the PowerShell scripts are checked structurally, because
PowerShell cannot be executed in this environment. What is *not* covered is
stated in the module docstring and in the capture plan, rather than implied to
be covered by a passing suite.

No device access, no writes outside a temporary directory.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import windows_tools as wt

PCAPNG_HEAD = bytes.fromhex("0a0d0d0a1c000000")
PCAP_HEAD = bytes.fromhex("d4c3b2a102000400")


class CollisionRefusal(unittest.TestCase):

    def test_an_existing_output_is_refused(self):
        with self.assertRaises(wt.GuardError) as caught:
            wt.refuse_collision("captures/01-first-launch.pcapng", True)
        self.assertIn("already exists", str(caught.exception))
        self.assertIn("-Unique", str(caught.exception))

    def test_a_free_name_is_accepted(self):
        self.assertEqual(wt.refuse_collision("captures/new.pcapng", False),
                         "captures/new.pcapng")

    def test_unique_names_never_collide_with_the_original(self):
        made = wt.unique_name("captures/03-switch.pcapng", "20260920-101500")
        self.assertEqual(made, "captures/03-switch-20260920-101500.pcapng")
        self.assertNotEqual(made, "captures/03-switch.pcapng")
        self.assertTrue(made.endswith(".pcapng"))

    def test_unique_works_without_a_directory(self):
        self.assertEqual(wt.unique_name("trace.log", "20260920-101500"),
                         "trace-20260920-101500.log")

    def test_there_is_no_force_switch_to_find(self):
        self.assertEqual(wt.capture_drift(), [])
        self.assertNotIn("$Force", wt.CAPTURE_PS1.read_text())


class InterfaceValidation(unittest.TestCase):

    ENUMERATED = (r"\\.\USBPcap1", r"\\.\USBPcap2")

    def test_an_unenumerated_interface_is_refused(self):
        with self.assertRaises(wt.GuardError) as caught:
            wt.validate_interfaces((r"\\.\USBPcap9",), self.ENUMERATED)
        self.assertIn("NOT AN ENUMERATED INTERFACE", str(caught.exception))
        self.assertIn("USBPcap9", str(caught.exception))

    def test_one_bad_name_among_good_ones_still_refuses(self):
        with self.assertRaises(wt.GuardError):
            wt.validate_interfaces((r"\\.\USBPcap1", r"\\.\USBPcap9"),
                                   self.ENUMERATED)

    def test_no_request_captures_everything_enumerated(self):
        self.assertEqual(wt.validate_interfaces((), self.ENUMERATED),
                         self.ENUMERATED)

    def test_no_interface_at_all_is_an_error(self):
        with self.assertRaises(wt.GuardError):
            wt.validate_interfaces((), ())


class CaptureOutcome(unittest.TestCase):
    """`saved:` may only be printed when every one of these passes."""

    def test_a_native_failure_is_a_failure(self):
        ok, why = wt.capture_outcome(2, True, 4096, PCAPNG_HEAD)
        self.assertFalse(ok)
        self.assertIn("exited 2", why)

    def test_a_missing_file_is_a_failure(self):
        ok, why = wt.capture_outcome(0, False, 0, b"")
        self.assertFalse(ok)
        self.assertIn("no output file", why)

    def test_a_zero_byte_output_is_a_failure(self):
        ok, why = wt.capture_outcome(0, True, 0, b"")
        self.assertFalse(ok)
        self.assertIn("zero bytes", why)

    def test_a_non_capture_output_is_a_failure(self):
        ok, why = wt.capture_outcome(0, True, 512, b"<html>hi!")
        self.assertFalse(ok)
        self.assertIn("magic number", why)

    def test_a_real_capture_succeeds(self):
        for head in (PCAPNG_HEAD, PCAP_HEAD):
            ok, why = wt.capture_outcome(0, True, 4096, head)
            self.assertTrue(ok, why)

    def test_both_endiannesses_of_the_pcap_magic_are_known(self):
        self.assertTrue(wt.looks_like_capture(bytes.fromhex("a1b2c3d4")))
        self.assertTrue(wt.looks_like_capture(bytes.fromhex("d4c3b2a1")))
        self.assertTrue(wt.looks_like_capture(bytes.fromhex("a1b23c4d")))
        self.assertFalse(wt.looks_like_capture(b"\x00\x00\x00\x00"))
        self.assertFalse(wt.looks_like_capture(b"\x0a\x0d"))

    def test_only_an_empty_stub_of_a_failed_run_is_removed(self):
        self.assertTrue(wt.should_remove_stub(False, True, 0))
        self.assertFalse(wt.should_remove_stub(False, True, 4096),
                         "a partial capture is evidence and is kept")
        self.assertFalse(wt.should_remove_stub(True, True, 0))
        self.assertFalse(wt.should_remove_stub(False, False, 0))

    def test_completion_reports_size_and_sha256(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "x.pcapng"
            target.write_bytes(PCAPNG_HEAD)
            size, digest = wt.completion(target)
            self.assertEqual(size, len(PCAPNG_HEAD))
            self.assertEqual(digest, "936be9e7262677f11185591cf5287e84f0c97378ad78a88d83ca50f286c7c35a")

    def test_the_real_preserved_capture_passes_the_shape_check(self):
        capture = Path(wt.ROOT) / "captures/02-polling-rate.pcap"
        if not capture.is_file():
            self.skipTest("the preserved capture is not present")
        with capture.open("rb") as handle:
            head = handle.read(4)
        self.assertTrue(wt.looks_like_capture(head))
        ok, why = wt.capture_outcome(0, True, capture.stat().st_size, head)
        self.assertTrue(ok, why)


class DbwinOwnership(unittest.TestCase):
    """CreateFileMapping returns a handle for an object that already exists."""

    def test_a_valid_handle_with_already_exists_is_a_conflict(self):
        self.assertTrue(wt.dbwin_conflict(0x1234, wt.ERROR_ALREADY_EXISTS))

    def test_a_valid_handle_with_no_error_is_sole_ownership(self):
        self.assertFalse(wt.dbwin_conflict(0x1234, 0))

    def test_a_null_handle_is_an_outright_failure(self):
        with self.assertRaises(wt.GuardError):
            wt.dbwin_conflict(0, 5)


class ScriptsImplementTheRules(unittest.TestCase):
    """Structural, in the absence of a PowerShell runtime. Order matters."""

    def test_capture_ps1_has_no_drift(self):
        self.assertEqual(wt.capture_drift(), [])

    def test_haltrace_ps1_has_no_drift(self):
        self.assertEqual(wt.haltrace_drift(), [])

    def test_the_order_check_catches_a_reordered_script(self):
        problems = []
        wt._ordered("saved: $Out ... REFUSING", problems, "REFUSING",
                    "saved: $Out", "out of order")
        self.assertEqual(problems, ["out of order"])

    def test_the_order_check_catches_a_deleted_guard(self):
        problems = []
        wt._ordered("nothing here", problems, "REFUSING", "saved: $Out", "x")
        self.assertEqual(problems, ["missing 'REFUSING'"])

    def test_a_reintroduced_force_switch_is_caught(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "capture.ps1"
            target.write_text(
                wt.CAPTURE_PS1.read_text().replace(
                    "[switch]$Unique ", "[switch]$Force,\n  [switch]$Unique "))
            self.assertIn("capture.ps1 has a -Force overwrite escape",
                          wt.capture_drift(target))

    def test_a_reverted_elevation_warning_is_caught(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "haltrace.ps1"
            target.write_text(wt.HALTRACE_PS1.read_text().replace(
                'Write-Host "NOT ELEVATED',
                'Write-Warning "Not elevated"; Write-Host "NOT ELEVATED'))
            self.assertIn("haltrace.ps1 still only warns about elevation",
                          wt.haltrace_drift(target))

    def test_capture_ps1_sends_nothing_to_the_device(self):
        code = wt._code(wt.CAPTURE_PS1)
        for forbidden in ("send.ps1", "HidD_", "WriteFile", "SetOutputReport"):
            self.assertNotIn(forbidden, code)

    def test_haltrace_writes_a_session_artifact_before_it_listens(self):
        """Otherwise the Armoury-Crate-closed experiment, whose expected
        result is zero events, would produce nothing to hash."""
        code = wt._body(wt.HALTRACE_PS1)
        self.assertLess(code.index("start_utc"),
                        code.index("$w = [Dbwin]::WaitForSingleObject"))
        self.assertIn("end_utc", code)
        self.assertNotIn("no output file was created", code)

    def test_haltrace_stamps_lines_with_an_absolute_clock(self):
        """A relative capture time cannot be correlated with this file."""
        code = wt._body(wt.HALTRACE_PS1)
        self.assertIn("ToUniversalTime", code)
        self.assertIn("frame.time_epoch", code)

    def test_the_zero_event_artifact_rule_is_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "haltrace.ps1"
            target.write_text(wt.HALTRACE_PS1.read_text().replace(
                '"# start_utc   : $($startUtc.ToString(\'o\'))"', '""'))
            self.assertTrue(
                [item for item in wt.haltrace_drift(target)
                 if "start_utc" in item])

    def test_haltrace_ps1_sends_nothing_to_the_device(self):
        code = wt._code(wt.HALTRACE_PS1)
        for forbidden in ("send.ps1", "HidD_", "WriteFile", "SetOutputReport"):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
