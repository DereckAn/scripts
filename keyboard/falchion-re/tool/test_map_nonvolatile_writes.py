#!/usr/bin/env python3
"""Offline tests for the Phase 5E nonvolatile write map.

Most of these guard the model's honesty rather than arithmetic. Phase 5E traced
the commit path to a DMA setup and stopped: the storage medium is unidentified
and the settings format was never recovered. A later edit that quietly named the
medium from an opcode it merely recognised, or that claimed a format field, is
the failure mode that matters — as is anything that turns this read-only module
into something that can emit a command. No device access, no writes outside a
temporary directory.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_nonvolatile_writes as nv

READY = nv.MATCH_APP.exists()


class NeverTransmits(unittest.TestCase):
    """This phase reads code. It must stay unable to speak to the device."""

    def test_the_module_exposes_no_encoder_or_transmitter(self):
        for name in dir(nv):
            self.assertFalse(name.startswith(("build_", "send_", "encode_",
                                              "transmit_", "emit_")),
                             f"{name} looks like a command constructor")

    def test_the_commit_bytes_never_appear_as_a_packet(self):
        """0x50 and 0x55 are traced as values the firmware COMPARES against.
        They must not appear anywhere as an adjacent pair that could be read
        as a ready-made packet."""
        payload = json.dumps(nv.to_dict())
        self.assertNotIn("PQU", payload)          # b"\\x50\\x55" as ascii
        self.assertNotIn("[80, 85]", payload)
        self.assertNotIn("0x5055", payload)

    def test_the_report_says_it_never_speaks_to_the_device(self):
        text = "\n".join(nv.report_lines())
        self.assertIn("never speaks to the device", text)


class ModelHonesty(unittest.TestCase):

    def test_the_storage_medium_stays_unidentified(self):
        medium = nv.to_dict()["storage_medium"]
        self.assertFalse(medium["identified"])
        self.assertIn("recognition and not proof", medium["note"])

    def test_the_opcodes_are_recorded_as_recognition_not_identification(self):
        for note in nv.OPCODES.values():
            self.assertTrue(note.startswith("matches the JEDEC"), note)
        self.assertNotIn("is the JEDEC", " ".join(nv.OPCODES.values()))

    def test_no_settings_format_field_is_claimed(self):
        fmt = nv.to_dict()["settings_format"]
        for field in ("magic", "version", "length", "checksum", "defaults",
                      "migration"):
            self.assertIsNone(fmt[field], field)
        self.assertIn("NOT RECOVERED", fmt["note"])

    def test_the_dispatch_answer_is_queueing(self):
        answer = nv.to_dict()["answer_to_the_dispatch_question"]
        self.assertEqual(answer["choice"], "b")
        self.assertIn("no call instruction", answer["detail"])

    def test_the_exit_gate_is_the_negative_branch(self):
        gate = nv.to_dict()["exit_gate"]
        self.assertEqual(gate["branch"], "omit-all-writes")
        self.assertIn("cannot be implemented from this evidence", gate["detail"])
        self.assertGreaterEqual(
            len(gate["what_a_custom_firmware_must_never_do"]), 4)

    def test_the_never_do_list_names_the_two_gates(self):
        items = " ".join(
            nv.to_dict()["exit_gate"]["what_a_custom_firmware_must_never_do"])
        self.assertIn(f"0x{nv.COMMAND_BYTE:08x}", items)
        self.assertIn(f"0x{nv.REQUEST_STRUCT:08x}", items)

    def test_the_unresolved_steps_stay_unresolved(self):
        medium, = [step for step in nv.STEPS if step.key == "medium"]
        self.assertEqual(medium.confidence, "unresolved")
        hop, = [item for item in nv.HOPS if item.target == "medium"]
        self.assertEqual(hop.confidence, "unresolved")

    def test_the_asynchronous_hop_is_not_claimed_as_observed(self):
        """Nothing established which context runs the state machine."""
        hop, = [item for item in nv.HOPS
                if item.source == "command_byte"]
        self.assertEqual(hop.confidence, "strongly-inferred")
        self.assertIn("callerless", hop.kind_basis)

    def test_the_load_bearing_steps_are_listing_verified(self):
        for key in ("commit_request", "command_byte", "erase_64k",
                    "erase_32k", "busy_check", "dma_setup"):
            step, = [item for item in nv.STEPS if item.key == key]
            self.assertEqual(step.verified_against, "listing", key)

    def test_every_confidence_is_from_the_closed_set(self):
        for item in list(nv.STEPS) + list(nv.HOPS) + list(nv.MODIFIABLE_RANGES):
            self.assertIn(item.confidence, nv.CONFIDENCES)


class Ranges(unittest.TestCase):

    def test_no_target_overlaps_the_bootloader_application_region(self):
        """The bootloader writes 0x10000..0x7c000. These targets start at
        0x320000, so the commit path and the firmware region are disjoint."""
        for item in nv.MODIFIABLE_RANGES:
            self.assertFalse(
                nv.reaches_bootloader_region(item.low, item.high),
                f"0x{item.low:x}")

    def test_the_overlap_helper_actually_detects_an_overlap(self):
        """A predicate that always returns False would pass the test above."""
        self.assertTrue(nv.reaches_bootloader_region(0x20000, 0x30000))
        self.assertTrue(nv.reaches_bootloader_region(0x0, 0x11000))
        self.assertFalse(nv.reaches_bootloader_region(0x7C000, 0x80000))
        self.assertFalse(nv.reaches_bootloader_region(0x0, 0x10000))

    def test_the_slot_range_is_bounded_by_a_byte_index(self):
        slot, = [item for item in nv.MODIFIABLE_RANGES
                 if "computed slot" in item.label]
        self.assertEqual(slot.high - slot.low, 256 * nv.SLOT_STRIDE)
        self.assertIn("byte", slot.kind_basis)

    def test_the_extent_caveat_is_recorded_on_every_erase_range(self):
        for item in nv.MODIFIABLE_RANGES[:3]:
            self.assertIn("extent", item.kind_basis.lower())


@unittest.skipUnless(READY, "Phase 3 match output not present")
class Counterparts(unittest.TestCase):

    def test_function_steps_are_looked_up(self):
        for step in nv.STEPS:
            if step.kind != "function":
                continue
            address, how = nv.counterpart(step)
            self.assertIsNotNone(address, step.key)
            self.assertTrue(how.startswith("matched"), step.key)

    def test_data_steps_take_the_flat_shift(self):
        for step in nv.STEPS:
            if step.kind != "data":
                continue
            address, how = nv.counterpart(step)
            self.assertEqual(address, step.address - nv.RELOCATION_DELTA)
            self.assertEqual(how, "flat region shift")

    def test_a_code_address_claims_no_counterpart(self):
        step, = [item for item in nv.STEPS if item.kind == "code"]
        address, how = nv.counterpart(step)
        self.assertIsNone(address)
        self.assertEqual(how, "not separately measured")

    def test_an_unmatched_function_address_raises(self):
        with self.assertRaises(nv.WriteMapError):
            nv.vendor_of(0x18004A7F)

    def test_a_known_function_resolves(self):
        self.assertEqual(nv.vendor_of(0x18001FBE)[0],
                         nv.measured_matches()[0x18001FBE][0])


@unittest.skipUnless(READY, "Phase 3 match output not present")
class Artifacts(unittest.TestCase):

    def test_every_check_passes(self):
        for item in nv.verify():
            self.assertTrue(item["ok"], item["name"])

    def test_json_is_deterministic(self):
        self.assertEqual(nv.bodies(), nv.bodies())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in nv.bodies().items()
                 if not (nv.NOTES / name).exists()
                 or (nv.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/map_nonvolatile_writes.py --write")

    def test_the_report_states_both_limitations(self):
        text = "\n".join(nv.report_lines())
        self.assertIn("recognition, not proof", text)
        self.assertIn("callerless in the application call graph", text)

    def test_a_missing_match_file_fails_closed(self):
        original = nv.MATCH_APP
        with tempfile.TemporaryDirectory() as directory:
            nv.MATCH_APP = Path(directory) / "absent.json"
            try:
                with self.assertRaises(OSError):
                    nv.measured_matches()
            finally:
                nv.MATCH_APP = original


if __name__ == "__main__":
    unittest.main()
