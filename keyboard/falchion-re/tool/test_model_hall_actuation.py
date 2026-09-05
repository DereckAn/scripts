#!/usr/bin/env python3
"""Offline tests for the Phase 5D Hall actuation model.

The arithmetic tests execute the recovered decision so the model is checked and
not merely described. The rest keep the model honest: Phase 5D recovered the
comparison but NOT the acquisition, and a later edit that quietly upgraded that
boundary, or attached a physical unit to a unitless number, is the failure mode
that matters. No device access, no writes outside a temporary directory.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import model_hall_actuation as ha

READY = ha.MATCH_APP.exists()


class Decision(unittest.TestCase):
    """The recovered comparison, exercised over its whole domain."""

    def test_at_and_above_the_threshold_actuates(self):
        for travel in (ha.ACTUATE_AT, ha.ACTUATE_AT + 1, 255):
            self.assertTrue(ha.actuate(travel, False), travel)
            self.assertTrue(ha.actuate(travel, True), travel)

    def test_zero_releases_from_either_state(self):
        self.assertFalse(ha.actuate(0, True))
        self.assertFalse(ha.actuate(0, False))

    def test_the_hold_band_preserves_the_previous_state(self):
        """1..99 is the band the sub-threshold branch skips over. It is the
        whole reason a key does not chatter across the threshold."""
        for travel in range(1, ha.ACTUATE_AT):
            self.assertTrue(ha.actuate(travel, True), travel)
            self.assertFalse(ha.actuate(travel, False), travel)

    def test_the_band_is_exactly_one_to_ninety_nine(self):
        held = [travel for travel in range(0, 256)
                if ha.actuate(travel, True) and not ha.actuate(travel, False)]
        self.assertEqual(held, list(range(1, ha.ACTUATE_AT)))


class Clamp(unittest.TestCase):

    def test_the_clamp_matches_the_recovered_branches(self):
        self.assertEqual([ha.clamp_actuation(v) for v in range(8)],
                         [0, 0, 0, 1, 2, 3, 3, 3])

    def test_the_field_mask_is_applied_before_the_clamp(self):
        """`and r0,r0,#0x7f` precedes the compare, so bit 7 and above are
        dropped rather than saturating the result."""
        self.assertEqual(ha.clamp_actuation(0x80), ha.clamp_actuation(0))
        self.assertEqual(ha.clamp_actuation(0x83), ha.clamp_actuation(3))

    def test_the_clamp_never_exceeds_its_maximum(self):
        for value in range(256):
            self.assertLessEqual(ha.clamp_actuation(value),
                                 ha.ACTUATION_CLAMP_MAX)


class Geometry(unittest.TestCase):

    def test_the_layer_stride_is_the_product(self):
        self.assertEqual(ha.LAYER_STRIDE, 0x4B)
        self.assertEqual(ha.layer_offset(1), 0x4B)
        self.assertEqual(ha.layer_offset(2), 0x96)

    def test_key_index_matches_the_shift_multiply(self):
        self.assertEqual(ha.key_index(0, 0), 0)
        self.assertEqual(ha.key_index(1, 0), ha.GROUP_STRIDE)
        self.assertEqual(ha.key_index(4, 14), ha.LAYER_STRIDE - 1)

    def test_a_group_out_of_range_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.key_index(ha.OUTER_GROUPS, 0)
        with self.assertRaises(ha.ModelError):
            ha.key_index(-1, 0)

    def test_a_position_out_of_range_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.key_index(0, ha.GROUP_STRIDE)


class ScanPass(unittest.TestCase):

    def keymap(self, fill=0x04):
        return [fill] * (ha.LAYER_STRIDE * 2)

    def test_a_full_pass_sets_and_clears_the_right_bits(self):
        """The linear travel index advances `active_positions` per group, so
        a period-2 pattern gives every group the SAME bits — position 0 set,
        position 1 clear. Getting this wrong is how an off-by-one in the
        linear index would hide."""
        travel = [ha.ACTUATE_AT if i % 2 == 0 else 0 for i in range(10)]
        bits = ha.scan_pass(travel, self.keymap(), [0] * 5, 2)
        self.assertEqual(bits, [0b01] * 5)

    def test_each_group_reads_its_own_slice_of_the_travel_bytes(self):
        """A per-group pattern proves the linear index really advances."""
        travel = [0] * 10
        travel[4] = ha.ACTUATE_AT      # group 2, position 0
        travel[7] = ha.ACTUATE_AT      # group 3, position 1
        bits = ha.scan_pass(travel, self.keymap(), [0] * 5, 2)
        self.assertEqual(bits, [0, 0, 0b01, 0b10, 0])

    def test_a_skipped_key_id_consumes_a_travel_byte_but_sets_nothing(self):
        """The firmware advances the linear index before the skip test's
        target, so a skipped id still costs a sample."""
        keymap = self.keymap()
        keymap[0] = 0x00
        bits = ha.scan_pass([ha.ACTUATE_AT] * 10, keymap, [0] * 5, 2)
        self.assertEqual(bits[0], 0b10)

    def test_the_other_skipped_id_behaves_the_same(self):
        keymap = self.keymap()
        keymap[0] = 0xD3
        bits = ha.scan_pass([ha.ACTUATE_AT] * 10, keymap, [0] * 5, 2)
        self.assertEqual(bits[0], 0b10)

    def test_the_hold_band_leaves_a_pressed_bit_alone_across_a_pass(self):
        bits = ha.scan_pass([50] * 10, self.keymap(), [0b11] * 5, 2)
        self.assertEqual(bits, [0b11] * 5)

    def test_a_wrong_sized_previous_bitmap_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.scan_pass([0] * 10, self.keymap(), [0] * 4, 2)

    def test_an_active_count_past_the_group_stride_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.scan_pass([0] * 100, self.keymap(), [0] * 5,
                         ha.GROUP_STRIDE + 1)

    def test_running_off_the_key_map_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.scan_pass([0] * 100, [0x04] * 4, [0] * 5, 2)

    def test_running_off_the_travel_bytes_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.scan_pass([ha.ACTUATE_AT], self.keymap(), [0] * 5, 2)

    def test_a_zero_active_count_is_a_no_op(self):
        self.assertEqual(ha.scan_pass([], self.keymap(), [0b101] * 5, 0),
                         [0b101] * 5)


class EdgeDetector(unittest.TestCase):

    def test_the_xor_reports_only_changed_bits(self):
        self.assertEqual(ha.edge_words([0b1010] * 5, [0b1000] * 5),
                         [0b0010] * 5)

    def test_no_change_yields_zero(self):
        self.assertEqual(ha.edge_words([7] * 5, [7] * 5), [0] * 5)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(ha.ModelError):
            ha.edge_words([0] * 5, [0] * 4)


class Honesty(unittest.TestCase):

    def test_the_acquisition_stays_unresolved(self):
        finding, = [item for item in ha.FINDINGS
                    if item.key == "acquisition"]
        self.assertEqual(finding.confidence, "unresolved")
        self.assertIn("NOT RECOVERED", finding.statement)
        self.assertEqual(ha.to_dict()["pipeline"]["acquisition"], "unresolved")

    def test_calibration_and_filtering_stay_unresolved(self):
        pipeline = ha.to_dict()["pipeline"]
        self.assertEqual(pipeline["calibration"], "unresolved")
        self.assertEqual(pipeline["filtering"], "unresolved")

    def test_no_physical_interpretation_is_recorded(self):
        physical = ha.to_dict()["physical_interpretation"]
        self.assertIsNone(physical["recovered"])
        for word in ("polarity", "voltage", "noise", "distance", "scan rate"):
            self.assertIn(word, physical["note"])

    def test_no_physical_unit_is_attached_to_any_number(self):
        """Word boundaries matter here: a naive substring search for " mm"
        also matches "program model_hall_actuation"."""
        import re
        text = "\n".join(ha.report_lines()).lower()
        for unit in ("mm", "volts?", "hz", "millimet\\w*", "microns?",
                     "milliseconds?"):
            self.assertIsNone(re.search(rf"\\b\\d+\\s*{unit}\\b", text),
                              f"{unit!r} is attached to a number")
            self.assertIsNone(re.search(rf"\\bin\\s+{unit}\\b", text),
                              f"a quantity is expressed in {unit!r}")

    def test_the_model_authorises_no_hardware_action(self):
        self.assertIn("authorises NO custom-firmware Hall drive",
                      ha.to_dict()["authorisation"])
        self.assertIn("NO live experiment", ha.to_dict()["authorisation"])

    def test_every_finding_names_what_verified_it(self):
        for item in ha.FINDINGS:
            self.assertIn(item.verified_against,
                          ("listing", "decompiler", "bytes", "xref"), item.key)

    def test_the_load_bearing_constants_are_listing_verified(self):
        """The threshold and the geometry are what a replacement firmware
        would have to reproduce, so decompiler-only evidence is not enough."""
        for key in ("threshold", "hold_band", "skipped_ids", "geometry",
                    "actuation_clamp"):
            finding, = [item for item in ha.FINDINGS if item.key == key]
            self.assertEqual(finding.verified_against, "listing", key)


@unittest.skipUnless(READY, "Phase 3 match output not present")
class Relocation(unittest.TestCase):
    """Counterparts are looked up, never computed."""

    def test_the_two_functions_relocate_differently(self):
        matches = ha.measured_matches()
        self.assertEqual(matches[0x18004A7E][0], 0x18004A7E)
        self.assertEqual(matches[0x18005A88][0],
                         0x18005A88 - ha.RELOCATION_DELTA)

    def test_both_sit_above_the_insertion_point(self):
        """Which is exactly why the simple relocation rule is wrong here."""
        self.assertGreater(0x18004A7E, ha.INSERTION_POINT)
        self.assertGreater(0x18005A88, ha.INSERTION_POINT)

    def test_the_comparison_function_match_is_tentative(self):
        self.assertEqual(ha.measured_matches()[0x18004A7E][1], "tentative")

    def test_an_unmatched_application_address_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.vendor_address(0x18004A7F, "app")

    def test_data_addresses_use_the_flat_region_shift(self):
        self.assertEqual(ha.vendor_address(0x1801ED6C, "region"),
                         0x1801ED6C - ha.RELOCATION_DELTA)

    def test_an_unknown_image_raises(self):
        with self.assertRaises(ha.ModelError):
            ha.vendor_address(0x1000, "elsewhere")


@unittest.skipUnless(READY, "Phase 3 match output not present")
class Artifacts(unittest.TestCase):

    def test_every_check_passes(self):
        for item in ha.verify():
            self.assertTrue(item["ok"], item["name"])

    def test_json_is_deterministic(self):
        self.assertEqual(ha.bodies(), ha.bodies())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in ha.bodies().items()
                 if not (ha.NOTES / name).exists()
                 or (ha.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/model_hall_actuation.py --write")

    def test_the_json_parses_and_carries_the_boundary(self):
        payload = json.loads(ha.bodies()["hall-actuation.json"])
        self.assertEqual(payload["constants"]["actuate_at"], 100)
        self.assertIsNone(payload["physical_interpretation"]["recovered"])


if __name__ == "__main__":
    unittest.main()
