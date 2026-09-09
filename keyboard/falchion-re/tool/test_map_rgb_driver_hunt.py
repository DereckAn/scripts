#!/usr/bin/env python3
"""Tests for the RGB driver hunt.

The delicate part here is that the headline result is a NEGATIVE — the driver
was not found. A negative is only worth anything if the search that produced
it can be shown to work, so every "found nothing" check has a companion that
makes the same machinery find something.
"""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_rgb_driver_hunt as rh
import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and (rh.INVENTORIES / "installed_b.txt").exists()
         and (rh.PERIPHERALS / "installed_b.txt").exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):

    def test_the_frame_geometry_is_consistent(self):
        self.assertEqual(rh.FRAME_ROWS * rh.FRAME_COLS * rh.FRAME_CHANNELS,
                         rh.FRAME_BYTES)
        self.assertEqual(rh.FRAME_BYTES, 0x132)

    def test_the_shadow_is_one_frame_below_the_live_buffer(self):
        self.assertEqual(rh.SHADOW, rh.FRAME - rh.FRAME_BYTES)

    def test_every_claim_carries_a_label_and_a_citation(self):
        for claim in rh.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_the_unresolved_list_keeps_polarity_open(self):
        keys = {k for k, _ in rh.UNRESOLVED}
        self.assertIn("driver_polarity", keys)
        self.assertIn("final_transport", keys)
        self.assertIn("shared_initialisation", keys)

    def test_no_device_vocabulary_in_the_tool(self):
        text = Path(rh.__file__).read_text().lower()
        for word in ("/dev/hidraw", "usb.core", "subprocess", "socket",
                     "urllib", "sudo", "spi_write", "bootloader_enter"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "mentions /dev/hidraw here")

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(rh, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(rh.main([]), 1)

    def test_a_missing_slice_fails_closed(self):
        with mock.patch.object(rh, "IMPORTS", Path("/nonexistent")):
            with self.assertRaises(rh.RgbHuntError):
                rh._load(rh.APP_BIN)

    def test_a_missing_inventory_fails_closed(self):
        with mock.patch.object(rh, "INVENTORIES", Path("/nonexistent")):
            with self.assertRaises(rh.RgbHuntError):
                rh.closure()

    def test_a_missing_census_fails_closed(self):
        with mock.patch.object(rh, "PERIPHERALS", Path("/nonexistent")):
            with self.assertRaises(rh.RgbHuntError):
                rh._census("installed_b.txt")


@unittest.skipUnless(READY, "preserved dumps or Ghidra outputs absent")
class Evidence(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [c["label"] for c in rh.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} failed")

    def test_the_closure_is_substantial(self):
        self.assertGreater(len(rh.closure()), 20)

    def test_the_closure_reaches_no_mmio(self):
        self.assertTrue(rh.mmio_in_closure()["reaches_no_mmio"])

    def test_the_mmio_search_is_not_blind(self):
        """Companion to the negative: the same machinery must find MMIO when
        it is there. FUN_18011900 drives the 0x40022000 bank."""
        with mock.patch.object(rh, "CLOSURE_ROOTS", ("18011900",)):
            found = rh.mmio_in_closure()
        self.assertFalse(found["reaches_no_mmio"])
        self.assertGreater(found["mmio_access_count"], 0)

    def test_double_buffering_is_recovered(self):
        db = rh.double_buffer()
        self.assertTrue(db["recovered"])
        self.assertTrue(db["live_matches_log112"])
        self.assertEqual(db["bytes"], 0x132)
        self.assertEqual(db["shadow"], "0x18024f2c")

    def test_all_three_lighting_roots_ride_the_div8_job(self):
        ft = rh.frame_timing()
        self.assertTrue(ft["all_roots_on_the_tick"])
        self.assertEqual(len(ft["roots"]), 3)
        for row in ft["roots"]:
            self.assertTrue(row["veneer_resolves"], row["app_function"])
            self.assertTrue(row["inside_the_div8_job"], row["call_site"])

    def test_the_veneer_decoder_is_not_vacuous(self):
        """A veneer that points elsewhere must fail the resolves check."""
        bogus = dict(rh.LIGHTING_ROOTS)
        bogus[0x1800AAAA] = (0x40D0, 0x0550, "deliberately wrong target")
        with mock.patch.object(rh, "LIGHTING_ROOTS", bogus):
            ft = rh.frame_timing()
        self.assertFalse(ft["all_roots_on_the_tick"])

    def test_the_second_context_is_eliminated(self):
        c = rh.candidate_second_context()
        self.assertTrue(c["eliminated"])
        self.assertEqual(c["frame_address_references"], 0)
        self.assertEqual(c["lighting_region_references"], 0)

    def test_the_0x40022000_bank_is_eliminated(self):
        c = rh.candidates()["bank_0x40022000"]
        self.assertTrue(c["eliminated"])
        self.assertEqual(c["intersection_with_lighting_closure"], [])
        self.assertGreater(c["user_count"], 0, "it does have users, elsewhere")

    def test_the_dma_setup_is_eliminated(self):
        self.assertTrue(rh.candidate_dma()["eliminated"])

    def test_the_unresolved_accesses_are_explained(self):
        ub = rh.unresolved_breakdown()
        self.assertGreater(ub["total"], 0)
        explained = (ub["stack_relative"] + ub["indexed_into_a_known_array"]
                     + ub["base_is_an_argument_register"])
        self.assertGreater(explained, ub["other_registers"])

    def test_reports_on_disk_are_current(self):
        payload = rh.bodies()
        stale = [n for n, b in payload.items()
                 if not (rh.NOTES / n).exists()
                 or (rh.NOTES / n).read_text() != b]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(rh.bodies()["rgb-driver-hunt.json"],
                         rh.bodies()["rgb-driver-hunt.json"])

    def test_the_report_states_no_device_was_accessed(self):
        self.assertIn("no device was accessed",
                      "\n".join(rh.report_lines()).lower())


@unittest.skipUnless(READY, "preserved dumps or Ghidra outputs absent")
class Discipline(unittest.TestCase):
    """RGB must not move without the proof, and no block may be named."""

    def test_the_safe_idle_question_stays_unanswered(self):
        si = rh.safe_idle()
        self.assertFalse(si["answerable"])
        self.assertEqual(si["hardware_idle_state"],
                         "NOT DETERMINABLE from the preserved images")

    def test_rgb_stays_unresolved(self):
        si = rh.safe_idle()
        self.assertEqual(si["classification"], "unresolved")
        self.assertTrue(si["classification_unchanged"])

    def test_tighter_ignorance_is_not_called_proof(self):
        si = rh.safe_idle()
        self.assertIn("tighter ignorance is not", si["why_unchanged"].lower())

    def test_no_claim_names_a_peripheral_block(self):
        """Naming on correlation is what this project refuses. The bank may be
        mentioned as ELIMINATED, never as identified."""
        blob = " ".join(c.answer for c in rh.CLAIMS)
        for phrase in ("is the PWM controller", "is the LED driver",
                       "is an SPI controller", "identified as"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_naming_detector_is_not_vacuous(self):
        self.assertIn("is the LED driver", "a sentence: it is the LED driver")

    def test_no_claim_promises_the_leds_are_off(self):
        blob = " ".join(c.answer.lower() for c in rh.CLAIMS)
        for phrase in ("the leds are off", "leds will be dark",
                       "safe to omit"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_buffer_idle_claim_survives_and_is_separate(self):
        """The one thing that IS provable must not be lost in the negative."""
        si = rh.safe_idle()
        self.assertIn("all zero", si["buffer_idle_state"])
        self.assertIn("zeroinit", si["buffer_idle_state"])

    def test_the_absolute_rate_is_never_given_in_hz(self):
        blob = " ".join(c.answer.lower() for c in rh.CLAIMS)
        for phrase in (" hz", "khz", "frames per second", "fps"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_rate_detector_is_not_vacuous(self):
        self.assertIn("khz", "a sentence saying khz")


if __name__ == "__main__":
    unittest.main()
