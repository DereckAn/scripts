#!/usr/bin/env python3
"""Tests for the vendor command map.

Four groups.

  FAIL-CLOSED. A located subcommand with no curated row RAISES rather than
  being emitted as a blank; a missing image or upstream model raises. The whole
  point of this map is completeness, so a silently short table is the worst
  failure it could have.

  THE EVIDENCE. Every compare site, every jump table and every cited
  instruction pinned to the image, in both releases.

  ANTI-VACUITY. The two headline negatives — block D has no USB writer, the
  dispatcher never writes the profile selection byte — each have a companion
  that makes the same filter produce a positive.

  DISCIPLINE. Nothing is named for a feature on resemblance; the undecoded
  majority must stay labelled undecoded; queries must not be gated and writes
  must be; no frame may be constructed.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_vendor_commands as m

ROOT = Path(__file__).resolve().parent.parent


class FailClosed(unittest.TestCase):
    def test_missing_image_raises(self):
        with self.assertRaises(m.CommandError):
            m.image("no-such-slice.bin")

    def test_address_outside_the_image_raises(self):
        with self.assertRaises(m.CommandError):
            m.halfwords(0x1FFFFFFC, 1)

    def test_byte_outside_the_image_raises(self):
        with self.assertRaises(m.CommandError):
            m.byte(0x1FFFFFFC)

    def test_a_located_subcommand_without_a_curated_row_raises(self):
        original = m.SUBCOMMANDS
        m.SUBCOMMANDS = tuple(r for r in original if r[0] != 0x31)
        m.subcommand_table.cache_clear()
        try:
            with self.assertRaises(m.CommandError) as ctx:
                m.subcommand_table()
            self.assertIn("no curated row", str(ctx.exception))
        finally:
            m.SUBCOMMANDS = original
            m.subcommand_table.cache_clear()

    def test_a_located_query_without_a_curated_row_raises(self):
        original = m.QUERIES
        m.QUERIES = tuple(r for r in original if r[0] != 0x15)
        m.query_table.cache_clear()
        try:
            with self.assertRaises(m.CommandError):
                m.query_table()
        finally:
            m.QUERIES = original
            m.query_table.cache_clear()

    def test_a_missing_upstream_model_raises(self):
        original = m.WIRE_MODEL
        m.WIRE_MODEL = ROOT / "notes" / "does-not-exist.json"
        m.rapid_burst.cache_clear()
        try:
            with self.assertRaises(m.CommandError):
                m.rapid_burst()
        finally:
            m.WIRE_MODEL = original
            m.rapid_burst.cache_clear()


class TheEvidence(unittest.TestCase):
    def test_seventeen_top_level_opcodes(self):
        self.assertEqual(len(m.opcode_table()), 17)

    def test_twenty_four_subcommands(self):
        self.assertEqual(len(m.subcommand_table()), 24)

    def test_ten_queries(self):
        self.assertEqual(len(m.query_table()), 10)

    def test_every_compare_site_is_where_the_model_says(self):
        for addr, op, enc, _ in m.TOP_LEVEL_SITES + m.SUB_SITES:
            self.assertEqual(m.halfwords(addr, 1), enc, f"{op:#04x}@{addr:#x}")

    def test_every_cited_instruction_is_present(self):
        for addr, enc in m.CITED.items():
            self.assertEqual(m.halfwords(addr, len(enc.split())), enc,
                             hex(addr))

    def test_the_subcommand_jump_table_decodes(self):
        tbb = m.decode_tbb(*m.SUB_TBB)
        self.assertEqual(set(tbb), {0x50, 0x51, 0x52, 0x53, 0x54})
        self.assertEqual(tbb[0x50], 0x180026EC)

    def test_the_query_jump_table_decodes_and_has_a_default(self):
        tbh = m.decode_tbh(*m.QUERY_TBH)
        self.assertEqual(tbh[0x00], 0x1800209A)
        self.assertEqual(len({v for v in tbh.values()}), 6)

    def test_the_vendor_release_has_the_same_dispatch(self):
        for addr, op, enc, _ in m.TOP_LEVEL_SITES:
            self.assertEqual(m.halfwords(addr, 1, m.VENDOR_APP), enc,
                             f"{op:#04x}")

    def test_the_profile_selection_byte_has_two_writers(self):
        ps = m.profile_switch()
        self.assertEqual(len(ps["writers"]), 2)
        self.assertEqual(ps["dispatcher_writes"], 0)
        self.assertGreater(ps["reader_count"], 50)

    def test_the_macro_block_has_a_usb_writer(self):
        self.assertTrue(m.macro_block()["has_usb_writer"])

    def test_block_d_has_no_usb_writer(self):
        bd = m.block_d()
        self.assertFalse(bd["has_usb_writer"])
        self.assertEqual(bd["writer_functions"], [f"{m.STORAGE_SM:#x}"])

    def test_the_rapid_burst_is_nine_identical_rate_writes(self):
        rb = m.rapid_burst()
        self.assertEqual(rb["count"], 9)
        self.assertEqual(rb["indices"], [0])
        self.assertEqual(len(rb["distinct_payloads"]), 1)


class AntiVacuity(unittest.TestCase):
    def test_the_census_is_scoped_to_one_export(self):
        """Unscoped, the vendor image's identical addresses merge two releases
        and turn block D's single writer into five."""
        scoped = m.accesses(0x1801FEF8, 0x180202D8)
        unscoped = [r for r in m.census()
                    if 0x1801FEF8 <= r["target"] < 0x180202D8]
        self.assertLess(len(scoped), len(unscoped))
        self.assertTrue(all(r["file"] == m.INSTALLED_EXPORT for r in scoped))

    def test_the_block_filter_finds_accesses_in_both_blocks(self):
        self.assertGreater(len(m.accesses(0x180225FC, 0x18022C60)), 10)
        self.assertGreater(len(m.accesses(0x1801FEF8, 0x180202D8)), 10)

    def test_the_dispatcher_does_write_other_things(self):
        """'The dispatcher never writes the selection byte' means something
        only because the dispatcher demonstrably writes elsewhere."""
        writes = [r for r in m.accesses(0x180225FC, 0x18022C60)
                  if r["dir"] == "write" and r["func"] == m.DISPATCHER]
        self.assertTrue(writes)

    def test_the_census_is_populated(self):
        self.assertGreater(len(m.census()), 1000)

    def test_a_wrong_encoding_would_be_caught(self):
        self.assertNotEqual(m.halfwords(0x18001FFC, 1), "2941")
        self.assertEqual(m.halfwords(0x18001FFC, 1), "2a41")


class Discipline(unittest.TestCase):
    def setUp(self):
        self.doc = m.to_dict()
        self.md = m.markdown()

    def test_most_of_the_table_is_admitted_undecoded(self):
        cov = self.doc["coverage"]
        self.assertGreater(cov["static-located-only"], 10)
        self.assertIn("static-handler-proven", cov)
        self.assertIn("wire-proven", cov)

    def test_every_write_is_gated_and_no_query_is(self):
        for r in self.doc["subcommands_51"]:
            self.assertTrue(r["owner_approval_required"], r["subcommand"])
        for r in self.doc["queries_12"]:
            self.assertFalse(r["owner_approval_required"], r["subcommand"])

    def test_the_hold_timer_gets_no_hal_name(self):
        ht = self.doc["hold_timer"]
        self.assertIsNone(ht["hal_match"])
        self.assertIn("hypothesis", ht["hal_match_confidence"])
        self.assertGreater(len(ht["hal_candidates"]), 1)

    def test_hal_names_without_an_opcode_are_listed(self):
        names = self.doc["hal_names_without_an_opcode"]
        self.assertIn("SetSpeedTap", names)
        self.assertIn("SetDeadZone_AllKey", names)

    def test_the_actuation_match_is_offered_not_asserted(self):
        row = next(r for r in self.doc["subcommands_51"]
                   if r["subcommand"] == "0x50")
        self.assertIn("offered as a match, not as the command's name",
                      row["meaning"])

    def test_undecoded_rows_say_so(self):
        """A `static-located-only` row must state the limit in words, not just
        wear the label."""
        for r in self.doc["subcommands_51"] + self.doc["queries_12"]:
            if r["confidence"] == "static-located-only":
                self.assertIn("NOT established", r["meaning"], r["subcommand"])

    def test_handler_proven_rows_name_a_store_or_a_reply(self):
        for r in self.doc["subcommands_51"]:
            if r["confidence"] == "static-handler-proven":
                self.assertNotEqual(r["storage"], "unestablished",
                                    r["subcommand"])

    def test_the_polling_rate_field_is_marked_unchecksummed(self):
        row = next(f for f in self.doc["storage_map"]
                   if f["field"] == "polling-rate index")
        self.assertFalse(row["covered"])
        self.assertIn("NEITHER", row["checksum"])

    def test_no_frame_is_constructed(self):
        blob = json.dumps(self.doc).lower()
        for banned in ("send this", "transmit", "write_report", "payload = b'"):
            self.assertNotIn(banned, blob, banned)
        self.assertIn("no frame was constructed", self.doc["disclaimer"].lower())

    def test_never_send_covers_the_whole_write_family(self):
        frames = " ".join(n["frame"] for n in self.doc["never_send"])
        self.assertIn("50 55", frames)
        self.assertIn("51 xx", frames)

    def test_the_document_states_no_device_was_accessed(self):
        self.assertIn("No device was accessed", self.doc["disclaimer"])
        self.assertIn("No device was accessed", self.md)

    def test_the_json_is_deterministic(self):
        self.assertEqual(json.dumps(m.to_dict(), sort_keys=True),
                         json.dumps(m.to_dict(), sort_keys=True))

    def test_every_check_passes(self):
        failed = [c for c in self.doc["checks"] if not c["ok"]]
        self.assertEqual(failed, [], failed)

    def test_written_notes_are_current(self):
        for name, body in m.bodies().items():
            self.assertEqual((ROOT / "notes" / name).read_text(), body, name)

    def test_main_check_reports_current(self):
        out = subprocess.run(
            [sys.executable, str(ROOT / "tool" / "map_vendor_commands.py"),
             "--check"], capture_output=True, text=True, check=False)
        self.assertIn("reports_current=True stale=0", out.stdout)


if __name__ == "__main__":
    unittest.main()
