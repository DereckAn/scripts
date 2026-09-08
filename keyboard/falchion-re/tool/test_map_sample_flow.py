#!/usr/bin/env python3
"""Tests for the mailbox sample-flow trace.

`Pure` runs anywhere. `Evidence` needs the preserved dumps and the Ghidra
slices, and skips rather than passing when they are absent.

The important group is `AntiPromotion`. Log 118 forbade the words "gate is
closed" outright, because the path was incomplete. This step completes it, so
the wording is now permitted — but only while the evidence holds it up. The
tests below tie the conclusion to `path_complete()` and then break each
supporting fact in turn to show the conclusion actually moves. A conclusion
that cannot be falsified by breaking its own evidence is not a conclusion.
"""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_sample_flow as sf
import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and (sf.IMPORTS / sf.ENTRY_BIN).exists()
         and (sf.IMPORTS / sf.APP_BIN).exists()
         and (sf.IMPORTS / sf.REGION_BIN).exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):

    def test_the_movw_encoder_matches_log113s_validated_bytes(self):
        """The one veneer that was decoded by hand before any tool existed."""
        self.assertTrue(sf.movw_self_test())
        hw = sf.movw_halfwords(sf.START_ROUTINE | 1, 12)
        self.assertEqual(struct.pack("<HH", *hw), sf.START_VENEER_BYTES)

    def test_the_movw_encoder_is_not_vacuous(self):
        """A different immediate must produce different bytes."""
        self.assertNotEqual(sf.movw_halfwords(0x1F51, 12),
                            sf.movw_halfwords(0x1F52, 12))
        self.assertNotEqual(sf.movw_halfwords(0x1F51, 12),
                            sf.movw_halfwords(0x1F51, 11))

    def test_the_branch_decoder_round_trips_a_known_encoding(self):
        """b.w with a small positive displacement, checked by construction."""
        buf = struct.pack("<HH", 0xF000, 0xB806)      # b.w +0x10
        got = sf.decode_branch(buf, 0x1000, 0x1000)
        self.assertEqual(got, ("b.w", 0x1010))

    def test_the_branch_decoder_rejects_non_branches(self):
        self.assertIsNone(sf.decode_branch(struct.pack("<HH", 0x4770, 0x0000),
                                           0, 0))

    def test_every_claim_carries_a_label_and_a_citation(self):
        for claim in sf.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_every_path_link_cites_something(self):
        for link in sf.PATH:
            self.assertTrue(link.citation.strip(), link.key)
            self.assertTrue(link.detail.strip(), link.key)

    def test_the_unresolved_list_keeps_the_rate_open(self):
        keys = {k for k, _ in sf.UNRESOLVED}
        self.assertIn("absolute_rate", keys)
        self.assertIn("unresolved_accesses", keys)

    def test_no_device_vocabulary_in_the_tool(self):
        text = Path(sf.__file__).read_text().lower()
        for word in ("/dev/hidraw", "usb.core", "subprocess", "socket",
                     "urllib", "sudo", "spi_write", "bootloader_enter"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "mentions /dev/hidraw here")

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(sf, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(sf.main([]), 1)

    def test_a_missing_slice_fails_closed(self):
        with mock.patch.object(sf, "IMPORTS", Path("/nonexistent")):
            with self.assertRaises(sf.SampleFlowError):
                sf._load(sf.ENTRY_BIN)


@unittest.skipUnless(READY, "preserved dumps or Ghidra slices absent")
class Evidence(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [c["label"] for c in sf.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} failed")

    def test_the_branch_decoder_agrees_with_ghidra(self):
        self.assertTrue(sf.branch_self_test())

    def test_every_client_has_a_veneer(self):
        for row in sf.veneers():
            self.assertTrue(row["found"], row["client"])

    def test_each_clients_opcode_is_in_its_own_bytes(self):
        found = sf.client_opcodes()
        for client in sf.CLIENTS:
            self.assertTrue(set(client.opcodes) <= set(found[client.address]),
                            f"0x{client.address:x}: {found[client.address]}")

    def test_the_application_shares_its_structure_pointer(self):
        share = sf.pointer_share()
        self.assertTrue(share["cell_is_in_the_pool"])
        self.assertTrue(share["record_array_in_pool"])
        self.assertEqual(share["cell_value"], "0x180344f4")

    def test_the_shared_base_plus_35c_is_log110s_travel_array(self):
        self.assertTrue(sf.pointer_share()["matches_log110"])
        self.assertEqual(sf.pointer_share()["travel_array"], "0x18034850")

    def test_the_second_context_writes_the_travel_array(self):
        self.assertEqual(sf.delivery()["travel_store_count"], 3)

    def test_the_second_context_writes_raw_samples(self):
        self.assertEqual(sf.delivery()["sample_store_count"], 24)

    def test_the_second_context_never_touches_the_bitmap(self):
        self.assertFalse(sf.delivery()["bitmap_referenced"])

    def test_the_travel_curve_agrees_on_three_independent_properties(self):
        """Length, monotonicity and maximum. Any one alone could be chance."""
        curve = sf.travel_curve()
        self.assertTrue(curve["length_equals_clamp_bound"])
        self.assertTrue(curve["monotonic_non_decreasing"])
        self.assertTrue(curve["maximum_is_twice_the_threshold"])
        self.assertEqual(curve["length"], 1280)
        self.assertEqual(curve["maximum"], 200)

    def test_the_tick_job_reaches_the_sample_client(self):
        cad = sf.cadence()
        self.assertTrue(cad["reaches_the_sample_client"])
        self.assertEqual(cad["stub_target"], "0x1801be22")

    def test_the_absolute_rate_stays_unresolved(self):
        self.assertTrue(sf.cadence()["absolute_rate"].startswith("UNRESOLVED"))

    def test_reports_on_disk_are_current(self):
        payload = sf.bodies()
        stale = [n for n, b in payload.items()
                 if not (sf.NOTES / n).exists()
                 or (sf.NOTES / n).read_text() != b]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(sf.bodies()["sample-flow.json"],
                         sf.bodies()["sample-flow.json"])

    def test_the_report_states_no_device_was_accessed(self):
        text = "\n".join(sf.report_lines()).lower()
        self.assertIn("no device was accessed", text)


@unittest.skipUnless(READY, "preserved dumps or Ghidra slices absent")
class AntiPromotion(unittest.TestCase):
    """The wording is allowed only while the evidence holds it up.

    Log 118 banned "gate is closed" outright. That ban is lifted here because
    the path is complete — so the guard has to become a live one: break any
    supporting fact and the conclusion must move on its own.
    """

    def test_the_gate_is_closed_only_because_the_path_is_complete(self):
        self.assertTrue(sf.path_complete())
        self.assertEqual(sf.hall_gate()["status"], "CLOSED")

    def test_breaking_the_pointer_share_reopens_the_gate(self):
        broken = dict(sf.pointer_share(), matches_log110=False)
        with mock.patch.object(sf, "pointer_share", return_value=broken):
            self.assertFalse(sf.path_complete())
            self.assertEqual(sf.hall_gate()["status"], "still open")

    def test_breaking_the_travel_delivery_reopens_the_gate(self):
        broken = dict(sf.delivery(), travel_store_count=0)
        with mock.patch.object(sf, "delivery", return_value=broken):
            self.assertFalse(sf.path_complete())
            self.assertEqual(sf.hall_gate()["status"], "still open")

    def test_breaking_the_cadence_reopens_the_gate(self):
        broken = dict(sf.cadence(), reaches_the_sample_client=False)
        with mock.patch.object(sf, "cadence", return_value=broken):
            self.assertFalse(sf.path_complete())
            self.assertEqual(sf.hall_gate()["status"], "still open")

    def test_breaking_the_travel_curve_reopens_the_gate(self):
        broken = dict(sf.travel_curve(), monotonic_non_decreasing=False)
        with mock.patch.object(sf, "travel_curve", return_value=broken):
            self.assertFalse(sf.path_complete())
            self.assertEqual(sf.hall_gate()["status"], "still open")

    def test_a_reopened_gate_makes_verification_fail(self):
        """Not just the label: the checks must go red too."""
        broken = dict(sf.cadence(), reaches_the_sample_client=False)
        with mock.patch.object(sf, "cadence", return_value=broken):
            failed = [c["label"] for c in sf.verify() if not c["ok"]]
        self.assertTrue(any("CLOSED" in lbl for lbl in failed), failed)
        self.assertTrue(any("producer path" in lbl for lbl in failed), failed)

    def test_the_claim_text_tracks_the_computed_state(self):
        """The prose answer must not outlive the computation behind it."""
        claim, = [c for c in sf.CLAIMS if c.key == "gate"]
        self.assertIn("YES", claim.answer)
        self.assertTrue(sf.path_complete(),
                        "the affirmative claim is only licensed while the "
                        "path is complete")

    def test_the_rate_is_never_upgraded_to_a_frequency(self):
        """A ratio is not a frequency, and no wording may imply otherwise."""
        blob = " ".join(c.answer.lower() for c in sf.CLAIMS)
        for phrase in ("khz", "hz", "milliseconds", "microseconds",
                       "polling rate of", "1000 hz"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_frequency_detector_is_not_vacuous(self):
        self.assertIn("khz", "a sentence claiming 8 khz".lower())


if __name__ == "__main__":
    unittest.main()
