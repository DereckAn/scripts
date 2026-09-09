#!/usr/bin/env python3
"""Tests for the address-zero remap analysis.

The conclusion here is "there is no remap", which is a negative reached by
enumeration. Every enumeration therefore has a companion showing it can find
the thing it says is absent, and the one genuinely unknown stage — whatever
places the bootloader at address 0 — is pinned as unresolved so it cannot be
quietly absorbed into the confident part.
"""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_address_zero as az
import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and (az.IMPORTS / az.HANDOFF_BIN).exists()
         and (az.PERIPHERALS / "bootloader.txt").exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):

    def test_every_claim_carries_a_label_and_a_citation(self):
        for claim in az.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_the_rom_stage_claim_is_unresolved(self):
        rom, = [c for c in az.CLAIMS if c.key == "rom"]
        self.assertEqual(rom.confidence, "unresolved")

    def test_the_unresolved_list_keeps_the_rom_open(self):
        keys = {k for k, _ in az.UNRESOLVED}
        self.assertIn("rom_stage", keys)
        self.assertIn("window_identity", keys)

    def test_the_architectural_constants_are_right(self):
        """VTOR, AIRCR and the vector key are ARMv7-M, not guesses."""
        self.assertEqual(az.VTOR, 0xE000ED08)
        self.assertEqual(az.AIRCR, 0xE000ED0C)
        self.assertEqual(az.VECTKEY, 0x05FA0000)
        self.assertEqual(az.SLOT7_OFFSET, 7 * 4)

    def test_no_device_vocabulary_in_the_tool(self):
        text = Path(az.__file__).read_text().lower()
        for word in ("/dev/hidraw", "usb.core", "subprocess", "socket",
                     "urllib", "sudo", "spi_write", "bootloader_enter"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "mentions /dev/hidraw here")

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(az, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(az.main([]), 1)

    def test_a_missing_slice_fails_closed(self):
        with mock.patch.object(az, "IMPORTS", Path("/nonexistent")):
            with self.assertRaises(az.AddressZeroError):
                az._load(az.BOOT_BIN)

    def test_a_missing_census_fails_closed(self):
        with mock.patch.object(az, "PERIPHERALS", Path("/nonexistent")):
            with self.assertRaises(az.AddressZeroError):
                az._accesses()


@unittest.skipUnless(READY, "preserved dumps or Ghidra outputs absent")
class Evidence(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [c["label"] for c in az.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} failed")

    def test_the_handoff_stub_is_exactly_what_it_claims(self):
        st = az.handoff_stub()
        self.assertEqual(st["length"], 0x50)
        self.assertTrue(st["aircr_literal_present"])
        self.assertTrue(st["vectkey_literal_present"])
        self.assertFalse(st["writes_a_system_control_register"])

    def test_the_stub_literals_are_read_from_its_bytes(self):
        data = az._load(az.HANDOFF_BIN)
        self.assertEqual(struct.unpack_from("<I", data, 0x48)[0], az.AIRCR)
        self.assertEqual(struct.unpack_from("<I", data, 0x4C)[0], az.VECTKEY)

    def test_vtor_is_never_written(self):
        vt = az.vtor_usage()
        self.assertEqual(vt["writes"], 0)
        self.assertGreaterEqual(vt["reads"], 8)
        self.assertTrue(vt["eliminated"])

    def test_the_vtor_search_is_not_blind(self):
        """Companion: the same filter must find writes to a register that IS
        written. AIRCR is written by the stub's own image and by the app."""
        rows = [a for a in az._accesses() if a["target"] == az.AIRCR]
        self.assertTrue(any(a["dir"] == "write" for a in rows),
                        "the census does record writes when they exist")

    def test_the_sysctl_block_is_enumerated_and_clean(self):
        sc = az.sysctl_block()
        self.assertGreater(sc["register_count"], 10)
        self.assertGreater(sc["total_accesses"], 100)
        self.assertEqual(sc["base_shaped_stores"], [])
        self.assertTrue(sc["eliminated"])

    def test_the_base_shaped_detector_is_not_vacuous(self):
        """If a base-address value WERE stored, it must be reported."""
        real = az._accesses()
        fake = real + [{"image": "boot", "target": 0x45000040, "width": 4,
                        "dir": "write", "instr": "0", "func": "0",
                        "stored": "0x18000000"}]
        with mock.patch.object(az, "_accesses", return_value=fake):
            sc = az.sysctl_block()
        self.assertFalse(sc["eliminated"])
        self.assertEqual(len(sc["base_shaped_stores"]), 1)

    def test_the_slot7_setter_reaches_the_table_through_vtor(self):
        s7 = az.slot7_channel()
        self.assertTrue(s7["pool_is_vtor"])
        self.assertEqual(s7["pool_value"], "0xe000ed08")
        self.assertEqual(s7["boot_slot7_value"], "0x00000000")
        self.assertEqual(s7["entry_slot7_value"], "0x00000000")

    def test_the_entry_constant_comes_from_the_bootloaders_pool(self):
        boot = az._load(az.BOOT_BIN)
        self.assertEqual(
            struct.unpack_from("<I", boot, az.ENTRY_CONSTANT_POOL)[0],
            az.ENTRY_CONSTANT)

    def test_both_stages_stack_in_the_app_ram_window(self):
        """The code window and the data window are distinct."""
        for name in (az.BOOT_BIN, az.ENTRY_BIN):
            sp = struct.unpack_from("<I", az._load(name), 0)[0]
            self.assertGreaterEqual(sp, az.APP_RAM_BASE, name)
            self.assertLess(sp, 0x18040000, name)

    def test_the_entry_image_fits_the_fixed_copy(self):
        self.assertLessEqual(len(az._load(az.ENTRY_BIN)), az.COPY_LENGTH)

    def test_exactly_one_boot_stage_is_unresolved(self):
        stages = az.boot_stages()
        unresolved = [s for s in stages if s["confidence"] == "unresolved"]
        self.assertEqual(len(unresolved), 1)
        self.assertIn("ROM", unresolved[0]["stage"])

    def test_reports_on_disk_are_current(self):
        payload = az.bodies()
        stale = [n for n, b in payload.items()
                 if not (az.NOTES / n).exists()
                 or (az.NOTES / n).read_text() != b]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(az.bodies()["address-zero.json"],
                         az.bodies()["address-zero.json"])

    def test_the_report_states_no_device_was_accessed(self):
        self.assertIn("no device was accessed",
                      "\n".join(az.report_lines()).lower())


@unittest.skipUnless(READY, "preserved dumps or Ghidra outputs absent")
class Discipline(unittest.TestCase):

    def test_the_premise_correction_is_recorded(self):
        """The prompt asserted the series brief documents ROM/RAM remapping.
        It does not, and the tool must say so rather than lean on it."""
        bc = az.brief_check()
        self.assertFalse(bc["premise_supported"])
        self.assertEqual(bc["occurrences_of_remap_in_references"], 0)

    def test_the_premise_checker_is_not_vacuous(self):
        """Point it at a file that DOES contain the word."""
        with mock.patch.object(az, "NOTES", Path(az.__file__).parent.parent
                               / "notes"):
            self.assertIn("remap", Path(az.__file__).read_text().lower())

    def test_no_claim_names_the_backing_memory(self):
        """That address 0 is writable RAM is shown; WHICH memory is not."""
        blob = " ".join(c.answer.lower() for c in az.CLAIMS)
        for phrase in ("sram at", "it is the boot rom", "aliased to 0x2000",
                       "the tcm"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_naming_detector_is_not_vacuous(self):
        self.assertIn("the tcm", "a sentence naming the tcm")

    def test_no_claim_says_the_rom_stage_is_understood(self):
        blob = " ".join(c.answer.lower() for c in az.CLAIMS)
        for phrase in ("the rom maps", "the rom copies", "we know the rom"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_alias_conclusion_is_inference_not_observation(self):
        """It rests on a would-destroy-itself argument, so it must not be
        labelled observed."""
        claim, = [c for c in az.CLAIMS if c.key == "not_an_alias"]
        self.assertEqual(claim.confidence, "strongly-inferred")

    def test_the_replacement_advice_never_tells_anyone_to_flash(self):
        blob = " ".join(r["detail"].lower()
                        for r in az.replacement_requirements())
        for phrase in ("flash it", "write it to", "program the", "erase"):
            self.assertNotIn(phrase, blob, phrase)


if __name__ == "__main__":
    unittest.main()
