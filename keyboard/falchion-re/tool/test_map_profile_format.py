#!/usr/bin/env python3
"""Offline tests for the settings / profile format map.

Three jobs, in order of how badly a regression would hurt.

FAIL-CLOSED. Every input is gated: both preserved dumps by hash, each imported
slice by the hash its own filename claims, and the Armoury Crate decode by
existence. A missing or swapped input must raise, not quietly produce a map
against the wrong bytes.

NEVER TRANSMITS. This phase recovered a payload format. A module that could
also build a frame would be one edit away from writing the device, so the
persistence command's bytes must not appear in the model at all and no name may
look like a constructor.

HONESTY. The format is recovered; the storage medium is not, polling rate
matched nothing, and two runs of the profile block were never decoded. The
failure mode that matters is a later edit that quietly upgrades one of those.
The match table is also guarded from the opposite direction: several checks
break a backing byte and require the corresponding check to go red, so a table
that agrees with the decode by construction rather than by evidence fails.

No device access, no writes outside a temporary directory.
"""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_profile_format as pf

READY = (pf.IMPORTS / pf.APP_BIN).exists() and (pf.NOTES
                                                / "ac-profile3-decoded.json").exists()


def checks():
    return {c["label"]: c["ok"] for c in pf.verify()}


class NeverTransmits(unittest.TestCase):

    def test_no_name_looks_like_a_command_constructor(self):
        for name in dir(pf):
            self.assertFalse(name.startswith(("build_", "send_", "encode_",
                                              "transmit_", "emit_")),
                             f"{name} looks like a command constructor")

    @unittest.skipUnless(READY, "evidence slices absent")
    def test_the_persistence_command_bytes_are_absent_from_the_model(self):
        payload = json.dumps(pf.to_dict())
        for shape in ("PQU", "[80, 85]", "0x5055", "50 55", "0x50/0x55"):
            self.assertNotIn(shape, payload, shape)

    @unittest.skipUnless(READY, "evidence slices absent")
    def test_the_report_says_it_never_speaks_to_the_device(self):
        self.assertIn("never speaks to the device",
                      "\n".join(pf.report_lines()))


class FailClosed(unittest.TestCase):

    def test_a_missing_slice_raises(self):
        with self.assertRaises(pf.ProfileFormatError):
            pf._load("not-a-real-slice_00000000.bin")

    def test_a_slice_whose_bytes_contradict_its_name_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            name = "fake_slice_deadbeef.bin"
            (Path(tmp) / name).write_bytes(b"\x00" * 16)
            with mock.patch.object(pf, "IMPORTS", Path(tmp)):
                with self.assertRaises(pf.ProfileFormatError) as ctx:
                    pf._load(name)
        self.assertIn("deadbeef", str(ctx.exception))

    def test_a_slice_whose_bytes_match_its_name_loads(self):
        """Anti-vacuity: the gate above must be passable."""
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            data = b"\x00" * 16
            tag = hashlib.sha256(data).hexdigest()[:8]
            name = f"fake_slice_{tag}.bin"
            (Path(tmp) / name).write_bytes(data)
            with mock.patch.object(pf, "IMPORTS", Path(tmp)):
                self.assertEqual(pf._load(name), data)

    def test_an_out_of_range_read_raises(self):
        with self.assertRaises(pf.ProfileFormatError):
            pf._b((b"\x00" * 4, 0x1000), 0x2000, 1)

    def test_a_missing_armoury_crate_decode_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(pf, "NOTES", Path(tmp)):
                with self.assertRaises(pf.ProfileFormatError):
                    pf.ac_profile()

    def test_main_reports_the_failure_without_a_traceback(self):
        with mock.patch.object(pf, "bodies",
                               side_effect=pf.ProfileFormatError("boom")):
            self.assertEqual(pf.main([]), 1)

    @unittest.skipUnless(READY, "evidence slices absent")
    def test_check_mode_is_red_against_an_empty_notes_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(pf, "NOTES", Path(tmp)):
                # ac_profile() also reads NOTES, so bodies() fails closed here.
                self.assertEqual(pf.main(["--check"]), 1)


class TheChecksumModel(unittest.TestCase):
    """The checksum is executable, so the tests run it."""

    def test_it_is_an_additive_sum_and_not_a_crc(self):
        self.assertEqual(pf.sum16(b"\x01\x02\x03"), 6)
        self.assertEqual(pf.sum16(b""), 0)

    def test_it_wraps_at_sixteen_bits(self):
        self.assertEqual(pf.sum16(b"\xff" * 0x101), 0xFFFF)      # exactly full
        self.assertEqual(pf.sum16(b"\xff" * 0x102), 0x00FE)      # one past

    def test_it_is_order_insensitive_which_a_crc_is_not(self):
        self.assertEqual(pf.sum16(b"\x01\x02"), pf.sum16(b"\x02\x01"))

    def test_the_stamp_binds_a_block_to_its_profile_slot(self):
        raw = 0xABCF
        self.assertEqual(pf.checksum_a_stamp(raw, 3), 0xABC3)
        self.assertNotEqual(pf.checksum_a_stamp(raw, 3),
                            pf.checksum_a_stamp(raw, 4))

    def test_the_stamp_is_a_mask_and_never_adds_bits(self):
        for profile in range(pf.PROFILES):
            self.assertEqual(pf.checksum_a_stamp(0x0000, profile), 0)


class TheOpcodeDecoder(unittest.TestCase):

    def test_it_finds_the_movs_strb_idiom(self):
        body = struct.pack("<HH", 0x2403, 0x701C)      # movs r4,#3; strb r4,[r3]
        self.assertEqual(pf.opcode_store(body), (0, 4, 3))

    def test_it_ignores_a_movs_that_is_not_followed_by_a_byte_store(self):
        body = struct.pack("<HH", 0x2403, 0x6158)      # movs r4,#3; str r0,[r3,#0x14]
        self.assertIsNone(pf.opcode_store(body))

    def test_it_ignores_a_store_of_a_different_register(self):
        body = struct.pack("<HH", 0x2403, 0x701D)      # strb r5, not r4
        self.assertIsNone(pf.opcode_store(body))

    def test_it_finds_nothing_in_bytes_without_the_idiom(self):
        self.assertIsNone(pf.opcode_store(b"\x00" * 0x20))


@unittest.skipUnless(READY, "evidence slices absent")
class TheLayoutIsArithmeticallyClosed(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [label for label, ok in checks().items() if not ok]
        self.assertEqual(failed, [])

    def test_the_lighting_slots_tile_the_gap_exactly(self):
        _, end = pf.light_slots()
        self.assertEqual(end, pf.KEYTABLE_OFFSET)

    def test_a_wrong_slot_size_breaks_the_tiling_check(self):
        """Anti-vacuity: the tiling check must be able to fail."""
        broken = ((0, 16),) + pf.LIGHT_SLOTS[1:]
        with mock.patch.object(pf, "LIGHT_SLOTS", broken):
            self.assertFalse(
                checks()["the ten lighting slots exactly fill the gap before "
                         "the key tables"])

    def test_the_runtime_blocks_are_contiguous(self):
        d = pf.to_dict()
        by_name = {b["name"]: b for b in d["runtime_blocks"]}
        for a, b in (("keymap_layer0", "keymap_layer1"),
                     ("keymap_layer1", "profile_block"),
                     ("profile_block", "macro_block")):
            self.assertEqual(by_name[a]["address"] + by_name[a]["size"],
                             by_name[b]["address"], f"{a} -> {b}")

    def test_the_stored_regions_do_not_overlap_each_other(self):
        regions = pf.stored_map()
        for i, a in enumerate(regions):
            for b in regions[i + 1:]:
                self.assertTrue(a["hi"] <= b["lo"] or b["hi"] <= a["lo"],
                                f"{a['name']} vs {b['name']}")

    def test_every_primitive_opcode_is_decoded_and_distinct(self):
        prims = pf.primitives()
        self.assertEqual(len(prims), 6)
        self.assertTrue(all(p["opcode_matches_expected"] for p in prims))
        self.assertEqual(len({p["opcode"] for p in prims}), 6)


@unittest.skipUnless(READY, "evidence slices absent")
class TheRosettaMatchesComeFromBytes(unittest.TestCase):
    """The two exact colour/effect matches must come from the image, not the
    table. Each test moves the bytes and requires the match to break."""

    def test_the_profile_three_colour_is_read_from_the_image(self):
        rom = pf.rom_defaults()
        self.assertEqual(rom["colour_per_profile"][3], [0, 0, 255])

    def test_pointing_the_colour_table_elsewhere_breaks_the_match(self):
        with mock.patch.object(pf, "ROM_COLOUR_TABLE",
                               pf.ROM_COLOUR_TABLE + 3):
            self.assertFalse(
                checks()["the ROM colour for profile 3 equals the decode's "
                         "single colour"])

    def test_the_profile_three_lighting_slot_is_read_from_the_image(self):
        self.assertEqual(pf.rom_defaults()["light_slot_per_profile"][3], 8)

    def test_pointing_the_slot_table_elsewhere_breaks_the_match(self):
        with mock.patch.object(pf, "ROM_LIGHT_SLOT", pf.ROM_LIGHT_SLOT + 1):
            self.assertFalse(
                checks()["the ROM lighting slot for profile 3 equals the "
                         "decode's effectID"])

    def test_the_decode_really_is_the_profile_three_snapshot(self):
        self.assertEqual(pf.AC_PROFILE_INDEX, 3)
        self.assertEqual(pf.ac_profile()["lighting"]["keyboard"]["effectID"],
                         "8")

    def test_the_wear_levelled_descriptors_come_from_the_region_image(self):
        groups = pf.small_store()
        self.assertEqual([g["bank_a"] for g in groups], [0x1C000, 0x1E000])
        self.assertEqual([g["item_count"] for g in groups], [3, 1])


@unittest.skipUnless(READY, "evidence slices absent")
class ModelHonesty(unittest.TestCase):

    def test_the_storage_medium_is_still_unresolved(self):
        keys = {u["key"] for u in pf.unresolved()}
        self.assertIn("storage_medium", keys)
        text = " ".join(u["detail"] for u in pf.unresolved())
        self.assertIn("not identified", text)

    def test_no_flash_part_or_bus_is_named(self):
        payload = json.dumps(pf.to_dict()).lower()
        for word in ("spi nor", "zb25", "jedec", "winbond", "quad spi"):
            self.assertNotIn(word, payload, word)

    def test_the_checksum_is_never_called_a_crc(self):
        payload = json.dumps(pf.to_dict()).lower()
        self.assertNotIn("crc", payload.replace("not a crc", ""))

    def test_polling_rate_stays_unmatched(self):
        row = next(m for m in pf.matches()
                   if m.ac_field == "performance.pollingRate")
        self.assertEqual(row.confidence, "unmatched")

    def test_the_match_table_leaves_several_fields_unmatched(self):
        unmatched = [m.ac_field for m in pf.matches()
                     if m.confidence == "unmatched"]
        self.assertGreaterEqual(len(unmatched), 3, unmatched)

    def test_every_match_row_carries_evidence_and_a_known_confidence(self):
        for m in pf.matches():
            self.assertTrue(m.evidence, m.ac_field)
            self.assertIn(m.confidence, ("exact", "structural", "unmatched"))

    def test_the_undecoded_runs_are_recorded_as_undecoded(self):
        layout = {f["name"]: f for f in pf.profile_layout()}
        for name in ("region_b", "tail", "pair_4b0"):
            self.assertEqual(layout[name]["confidence"], "unresolved", name)

    def test_the_two_readings_of_the_function_index_are_both_kept(self):
        row = next(m for m in pf.matches()
                   if m.ac_field == "lever.currentFunctionId")
        self.assertIn("neither is chosen", row.note)
        self.assertEqual(row.confidence, "structural")

    def test_the_numeric_overlap_with_the_application_region_is_recorded(self):
        text = " ".join(u["detail"] for u in pf.unresolved())
        self.assertIn("does NOT generalise", text)
        self.assertIn("0x10000..0x7c000", text)

    def test_calibration_stays_the_only_ram_only_section(self):
        ram_only = [p["section"] for p in pf.persistence()
                    if p["verdict"] == "RAM-only"]
        self.assertEqual(ram_only, ["per-key Hall calibration"])

    def test_lighting_keymaps_and_performance_are_all_proven_persisted(self):
        verdicts = {p["section"]: p["verdict"] for p in pf.persistence()}
        for section in ("lighting", "key mappings",
                        "performance (actuation, rapid trigger)"):
            self.assertEqual(verdicts[section], "persisted", section)

    def test_the_host_answer_confirms_and_corrects(self):
        self.assertIn("CORRECT in substance", pf.HOST_INDEPENDENCE)
        self.assertIn("imprecise", pf.HOST_INDEPENDENCE)
        self.assertIn("0x2000", pf.HOST_INDEPENDENCE)


@unittest.skipUnless(READY, "evidence slices absent")
class Reports(unittest.TestCase):

    def test_write_then_check_is_current(self):
        decode = (pf.NOTES / "ac-profile3-decoded.json").read_bytes()
        payload = pf.bodies()
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in payload.items():
                (Path(tmp) / name).write_text(body)
            # ac_profile() reads NOTES too, so the decode has to come along.
            (Path(tmp) / "ac-profile3-decoded.json").write_bytes(decode)
            with mock.patch.object(pf, "NOTES", Path(tmp)):
                self.assertEqual(pf.main(["--check"]), 0)

    def test_the_markdown_names_every_stored_region(self):
        md = pf.markdown()
        for region in pf.stored_map():
            self.assertIn(region["name"], md)

    def test_the_json_and_markdown_come_from_one_model(self):
        d = pf.to_dict()
        md = pf.markdown()
        self.assertIn(d["answer_to_the_host_question"], md)
        for row in d["armoury_crate_matches"]:
            self.assertIn(row["ac_field"], md)


if __name__ == "__main__":
    unittest.main()
