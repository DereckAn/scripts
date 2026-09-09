#!/usr/bin/env python3
"""Tests for the recovery key-combination analysis.

`Pure` runs anywhere. `Evidence` needs the preserved dumps and the Ghidra
slices and skips rather than passing when they are absent.

`AntiPromotion` is the group that matters. Two links in this chain are NOT
proven — the third key's name and the bootloader-to-application group
correspondence — and the temptation is to round the gate up to RESOLVED. The
tests below tie the gate's status to those residuals and require it to move
when either is claimed as settled.
"""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_recovery_keys as rk
import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and (rk.IMPORTS / rk.BOOT_BIN).exists()
         and (rk.IMPORTS / rk.APP_BIN).exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):

    def test_every_claim_carries_a_label_and_a_citation(self):
        for claim in rk.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_the_hid_table_is_the_published_one_where_it_matters(self):
        """Spot-check the usages the answer depends on."""
        self.assertEqual(rk.HID_USAGES[0x23], "6")
        self.assertEqual(rk.HID_USAGES[0x24], "7")
        self.assertEqual(rk.HID_USAGES[0x25], "8")
        self.assertEqual(rk.HID_USAGES[0xE0], "Left Control")
        self.assertEqual(rk.HID_USAGES[0xE4], "Right Control")
        self.assertEqual(rk.HID_USAGES[0xE6], "Right Alt")

    def test_the_digits_are_contiguous_from_1_to_0(self):
        """1..9 then 0 is the HID page's own ordering; a slip would rename
        the answer keys silently."""
        self.assertEqual([rk.HID_USAGES[0x1E + i] for i in range(10)],
                         ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"])

    def test_0xe8_is_not_in_the_hid_table(self):
        """It must stay unknown; adding a guessed name would defeat the point."""
        self.assertNotIn(0xE8, rk.HID_USAGES)
        self.assertIn("UNKNOWN", rk.name_for(0xE8))

    def test_the_unresolved_list_names_both_residuals(self):
        keys = {k for k, _ in rk.UNRESOLVED}
        self.assertIn("third_key_name", keys)
        self.assertIn("group_correspondence", keys)

    def test_no_device_vocabulary_in_the_tool(self):
        text = Path(rk.__file__).read_text().lower()
        for word in ("/dev/hidraw", "usb.core", "subprocess", "socket",
                     "urllib", "sudo", "spi_write", "bootloader_enter"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "mentions /dev/hidraw here")

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(rk, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(rk.main([]), 1)

    def test_a_missing_slice_fails_closed(self):
        with mock.patch.object(rk, "IMPORTS", Path("/nonexistent")):
            with self.assertRaises(rk.RecoveryKeyError):
                rk._load(rk.BOOT_BIN)

    def test_a_wrong_bootloader_hash_fails_closed(self):
        if not READY:
            self.skipTest("preserved slices absent")
        with mock.patch.object(rk, "BOOT_SHA", "0" * 64):
            with self.assertRaises(rk.RecoveryKeyError) as caught:
                rk.images()
            self.assertIn("unexpected", str(caught.exception))

    def test_the_pattern_decoder_is_pure_arithmetic(self):
        """0xa0 is bits 5 and 7; 0x100 is bit 8. Checked by construction."""
        self.assertEqual([b for b in range(15) if 0xA0 & (1 << b)], [5, 7])
        self.assertEqual([b for b in range(15) if 0x100 & (1 << b)], [8])


@unittest.skipUnless(READY, "preserved dumps or Ghidra slices absent")
class Evidence(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [c["label"] for c in rk.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} failed")

    def test_the_two_bootloader_slices_are_identical(self):
        self.assertEqual(rk._load(rk.BOOT_BIN), rk._load(rk.BOOT_MIRROR))

    def test_the_poll_constants_come_from_the_bootloader_bytes(self):
        poll = rk.poll_constants()
        self.assertTrue(poll["buffer_matches_log101"])
        self.assertEqual(poll["buffer"], "0x18012ac8")
        self.assertEqual(poll["consecutive_samples"], 31)

    def test_the_scan_drives_the_converter_not_gpio(self):
        """The question the whole answer turns on."""
        mech = rk.scan_mechanism()
        self.assertTrue(mech["all_three_present"])
        self.assertTrue(mech["matches_log119_trio"])
        self.assertEqual(mech["registers"]["strobe"], "0x4001b000")
        self.assertEqual(mech["registers"]["data_out"], "0x40018000")
        self.assertEqual(mech["registers"]["data_in"], "0x40019000")

    def test_the_primask_function_is_not_a_scan_enable(self):
        self.assertIn("msr primask", rk.scan_mechanism()["critical_section"])

    def test_the_pattern_decodes_to_three_pressed_positions(self):
        down = [(r["group"], r["position"])
                for r in rk.decode_pattern()["required_down"]]
        self.assertEqual(down, [(0, 5), (0, 7), (4, 8)])

    def test_the_modifier_rule_proves_the_codes_are_hid_usages(self):
        proof = rk.modifier_rule_proof()
        self.assertTrue(proof["subtracts_0xe0"])
        self.assertTrue(proof["compares_against_7"])
        self.assertTrue(proof["proves_hid_usages"])

    def test_two_keys_are_named_and_one_is_not(self):
        keys = rk.resolved_keys()
        down = [k for k in keys if k.get("state") != "must be UP"]
        named = [k["name"] for k in down if k["identity"] == "observed"]
        self.assertEqual(sorted(named), ["6", "8"])
        self.assertEqual([k["code"] for k in down
                          if k["identity"] == "unresolved"], ["0xe8"])

    def test_the_key_between_them_must_be_released(self):
        between = [k for k in rk.resolved_keys()
                   if k.get("state") == "must be UP"]
        self.assertEqual(len(between), 1)
        self.assertEqual(between[0]["name"], "7")

    def test_the_recovery_positions_are_variant_independent(self):
        var = rk.variant_masks()
        self.assertTrue(var["recovery_is_variant_independent"])
        self.assertEqual(var["recovery_positions_affected"], [])

    def test_the_delay_unit_is_microseconds(self):
        tim = rk.timing()
        self.assertEqual(tim["delay_divisor"], 1_000_000)
        self.assertEqual(tim["delay_unit"], "microseconds")
        self.assertEqual(tim["per_sample_us"], 1000)

    def test_the_poll_has_exactly_one_caller(self):
        """The prompt's second call site is a caller of the SCAN, not the
        poll. Recorded so the correction cannot quietly regress."""
        self.assertEqual(rk.timing()["callers_total"], 1)

    def test_the_poll_runs_before_the_other_boot_gates(self):
        self.assertIn("BEFORE all three remaining boot gates",
                      rk.timing()["position_in_boot"])

    def test_the_combination_is_physically_holdable(self):
        plaus = rk.plausibility()
        self.assertTrue(plaus["simultaneously_readable"])
        self.assertEqual(plaus["verdict"], "physically holdable")

    def test_reports_on_disk_are_current(self):
        payload = rk.bodies()
        stale = [n for n, b in payload.items()
                 if not (rk.NOTES / n).exists()
                 or (rk.NOTES / n).read_text() != b]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(rk.bodies()["recovery-keys.json"],
                         rk.bodies()["recovery-keys.json"])

    def test_the_report_states_no_device_was_accessed(self):
        self.assertIn("no device was accessed",
                      "\n".join(rk.report_lines()).lower())


@unittest.skipUnless(READY, "preserved dumps or Ghidra slices absent")
class AntiPromotion(unittest.TestCase):
    """The gate is PARTIAL, and it must stay PARTIAL while residuals stand."""

    def test_the_gate_is_partial_not_resolved(self):
        self.assertEqual(rk.to_dict()["gate_status"], "PARTIAL")

    def test_the_group_correspondence_is_never_reported_proven(self):
        corr = rk.group_correspondence()
        self.assertFalse(corr["proven"])
        self.assertFalse(corr["bootloader_holds_a_key_map"])
        self.assertTrue(corr["residual"].strip())
        self.assertTrue(corr["what_would_settle_it"].strip())

    def test_the_corroboration_is_real_and_could_fail(self):
        """The 'D' mask landing on non-keys depends on the group permutation,
        so it is evidence rather than decoration. If the key map ever changes
        so that a real key sits there, this must fail."""
        corr = rk.group_correspondence()
        depends = [c for c in corr["corroboration"]
                   if "DOES depend on the group permutation" in c["strength"]]
        self.assertEqual(len(depends), 1)
        self.assertTrue(depends[0]["holds"])

    def test_the_third_key_is_never_named_in_the_claims(self):
        """Fn may appear as an explicit inference, never as the answer."""
        answer, = [c for c in rk.CLAIMS if c.key == "keys"]
        self.assertNotIn("Fn", answer.answer)
        third, = [c for c in rk.CLAIMS if c.key == "third_key"]
        self.assertEqual(third.confidence, "strongly-inferred")
        self.assertIn("Not resolved by name", third.answer)

    def test_the_third_key_inference_is_not_vacuous(self):
        self.assertIn("Fn", "a sentence naming the Fn key")

    def test_naming_the_third_key_would_have_to_change_the_gate(self):
        """If 0xe8 were ever added to the usage table, the resolved-keys view
        must stop reporting it unresolved — proving the status is computed
        from the evidence and not hard-coded."""
        with mock.patch.dict(rk.HID_USAGES, {0xE8: "Fn"}):
            keys = rk.resolved_keys()
            unresolved = [k for k in keys if k["identity"] == "unresolved"]
        self.assertEqual(unresolved, [])
        # and without the patch it is unresolved again
        self.assertTrue(any(k["identity"] == "unresolved"
                            for k in rk.resolved_keys()))

    def test_no_claim_promises_a_working_recovery_procedure(self):
        blob = " ".join(c.answer.lower() for c in rk.CLAIMS)
        for phrase in ("will enter recovery", "guaranteed", "simply hold",
                       "this recovers the device", "proven to work"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_procedure_detector_is_not_vacuous(self):
        self.assertIn("guaranteed", "a sentence saying guaranteed")

    def test_the_absolute_window_is_not_overclaimed(self):
        """The delays are ~200 ms but the scan time is unmeasured, so no
        total may be stated as if it were bounded."""
        tim = rk.timing()
        self.assertIn("not bounded here", tim["practical_consequence"])
        self.assertIn("longer than 200 ms", tim["practical_consequence"])


if __name__ == "__main__":
    unittest.main()
