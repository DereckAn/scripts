#!/usr/bin/env python3
"""Tests for the calibration lifecycle.

`Pure` runs anywhere. `Evidence` needs the preserved dumps and the Ghidra
inventory and skips rather than passing when they are absent.

`Discipline` guards the two things this step could most easily get wrong: the
exhaustiveness claim (only three writers) and the safe-direction claim (an
uncalibrated key reads released). Both are tied to computations that move when
the evidence moves, and both have anti-vacuity companions.
"""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_calibration_flow as cf
import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and (cf.INVENTORIES / "ram18038000.txt").exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):

    def test_every_claim_carries_a_label_and_a_citation(self):
        for claim in cf.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_the_scale_formula_is_arithmetic_not_assertion(self):
        span = cf.DEFAULT_REFERENCE - cf.DEFAULT_FLOOR
        self.assertEqual(span, 2100)
        self.assertEqual(cf.SCALE_NUMERATOR // span, cf.DEFAULT_SCALE)

    def test_the_formula_would_notice_a_wrong_default(self):
        """Anti-vacuity: the identity must not hold for just any span.

        A one-unit perturbation is NOT enough — integer division absorbs it,
        which is itself worth knowing, so the test uses a span difference the
        quotient actually resolves.
        """
        span = cf.DEFAULT_REFERENCE - cf.DEFAULT_FLOOR
        self.assertEqual(cf.SCALE_NUMERATOR // (span + 1), cf.DEFAULT_SCALE,
                         "integer division absorbs a one-unit change")
        self.assertNotEqual(cf.SCALE_NUMERATOR // (span + 100),
                            cf.DEFAULT_SCALE)

    def test_the_service_entry_is_well_formed(self):
        svc = cf.SERVICE
        self.assertIn(svc["classification"],
                      ("must-implement", "must-neutralize", "may-omit",
                       "unresolved"))
        self.assertTrue(svc["evidence"])
        self.assertGreater(len(svc["evidence_boundary"]), 60)

    def test_the_service_is_never_may_omit(self):
        """Omitting calibration would mean shipping a keyboard that never
        reports a keypress; the classification must never drift there."""
        self.assertNotEqual(cf.SERVICE["classification"], "may-omit")

    def test_the_unresolved_list_keeps_the_physics_open(self):
        keys = {k for k, _ in cf.UNRESOLVED}
        self.assertIn("physical_units", keys)
        self.assertIn("drift_constants", keys)
        self.assertIn("settling_duration", keys)

    def test_no_device_or_command_vocabulary_in_the_tool(self):
        text = Path(cf.__file__).read_text().lower()
        for word in ("/dev/hidraw", "usb.core", "subprocess", "socket",
                     "urllib", "sudo", "spi_write", "bootloader_enter",
                     "hid.write", "send_report"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "mentions /dev/hidraw here")

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(cf, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(cf.main([]), 1)

    def test_a_read_outside_the_image_fails_closed(self):
        if not READY:
            self.skipTest("preserved dumps absent")
        with self.assertRaises(cf.CalibrationError):
            cf._read(0x18037000, 4)

    def test_a_missing_inventory_fails_closed(self):
        with mock.patch.object(cf, "INVENTORIES", Path("/nonexistent")):
            with self.assertRaises(cf.CalibrationError):
                cf.writers()


@unittest.skipUnless(READY, "preserved dumps or Ghidra inventory absent")
class Evidence(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [c["label"] for c in cf.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} failed")

    def test_reference_floor_and_scale_are_all_bss(self):
        arr = {a["name"]: a for a in cf.arrays()}
        for name in ("reference", "floor", "scale"):
            self.assertFalse(arr[name]["initialised_in_image"], name)
            self.assertEqual(arr[name]["nonzero_bytes_in_image"], 0, name)

    def test_the_bss_check_can_detect_initialised_data(self):
        """Anti-vacuity: the travel curve IS initialised, so the same
        predicate must report it as such."""
        raw = cf._read(cf.LUT, cf.LUT_LEN)
        self.assertGreater(sum(1 for b in raw if b), 0)

    def test_exactly_four_functions_touch_the_block(self):
        wr = cf.writers()
        self.assertEqual(len(wr), 4, [w["function"] for w in wr])
        entries = {w["entry"] for w in wr}
        self.assertEqual(entries, {f"0x{cf.INITIALISER:08x}",
                                   f"0x{cf.UPDATER:08x}",
                                   f"0x{cf.CONVERTER:08x}",
                                   f"0x{cf.GATE_INIT:08x}"})

    def test_the_exhaustiveness_scan_would_notice_a_fifth(self):
        """Widen the block and the scan must find more, proving it is a real
        search rather than a fixed list."""
        with mock.patch.object(cf, "BLOCK_LO", 0x1803C000):
            wider = cf.writers()
        self.assertGreater(len(wider), 4)

    def test_only_one_function_is_a_reader(self):
        readers = [w for w in cf.writers() if w["role"] == "reader"]
        self.assertEqual(len(readers), 1)
        self.assertEqual(readers[0]["entry"], f"0x{cf.CONVERTER:08x}")

    def test_the_formula_reproduces_the_default_scale(self):
        sf = cf.scale_formula()
        self.assertTrue(sf["formula_reproduces_the_default"])
        self.assertEqual(sf["default_scale_from_formula"], cf.DEFAULT_SCALE)

    def test_full_travel_lands_on_the_curve_maximum(self):
        sf = cf.scale_formula()
        self.assertTrue(sf["full_travel_reaches_the_curve_maximum"])
        self.assertEqual(sf["lut_maximum"], cf.ACTUATION_THRESHOLD * 2)

    def test_the_lifecycle_has_no_storage_stage(self):
        stages = {s["stage"]: s for s in cf.lifecycle()}
        self.assertEqual(stages["storage load"]["writer"], "none")
        self.assertEqual(stages["persistence"]["writer"], "none")

    def test_the_mailbox_carries_no_calibration(self):
        mb = cf.mailbox_relationship()
        self.assertFalse(mb["carries_calibration"])
        self.assertIsNone(mb["recalibrate_opcode"])
        self.assertIsNone(mb["host_command"])

    def test_both_orphan_roots_are_resolved(self):
        self.assertEqual(len(cf.mailbox_relationship()["orphans_resolved"]), 2)

    def test_reports_on_disk_are_current(self):
        payload = cf.bodies()
        stale = [n for n, b in payload.items()
                 if not (cf.NOTES / n).exists()
                 or (cf.NOTES / n).read_text() != b]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(cf.bodies()["calibration-flow.json"],
                         cf.bodies()["calibration-flow.json"])

    def test_the_report_states_no_device_and_no_command(self):
        text = "\n".join(cf.report_lines()).lower()
        self.assertIn("no device was accessed", text)
        self.assertIn("no command was constructed", text)


@unittest.skipUnless(READY, "preserved dumps or Ghidra inventory absent")
class Discipline(unittest.TestCase):
    """The two claims most worth guarding."""

    def test_an_uncalibrated_key_reads_released(self):
        inv = cf.invalid_behaviour()
        self.assertEqual(inv["uncalibrated_key_reads"], "RELEASED")
        self.assertTrue(inv["safe_direction"])

    def test_the_safe_direction_is_argued_from_code(self):
        """It must cite the mechanism, not merely assert the outcome."""
        why = cf.invalid_behaviour()["why_safe"]
        self.assertIn("travel >= 100", why)
        self.assertIn("not a hope", why)

    def test_the_sentinel_never_reaches_the_subtraction(self):
        inv = cf.invalid_behaviour()
        self.assertFalse(inv["sentinel_wraps"])
        self.assertIn("compares each sample against the sentinel FIRST",
                      inv["sentinel_effect"])

    def test_no_claim_says_calibration_is_reproducible(self):
        """Recovering the lifecycle does not mean a replacement can re-derive
        it, and the wording must not blur that."""
        blob = " ".join(c.answer.lower() for c in cf.CLAIMS)
        for phrase in ("can be reimplemented", "can be reproduced",
                       "we can re-derive", "fully reproducible"):
            self.assertNotIn(phrase, blob, phrase)
        self.assertIn("never implement",
                      " ".join(c.answer.lower() for c in cf.CLAIMS))

    def test_the_reproducibility_detector_is_not_vacuous(self):
        self.assertIn("can be reproduced", "a sentence: it can be reproduced")

    def test_no_claim_states_a_settling_duration_in_time(self):
        """600 passes on an unknown tick is a count, not a duration."""
        blob = " ".join(c.answer.lower() for c in cf.CLAIMS)
        for phrase in ("milliseconds", "seconds of settling", " ms of",
                       "takes about"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_duration_detector_is_not_vacuous(self):
        self.assertIn("milliseconds", "a sentence saying milliseconds")

    def test_no_command_bytes_are_recorded_anywhere(self):
        """The step explicitly must not produce anything transmittable. Since
        no host command exists, the payload must contain no frame."""
        blob = cf.bodies()["calibration-flow.json"].lower()
        for phrase in ("send ", "transmit", "write_report", "0x51 0x", "frame:"):
            self.assertNotIn(phrase, blob, phrase)


if __name__ == "__main__":
    unittest.main()
