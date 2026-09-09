#!/usr/bin/env python3
"""Offline tests for the Phase 5F RGB / LampArray route.

The arithmetic tests execute the recovered frame model. The rest keep it honest:
Phase 5F recovered the protocol and the frame buffer but NOT the hardware that
consumes it, and a later edit that quietly identified the driver, or that
claimed the LEDs are provably off when RGB is omitted, is the failure mode that
matters. No device access, no writes outside a temporary directory.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_rgb_lamparray as rgb
import map_usb_routing as ur

READY = ((ur.IMPORTS / ur.REGIONS["installed"][0]).exists()
         and (rgb.IMPORTS / rgb.ENTRY_SLICE).exists()
         and rgb.MATCH_APP.exists())


class FrameArithmetic(unittest.TestCase):
    """The recovered cell arithmetic, exercised rather than described."""

    def test_the_offset_matches_the_shift_multiplies(self):
        self.assertEqual(rgb.frame_offset(0, 0), 0)
        self.assertEqual(rgb.frame_offset(0, 1), 3)
        self.assertEqual(rgb.frame_offset(1, 0), rgb.FRAME_COLUMNS * 3)
        self.assertEqual(rgb.frame_offset(5, 16),
                         (5 * 17 + 16) * 3)

    def test_the_last_cell_ends_exactly_at_the_buffer_end(self):
        last = rgb.frame_offset(rgb.FRAME_ROWS - 1, rgb.FRAME_COLUMNS - 1)
        self.assertEqual(last + rgb.FRAME_BYTES_PER_CELL, len(rgb.blank_frame()))

    def test_a_row_out_of_range_raises(self):
        with self.assertRaises(rgb.RgbError):
            rgb.frame_offset(rgb.FRAME_ROWS, 0)
        with self.assertRaises(rgb.RgbError):
            rgb.frame_offset(-1, 0)

    def test_a_column_out_of_range_raises(self):
        with self.assertRaises(rgb.RgbError):
            rgb.frame_offset(0, rgb.FRAME_COLUMNS)

    def test_intensity_scales_by_a_shift_of_eight(self):
        self.assertEqual(rgb.apply_intensity(0xFF, 0xFF), 0xFE)
        self.assertEqual(rgb.apply_intensity(0xFF, 0x80), 0x7F)
        self.assertEqual(rgb.apply_intensity(0x10, 0xFF), 0x0F)
        self.assertEqual(rgb.apply_intensity(0xFF, 0), 0)
        self.assertEqual(rgb.apply_intensity(0, 0xFF), 0)

    def test_full_intensity_is_not_identity(self):
        """(ch*255)>>8 loses one count at the top. A model that returned the
        channel unchanged would be wrong, and this catches it."""
        self.assertNotEqual(rgb.apply_intensity(0xFF, 0xFF), 0xFF)

    def test_a_channel_outside_a_byte_raises(self):
        with self.assertRaises(rgb.RgbError):
            rgb.apply_intensity(0x100, 0xFF)
        with self.assertRaises(rgb.RgbError):
            rgb.apply_intensity(0xFF, -1)

    def test_a_cell_write_lands_in_rgb_order(self):
        frame = rgb.write_cell(rgb.blank_frame(), 2, 3,
                               0xFF, 0x80, 0x40, 0xFF)
        base = rgb.frame_offset(2, 3)
        self.assertEqual(list(frame[base:base + 3]), [0xFE, 0x7F, 0x3F])

    def test_an_out_of_range_cell_is_dropped_silently(self):
        """Both `bcs` branches jump straight to the return, so the caller
        cannot tell — and neither can this model."""
        frame = rgb.write_cell(rgb.blank_frame(), rgb.FRAME_ROWS, 0,
                               0xFF, 0xFF, 0xFF, 0xFF)
        self.assertEqual(frame, rgb.blank_frame())
        frame = rgb.write_cell(rgb.blank_frame(), 0, rgb.FRAME_COLUMNS,
                               0xFF, 0xFF, 0xFF, 0xFF)
        self.assertEqual(frame, rgb.blank_frame())

    def test_a_blank_frame_is_all_zero_and_the_right_size(self):
        frame = rgb.blank_frame()
        self.assertEqual(len(frame), 306)
        self.assertEqual(set(frame), {0})

    def test_writing_every_cell_touches_every_byte(self):
        frame = rgb.blank_frame()
        for row in range(rgb.FRAME_ROWS):
            for column in range(rgb.FRAME_COLUMNS):
                rgb.write_cell(frame, row, column, 0xFF, 0xFF, 0xFF, 0xFF)
        self.assertEqual(set(frame), {0xFE})


class Honesty(unittest.TestCase):

    def test_the_hardware_boundary_stays_unidentified(self):
        boundary = rgb.to_dict()["hardware_boundary"]
        self.assertFalse(boundary["identified"])
        self.assertIn("NOT named", boundary["note"])
        claim, = [item for item in rgb.CLAIMS
                  if item.key == "hardware_boundary"]
        self.assertEqual(claim.confidence, "unresolved")

    def test_no_mmio_block_is_named_for_lighting(self):
        text = json.dumps(rgb.to_dict())
        self.assertNotIn("PWM controller", text)
        self.assertNotIn("SPI controller", text)
        self.assertNotIn("LED driver at", text)

    def test_the_hardware_idle_state_is_not_claimed_provable(self):
        """The buffer's idle state IS provable; the LEDs' is not, because the
        driver's polarity is unknown."""
        omission = rgb.to_dict()["safe_omission"]
        self.assertTrue(omission["buffer_idle_state_provable"])
        self.assertFalse(omission["hardware_idle_state_provable"])
        self.assertIn("polarity is unknown", omission["note"])

    def test_frame_timing_stays_unresolved(self):
        claim, = [item for item in rgb.CLAIMS if item.key == "frame_timing"]
        self.assertEqual(claim.confidence, "unresolved")

    def test_spec_derived_names_are_labelled_not_observed(self):
        """Report semantics come from HID page 0x59, not from this device."""
        text = "\n".join(rgb.report_lines())
        self.assertIn("names are spec-derived", text)
        self.assertIn("not observed on this device", text)

    def test_every_claim_names_its_source(self):
        for item in rgb.CLAIMS:
            self.assertIn(item.verified_against, rgb.SOURCES, item.key)
            self.assertGreater(len(item.kind_basis), 30, item.key)

    def test_the_load_bearing_frame_claims_are_listing_verified(self):
        for key in ("frame_geometry", "frame_order", "intensity",
                    "out_of_range_dropped", "get_lengths",
                    "callback_registration", "request_dispatch"):
            claim, = [item for item in rgb.CLAIMS if item.key == key]
            self.assertEqual(claim.verified_against, "listing", key)


@unittest.skipUnless(READY, "reconstructed region or entry slice not present")
class Descriptor(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.reports = rgb.descriptor_reports("installed")

    def test_six_reports_all_feature(self):
        self.assertEqual(sorted(self.reports), [1, 2, 3, 4, 5, 6])
        for value in self.reports.values():
            self.assertEqual(value["kinds"], ["Feature"])

    def test_no_output_report_exists_despite_the_out_endpoint(self):
        """Interface 4 has a 64-byte OUT endpoint and no Output report, which
        is why the LampArray runs over control transfers."""
        for value in self.reports.values():
            self.assertNotIn("Output", value["kinds"])

    def test_report_one_is_twenty_three_wire_bytes(self):
        self.assertEqual(self.reports[1]["wire_bytes"], 0x17)

    def test_every_report_is_handled_by_the_firmware(self):
        for rid in self.reports:
            self.assertIn(rgb.HANDLED[rid], ("GET", "SET"), rid)

    def test_both_releases_declare_the_same_reports(self):
        vendor = rgb.descriptor_reports("vendor")
        self.assertEqual(
            {rid: value["wire_bytes"] for rid, value in self.reports.items()},
            {rid: value["wire_bytes"] for rid, value in vendor.items()})

    def test_the_lamp_counts_all_fit_the_frame(self):
        cells = rgb.FRAME_ROWS * rgb.FRAME_COLUMNS
        for count in rgb.lamp_counts():
            self.assertLessEqual(count, cells, count)
            self.assertGreater(count, 0)

    def test_a_short_entry_slice_fails_closed(self):
        original = rgb.IMPORTS
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / rgb.ENTRY_SLICE).write_bytes(b"\x00" * 16)
            rgb.IMPORTS = Path(directory)
            try:
                with self.assertRaises(rgb.RgbError):
                    rgb.lamp_counts()
            finally:
                rgb.IMPORTS = original


@unittest.skipUnless(READY, "prerequisites not present")
class Artifacts(unittest.TestCase):

    def test_every_check_passes(self):
        for item in rgb.verify():
            self.assertTrue(item["ok"], item["name"])

    def test_json_is_deterministic(self):
        self.assertEqual(rgb.bodies(), rgb.bodies())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in rgb.bodies().items()
                 if not (rgb.NOTES / name).exists()
                 or (rgb.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/map_rgb_lamparray.py --write")

    def test_every_route_function_has_a_measured_counterpart(self):
        for name, item in rgb.to_dict()["route"].items():
            self.assertIsNotNone(item["vendor"], name)
            self.assertIsNotNone(item["vendor_match"], name)

    def test_the_classification_is_implemented_with_its_caveat(self):
        classification = rgb.to_dict()["classification"]
        self.assertEqual(classification["verdict"], "implemented")
        self.assertIn("cannot yet drive the LEDs", classification["detail"])


if __name__ == "__main__":
    unittest.main()
