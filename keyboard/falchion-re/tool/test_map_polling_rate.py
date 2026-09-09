#!/usr/bin/env python3
"""Tests for the polling-rate trace.

The result is a negative about the FIRMWARE's consumers, reached by
enumeration, while the PROTOCOL side is explicitly left open — the note records
`SetPollingRate` as a known HAL name that was never captured. Keeping those two
apart is the main thing these tests guard, along with the rule that no Hz may
be attached to anything.
"""
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_polling_rate as pr
import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and pr.PROFILE.exists() and pr.PROTOCOL.exists()
         and (pr.PERIPHERALS / "installed_b.txt").exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):

    def test_every_claim_carries_a_label_and_a_citation(self):
        for claim in pr.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_the_timer_claim_is_unresolved_not_eliminated(self):
        """A block that was never found cannot be ruled out, only unconfirmed."""
        timer, = [c for c in pr.CLAIMS if c.key == "timer"]
        self.assertEqual(timer.confidence, "unresolved")

    def test_the_unresolved_list_keeps_the_protocol_side_open(self):
        keys = {k for k, _ in pr.UNRESOLVED}
        self.assertIn("uncaptured_commands", keys)
        self.assertIn("rate_destination", keys)
        self.assertIn("irq38_timer", keys)

    def test_no_device_vocabulary_in_the_tool(self):
        text = Path(pr.__file__).read_text().lower()
        for word in ("/dev/hidraw", "usb.core", "subprocess", "socket",
                     "urllib", "sudo", "hid.write", "send_report"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "mentions /dev/hidraw here")

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(pr, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(pr.main([]), 1)

    def test_a_missing_profile_fails_closed(self):
        with mock.patch.object(pr, "PROFILE", Path("/nonexistent.json")):
            with self.assertRaises(pr.PollingRateError):
                pr.profile_field()

    def test_a_missing_protocol_note_fails_closed(self):
        with mock.patch.object(pr, "PROTOCOL", Path("/nonexistent.md")):
            with self.assertRaises(pr.PollingRateError):
                pr.observed_wire_commands()

    def test_a_missing_slice_fails_closed(self):
        with mock.patch.object(pr, "IMPORTS", Path("/nonexistent")):
            with self.assertRaises(pr.PollingRateError):
                pr._load("app")


@unittest.skipUnless(READY, "preserved dumps or notes absent")
class Evidence(unittest.TestCase):

    def test_every_check_passes(self):
        failed = [c["label"] for c in pr.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} failed")

    def test_the_profile_index_is_read_not_assumed(self):
        prof = pr.profile_field()
        self.assertEqual(prof["polling_rate_index"], "3")
        self.assertEqual(list(prof["performance_block"]), ["pollingRate"])

    def test_no_rate_table_exists_anywhere(self):
        self.assertEqual(pr.rate_tables()["rate_table_count"], 0)
        self.assertTrue(pr.rate_tables()["eliminated"])

    def test_the_rate_table_search_is_not_blind(self):
        """Companion: given a value set that IS present, it must find one."""
        with mock.patch.object(pr, "RATE_VALUES", (1, 2, 3, 4, 5, 6, 7, 8)):
            found = pr.rate_tables()
        self.assertGreater(found["rate_table_count"], 0)

    def test_the_prescaler_divisors_are_immediates(self):
        pl = pr.prescaler_ladder()
        self.assertTrue(pl["all_immediates"])
        self.assertTrue(pl["eliminated"])
        immediates = [s["immediate"] for s in pl["sites"] if s["immediate"]]
        self.assertEqual(immediates, [8, 5, 10, 10])

    def test_the_static_bintervals_match_log107(self):
        bp = pr.binterval_path()
        self.assertEqual(bp["static_bintervals"][:4], [1, 1, 1, 4])
        self.assertTrue(bp["matches_log107"])

    def test_no_ram_binterval_byte_is_referenced(self):
        bp = pr.binterval_path()
        self.assertFalse(bp["any_runtime_reference"])
        for row in bp["ram_binterval_addresses"]:
            self.assertEqual(row["references"], [], row["address"])

    def test_the_binterval_reference_search_is_not_blind(self):
        """The parameter table's own base IS referenced, by the same method."""
        app, base = pr._load("app")
        hits = [i for i in range(0, len(app) - 3, 4)
                if struct.unpack_from("<I", app, i)[0] == pr.PARAM_TABLE_RAM]
        self.assertTrue(hits, "the table base is referenced, so the search works")

    def test_the_mailbox_carries_no_rate(self):
        mb = pr.mailbox_fields()
        self.assertTrue(mb["eliminated"])
        self.assertFalse(mb["any_rate_field"])
        self.assertEqual(mb["count"], 5)

    def test_no_timer_block_is_identified(self):
        tb = pr.timer_block()
        self.assertIsNone(tb["identified_timer_block"])
        self.assertFalse(tb["confirmable"])

    def test_the_tick_clients_are_enumerated(self):
        tick = pr.shared_tick()
        self.assertGreaterEqual(tick["client_count"], 6)
        for client in tick["clients"]:
            self.assertTrue(client["evidence"].startswith("log"))

    def test_reports_on_disk_are_current(self):
        payload = pr.bodies()
        stale = [n for n, b in payload.items()
                 if not (pr.NOTES / n).exists()
                 or (pr.NOTES / n).read_text() != b]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(pr.bodies()["polling-rate.json"],
                         pr.bodies()["polling-rate.json"])

    def test_the_report_states_no_device_and_no_frame(self):
        text = "\n".join(pr.report_lines()).lower()
        self.assertIn("no device was accessed", text)
        self.assertIn("no frame was constructed", text)


@unittest.skipUnless(READY, "preserved dumps or notes absent")
class Discipline(unittest.TestCase):

    def test_the_protocol_side_is_not_confused_with_the_firmware_side(self):
        """The opcode probably exists; the firmware consumer does not appear.
        Conflating the two would be the easy error here."""
        wire = pr.observed_wire_commands()
        self.assertFalse(wire["polling_in_command_table"])
        self.assertEqual(len(wire["hal_method_names"]), 2)
        self.assertTrue(wire["listed_as_never_captured"])

    def test_no_claim_says_the_device_has_no_polling_rate_command(self):
        blob = " ".join(c.answer.lower() for c in pr.CLAIMS)
        for phrase in ("there is no polling-rate command",
                       "the device does not support",
                       "no such command exists"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_overclaim_detector_is_not_vacuous(self):
        self.assertIn("no such command exists",
                      "a sentence: no such command exists")

    def test_no_hz_is_attached_to_the_tick(self):
        units = pr.units_status()
        self.assertFalse(units["hz_attached_to_anything"])
        self.assertEqual(units["irq38_period"], "UNRESOLVED")

    def test_no_claim_states_a_tick_frequency(self):
        blob = " ".join(c.answer.lower() for c in pr.CLAIMS)
        for phrase in ("irq38 is 8000", "runs at 8000 hz", "the tick is 1000 hz",
                       "8 khz tick"):
            self.assertNotIn(phrase, blob, phrase)

    def test_the_frequency_detector_is_not_vacuous(self):
        self.assertIn("runs at 8000 hz", "a sentence: it runs at 8000 hz")

    def test_the_alignment_is_labelled_a_consistency(self):
        """8000/8 = 1000 is suggestive and must never be promoted."""
        note = pr.units_status()["suggestive_but_unproven"].lower()
        self.assertIn("consistency", note)
        self.assertIn("not a measurement", note)

    def test_the_dependency_map_is_not_touched(self):
        self.assertTrue(
            pr.units_status()["dependency_map_effect"].startswith("none"))

    def test_no_frame_shaped_content_in_the_output(self):
        """The step forbids constructing a config-write frame; the generated
        JSON must contain nothing that looks like one."""
        blob = pr.bodies()["polling-rate.json"].lower()
        for phrase in ("send ", "transmit", "write_report", "0x51 0x",
                       "frame:", "payload bytes"):
            self.assertNotIn(phrase, blob, phrase)


if __name__ == "__main__":
    unittest.main()
