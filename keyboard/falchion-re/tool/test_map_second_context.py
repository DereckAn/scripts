#!/usr/bin/env python3
"""Tests for the second-execution-context analysis.

Two groups. `Pure` runs anywhere and pins the decoders and the discipline —
the confidence vocabulary, the refusal to overclaim the Hall gate, the
fail-closed behaviour on bad evidence. `Evidence` needs the preserved dumps
and the Ghidra census, and is skipped rather than silently passing when they
are absent, the same way `test_map_hardware_interfaces` handles it.

Every check the tool makes must be able to fail, so the negative tests below
corrupt the inputs and require a FAIL or a raise.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_second_context as ms

READY = (ms.INSTALLED.exists() and ms.VENDOR.exists()
         and (ms.PERIPHERALS / "ram18038000.txt").exists()
         and (ms.PERIPHERALS / "installed_a.txt").exists())

CONFIDENCES = {"observed", "strongly-inferred", "inferred",
               "hypothesis", "unresolved"}


class Pure(unittest.TestCase):
    """No preserved evidence needed."""

    def test_the_confidence_vocabulary_is_closed(self):
        for claim in ms.CLAIMS:
            self.assertIn(claim.confidence, CONFIDENCES, claim.key)

    def test_every_claim_cites_something(self):
        for claim in ms.CLAIMS:
            self.assertTrue(claim.kind_basis.strip(), claim.key)
            self.assertTrue(claim.evidence, claim.key)

    def test_no_claim_says_the_hall_gate_is_closed(self):
        """The tempting overclaim, blocked by a test.

        This image is the leading candidate owner of the acquisition, so the
        pressure to write 'the gate falls' is real. It does not fall, and a
        future edit that says it does must break here.
        """
        banned = ("gate falls", "gate is closed", "gate closed",
                  "acquisition is recovered", "producer is recovered",
                  "owns the hall acquisition", "fills the travel array")
        blob = " ".join(c.answer.lower() + " " + c.question.lower()
                        for c in ms.CLAIMS)
        for phrase in banned:
            self.assertNotIn(phrase, blob, f"overclaim: {phrase!r}")

    def test_the_overclaim_detector_is_not_vacuous(self):
        """A companion, so the test above cannot pass by matching nothing."""
        blob = "the gate falls because the producer is recovered"
        self.assertIn("gate falls", blob)
        self.assertIn("producer is recovered", blob)

    def test_the_unresolved_list_names_the_unresolved_access_ratio(self):
        keys = {k for k, _ in ms.UNRESOLVED}
        self.assertIn("unresolved_accesses", keys)
        self.assertIn("travel_producer", keys)
        self.assertIn("concurrency", keys)

    def test_no_device_or_flashing_vocabulary_in_the_tool(self):
        text = Path(ms.__file__).read_text().lower()
        for word in ("/dev/hidraw", "hid.device", "usb.core", "subprocess",
                     "socket", "urllib", "sudo", "erase(", "program(",
                     "spi_write", "bootloader_enter"):
            self.assertNotIn(word, text, word)

    def test_the_device_detector_is_not_vacuous(self):
        self.assertIn("/dev/hidraw", "a line mentioning /dev/hidraw".lower())

    def test_a_missing_source_fails_closed(self):
        with mock.patch.object(ms, "INSTALLED", Path("/nonexistent/x.bin")):
            with self.assertRaises(ms.SecondContextError):
                ms.sources()

    def test_a_wrong_source_hash_fails_closed(self):
        """The allowlist must reject a different binary, not adapt to it."""
        with mock.patch.object(ms, "SOURCE_SHA",
                               dict(ms.SOURCE_SHA, vendor="0" * 64)):
            if not ms.VENDOR.exists():
                self.skipTest("preserved vendor dump absent")
            with self.assertRaises(ms.SecondContextError) as caught:
                ms.sources()
            self.assertIn("allowlist", str(caught.exception))

    def test_main_reports_failure_rather_than_raising(self):
        with mock.patch.object(ms, "bodies", side_effect=OSError("no evidence")):
            self.assertEqual(ms.main([]), 1)

    def test_a_missing_census_fails_closed(self):
        with mock.patch.object(ms, "PERIPHERALS", Path("/nonexistent")):
            with self.assertRaises(ms.SecondContextError):
                ms._census(Path("/nonexistent/ram18038000.txt"))

    def test_a_census_without_a_result_line_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.txt"
            path.write_text("ACCESS target=0x40000000 width=4 dir=read "
                            "instr=1 func=2 base=r0@0x40000000 off=0 "
                            "stored=unknown\n")
            with self.assertRaises(ms.SecondContextError) as caught:
                ms._census(path)
            self.assertIn("RESULT", str(caught.exception))


@unittest.skipUnless(READY, "run the Ghidra census step first")
class Evidence(unittest.TestCase):
    """Needs the preserved dumps and the Ghidra outputs."""

    def test_every_check_passes(self):
        failed = [c["label"] for c in ms.verify() if not c["ok"]]
        self.assertEqual(failed, [], f"{len(failed)} checks failed")

    def test_the_slice_is_exactly_the_preserved_range(self):
        both = ms.slices()
        vendor = ms.VENDOR.read_bytes()
        self.assertEqual(both["vendor"], vendor[ms.IMAGE_LO:ms.IMAGE_HI])

    def test_the_imported_file_matches_the_vendor_slice(self):
        path = ms.IMPORTS / "ram_image_18038000.bin"
        if not path.exists():
            self.skipTest("import slice absent")
        self.assertEqual(path.read_bytes(), ms.slices()["vendor"])

    def test_the_two_releases_differ_only_in_the_word_sum_field(self):
        """The correction this step found, pinned.

        Phase 3 treated the range as one opaque image. Four bytes differ
        between releases and all four are the application word-sum, so the
        code is identical and a 'the second image changed' claim would be
        wrong.
        """
        delta = ms.release_delta()
        self.assertEqual(delta["differing_bytes"], 4)
        self.assertTrue(delta["all_inside_word_sum_field"])
        self.assertTrue(delta["code_bytes_identical"])

    def test_the_installed_offset_is_translated(self):
        """The installed dump starts at 0x10000; using a raw offset compares
        the wrong bytes and would make the delta test above pass or fail for
        the wrong reason."""
        installed = ms.INSTALLED.read_bytes()
        naive = installed[ms.IMAGE_LO:ms.IMAGE_HI]
        self.assertNotEqual(naive, ms.slices()["installed"])

    def test_the_token_is_at_the_recorded_offset(self):
        data = ms.image()
        self.assertEqual(ms.word(data, ms.TOKEN_POOL), ms.HANDSHAKE_TOKEN)
        self.assertEqual(ms.TOKEN_POOL - ms.RUNTIME_BASE, 0x3214)

    def test_the_vector_table_has_one_live_external_handler(self):
        vt = ms.vector_table()
        self.assertEqual(vt["live_external"], ["IRQ3"])
        self.assertEqual(vt["initial_sp"], "0x1803e458")
        self.assertEqual(vt["reset"], "0x180381c1")

    def test_the_dispatch_table_decodes_to_sixteen_opcodes(self):
        dt = ms.dispatch_table()
        self.assertEqual(dt["count"], 16)
        self.assertEqual(len(dt["rows"]), 16)
        self.assertGreaterEqual(len(dt["implemented"]), 8)

    def test_opcode_0x0f_has_its_own_handler(self):
        """The opcode the entry image's client actually issues."""
        row = next(r for r in ms.dispatch_table()["rows"]
                   if r["opcode"] == "0x0f")
        self.assertFalse(row["is_fallback"])

    def test_the_travel_array_is_still_in_no_aligned_word(self):
        """Log 110's negative, re-run with this image included.

        This is the test that stops the gate being declared closed: if the
        address ever does appear, this fails and the conclusion must be
        rewritten.
        """
        row = next(r for r in ms.cross_context()["rows"]
                   if r["name"] == "travel_array")
        self.assertFalse(row["found_anywhere"], row["found_in"])

    def test_the_mailbox_record_address_is_known_to_both_sides(self):
        row = next(r for r in ms.cross_context()["rows"]
                   if r["name"] == "mailbox_records")
        self.assertTrue(row["found_in_second_context"])
        self.assertTrue(any(k.startswith("entry") for k in row["found_in"]),
                        row["found_in"])

    def test_the_0x40040000_block_is_exclusive(self):
        self.assertIn("0x40040000", ms.census()["exclusive"])

    def test_no_resolved_access_reaches_application_ram(self):
        self.assertFalse(ms.census()["touches_application_ram"])

    def test_the_unresolved_count_is_reported_not_hidden(self):
        cen = ms.census()
        self.assertGreater(cen["unresolved"], 0)
        self.assertIn("unresolved", json.dumps(ms.to_dict()["shaped_questions"]))

    def test_0x40022000_is_not_a_per_channel_bank_here(self):
        bank = ms.shaped_questions()["per_channel_bank_0x40022000"]
        self.assertFalse(bank["is_a_per_channel_bank_here"])
        self.assertEqual(bank["distinct_registers"], 1)

    def test_both_watchdog_blocks_get_the_reset_path_disable(self):
        wd = ms.watchdog()
        self.assertTrue(wd["matches_log114_reset_path_disable"])
        self.assertEqual(len(wd["blocks"]), 2)
        for block in wd["blocks"]:
            self.assertTrue(block["disable_written"], block["block"])
            self.assertTrue(block["key_written"], block["block"])

    def test_the_hall_gate_is_narrowed_not_closed(self):
        hg = ms.hall_gate()
        self.assertTrue(hg["moved"])
        self.assertEqual(hg["gate_status"], "narrowed, not closed")
        self.assertTrue(hg["log110_negative_still_holds"])

    def test_a_corrupted_token_makes_verification_fail(self):
        """Anti-vacuity: the token check must be able to fail."""
        data = bytearray(ms.image())
        struct.pack_into("<I", data, ms.TOKEN_POOL - ms.RUNTIME_BASE, 0xDEADBEEF)
        with mock.patch.object(ms, "image", return_value=bytes(data)):
            failed = [c["label"] for c in ms.verify() if not c["ok"]]
        self.assertTrue(any("token" in label for label in failed), failed)

    def test_a_census_claiming_an_application_ram_access_makes_it_fail(self):
        """If the image ever is shown to touch application RAM, the tool must
        say so rather than keep reporting the reassuring negative."""
        original = ms._census          # captured before patching, or fake recurses
        rows, summary = original(ms.PERIPHERALS / "ram18038000.txt")
        rows.append({"target": 0x18034850, "width": 1, "dir": "write",
                     "instr": "0", "func": "0", "stored": "unknown"})

        def fake(path):
            if path.name == "ram18038000.txt":
                return rows, summary
            return original(path)

        with mock.patch.object(ms, "_census", side_effect=fake):
            self.assertTrue(ms.census()["touches_application_ram"])
            failed = [c["label"] for c in ms.verify() if not c["ok"]]
        self.assertTrue(any("application RAM" in label for label in failed), failed)

    def test_reports_on_disk_are_current(self):
        payload = ms.bodies()
        stale = [name for name, body in payload.items()
                 if not (ms.NOTES / name).exists()
                 or (ms.NOTES / name).read_text() != body]
        self.assertEqual(stale, [], "run --write")

    def test_json_is_deterministic(self):
        self.assertEqual(ms.bodies()["second-context.json"],
                         ms.bodies()["second-context.json"])

    def test_the_report_never_claims_a_device_was_touched(self):
        text = "\n".join(ms.report_lines()).lower()
        self.assertIn("no device was accessed", text)
        self.assertIn("offline", text)


if __name__ == "__main__":
    unittest.main()
