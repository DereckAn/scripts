#!/usr/bin/env python3
"""Offline tests for the Phase 5C scan-to-HID pipeline.

The point of most of these is to keep the model HONEST rather than to check
arithmetic: Phase 5C recovered the scheduling chain but not the acquisition, and
a later edit that quietly upgraded an unresolved link to observed, or that
restated the 189-entry translation table as a key count, would be the failure
mode that matters. No device access, no writes outside a temporary directory.
"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_scan_pipeline as sp
import map_usb_routing as ur

READY = (ur.IMPORTS / ur.REGIONS["installed"][0]).exists()


class Relocation(unittest.TestCase):
    """Getting this backwards would silently compare two different functions."""

    def test_the_entry_image_does_not_relocate(self):
        for address in (0x498, 0x42C, 0x4BA):
            self.assertEqual(
                sp.release_address(address, "entry", "vendor"), address)

    def test_an_application_function_below_the_insertion_does_not_move(self):
        self.assertLess(0x18004164, sp.INSERTION_POINT)
        self.assertEqual(
            sp.release_address(0x18004164, "app", "vendor"), 0x18004164)

    def test_an_application_function_above_the_insertion_moves(self):
        self.assertGreater(0x180061C2, sp.INSERTION_POINT)
        self.assertEqual(sp.release_address(0x180061C2, "app", "vendor"),
                         0x180061C2 - sp.RELOCATION_DELTA)

    def test_ram_and_region_addresses_always_move(self):
        for image in ("ram", "region"):
            self.assertEqual(
                sp.release_address(0x1801E734, image, "vendor"),
                0x1801E734 - sp.RELOCATION_DELTA)

    def test_installed_is_the_identity(self):
        self.assertEqual(
            sp.release_address(0x180061C2, "app", "installed"), 0x180061C2)

    def test_an_unknown_image_raises_rather_than_guessing(self):
        with self.assertRaises(sp.ScanError):
            sp.release_address(0x1000, "somewhere", "vendor")


class ModelHonesty(unittest.TestCase):

    def test_the_acquisition_stage_stays_unresolved(self):
        """Phase 5C did not recover it. An edit that marks it observed without
        new evidence is the regression this test exists to catch."""
        stage, = [item for item in sp.STAGES if item.key == "acquisition"]
        self.assertEqual(stage.confidence, "unresolved")
        self.assertIn("NOT RECOVERED", stage.detail)

    def test_the_link_into_the_key_array_stays_unresolved(self):
        link, = [item for item in sp.LINKS if item.source == "acquisition"]
        self.assertEqual(link.confidence, "unresolved")

    def test_no_absolute_scan_rate_is_claimed(self):
        payload = sp.to_dict()
        self.assertEqual(payload["cadence"]["period_confidence"], "unresolved")
        text = "\n".join(sp.report_lines()).lower()
        for unit in (" hz", "milliseconds", "microseconds", " ms ", " us "):
            self.assertNotIn(unit, text, f"{unit!r} implies a rate")

    def test_no_physical_dimension_is_claimed(self):
        physical = sp.to_dict()["physical_dimensions"]
        self.assertIsNone(physical["rows"])
        self.assertIsNone(physical["columns"])
        self.assertIsNone(physical["keys"])
        self.assertIn("189", physical["note"])

    def test_the_translation_table_size_is_never_used_as_a_dimension(self):
        """189 is a wire-ID map. It must not appear as a count anywhere."""
        payload = sp.to_dict()
        for key in ("report_dimensions", "buffers", "stages", "links"):
            self.assertNotIn("189", str(payload[key]))

    def test_no_contact_matrix_model_is_asserted(self):
        text = "\n".join(sp.report_lines()).lower()
        self.assertIn("hall-effect", text)
        for phrase in ("row drive", "column read", "the matrix is"):
            self.assertNotIn(phrase, text)

    def test_every_confidence_is_from_the_closed_set(self):
        for item in list(sp.STAGES) + list(sp.LINKS) + list(sp.BUFFERS):
            self.assertIn(item.confidence, sp.CONFIDENCES,
                          sp.label_of(item))

    def test_every_link_joins_declared_stages(self):
        keys = {stage.key for stage in sp.STAGES}
        for link in sp.LINKS:
            self.assertIn(link.source, keys)
            self.assertIn(link.target, keys)

    def test_every_observed_claim_cites_an_address(self):
        for item in list(sp.STAGES) + list(sp.LINKS) + list(sp.BUFFERS):
            if item.confidence == "observed":
                self.assertIn("0x", item.kind_basis, sp.label_of(item))

    def test_a_buffer_with_no_recovered_producer_says_so(self):
        """Log 110 moved this: 0x18023410 turned out to be the key-state
        BITMAP, which does have a recovered writer. The buffer that still has
        no producer is the travel-byte pointer cell."""
        cell, = [item for item in sp.BUFFERS if item.address == 0x1801ED6C]
        self.assertEqual(cell.confidence, "unresolved")
        self.assertIn("UNRESOLVED", cell.synchronisation)

    def test_the_key_state_array_is_a_bitmap_with_a_known_writer(self):
        bitmap, = [item for item in sp.BUFFERS if item.address == 0x18023410]
        self.assertEqual(bitmap.confidence, "observed")
        self.assertIn("bitmap", bitmap.name.lower())
        self.assertNotIn("halfword", bitmap.name.lower())
        self.assertEqual(bitmap.size, 20, "5 groups x 4 bytes")

    def test_the_event_word_records_its_synchronisation(self):
        word, = [item for item in sp.BUFFERS if item.address == 0x1801EE84]
        self.assertIn("cpsid", word.kind_basis)
        self.assertIn("interrupt masking", word.synchronisation.lower())


@unittest.skipUnless(READY, "reconstructed region not present")
class ReportGeometry(unittest.TestCase):
    """Dimensions must come from each descriptor's own items."""

    @classmethod
    def setUpClass(cls):
        cls.dimensions = sp.report_dimensions("installed")

    def test_the_nkro_report_is_152_bits_in_19_bytes(self):
        three = self.dimensions[3]
        self.assertEqual((three["last_report_size"],
                          three["last_report_count"]), (1, 152))
        self.assertEqual(three["bits"], 152)
        self.assertEqual(three["bits"] // 8, three["packet_bytes"])

    def test_152_is_not_189(self):
        self.assertNotEqual(self.dimensions[3]["bits"], 189)

    def test_the_boot_report_packet_is_eight_bytes(self):
        self.assertEqual(self.dimensions[0]["packet_bytes"], 8)

    def test_both_releases_agree_on_every_report_dimension(self):
        self.assertEqual(sp.report_dimensions("installed"),
                         sp.report_dimensions("vendor"))

    def test_every_interface_yields_a_dimension_record(self):
        self.assertEqual(sorted(self.dimensions), [0, 1, 2, 3, 4])


@unittest.skipUnless(READY, "reconstructed region not present")
class Artifacts(unittest.TestCase):

    def test_every_check_passes(self):
        for item in sp.verify():
            self.assertTrue(item["ok"], item["name"])

    def test_json_is_deterministic(self):
        self.assertEqual(sp.bodies(), sp.bodies())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in sp.bodies().items()
                 if not (sp.NOTES / name).exists()
                 or (sp.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/map_scan_pipeline.py --write")

    def test_the_report_states_both_limitations(self):
        text = "\n".join(sp.report_lines())
        self.assertIn("Call-graph reachability is not timing", text)
        self.assertIn("is NOT recovered", text)


if __name__ == "__main__":
    unittest.main()
