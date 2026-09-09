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

    def test_the_table_admits_whatever_is_still_undecoded(self):
        """Log 128 asserted more than ten located-only rows, which was the
        honest state then. Log 130 decoded twelve of the thirteen, so the
        assertion is re-anchored rather than dropped: whatever remains must
        still be reported, and the coverage must still name all three grades
        the model uses."""
        cov = self.doc["coverage"]
        self.assertIn("static-handler-proven", cov)
        self.assertIn("wire-proven", cov)
        left = [r["subcommand"] for r in
                self.doc["subcommands_51"] + self.doc["queries_12"]
                if r["confidence"] == "static-located-only"]
        self.assertEqual(cov.get("static-located-only", 0), len(left))
        self.assertEqual(len(left), 1)

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


class LogOneThirtyEvidence(unittest.TestCase):
    """Log 130: the located-only remainder, block D, the dual-role banks."""

    def setUp(self):
        self.doc = m.to_dict()
        self.subs = {r["subcommand"]: r for r in self.doc["subcommands_51"]}
        self.queries = {r["subcommand"]: r for r in self.doc["queries_12"]}

    def test_only_one_subcommand_is_still_located_only(self):
        left = [r["subcommand"] for r in
                self.doc["subcommands_51"] + self.doc["queries_12"]
                if r["confidence"] == "static-located-only"]
        self.assertEqual(left, ["0x52"])

    def test_the_four_actuation_and_rapid_trigger_carriers(self):
        """All-key and per-key, actuation and rapid trigger — the four HAL
        names that had no opcode before this step."""
        for sub, needle in (("0x50", "bits 9..15"), ("0x4f", "+0x08"),
                            ("0x58", "20..22"), ("0x59", "+0x06")):
            self.assertIn(needle, self.subs[sub]["meaning"], sub)
            self.assertEqual(self.subs[sub]["confidence"],
                             "static-handler-proven", sub)

    def test_the_shared_rapid_trigger_helper_bytes(self):
        """0x58 and 0x59 differ only in the mode they pass to 0x1800f948."""
        self.assertEqual(m.halfwords(0x1800334C, 2), "f00c fafc")
        self.assertEqual(m.halfwords(0x1800338C, 2), "f00c fadc")
        self.assertEqual(m.halfwords(0x1800F9D0, 2), "f362 5c16")   # bfi #20,#3
        self.assertEqual(m.halfwords(0x1800F9FC, 2), "f3c4 4442")   # ubfx #17,#3

    def test_the_per_key_override_discipline_is_the_same_in_both_families(self):
        """0x4f clears/sets bit 15 of record +0x08; 0x1800f948 clears/sets bit
        7 of +0x06 and +0x07. Same rule, two fields."""
        self.assertEqual(m.halfwords(0x18002BCC, 2), "f440 4000")   # orr 0x8000
        self.assertEqual(m.halfwords(0x1800F9A8, 2), "f022 0280")   # bic 0x80

    def test_the_mode_byte_is_at_least_four_valued(self):
        for sub in ("0x23", "0x24"):
            self.assertIn("+0x04", self.subs[sub]["meaning"], sub)
        self.assertEqual(m.halfwords(0x18002814, 2), "f886 9004")
        self.assertEqual(m.halfwords(0x180028EC, 1), "713a")

    def test_the_firmware_named_handlers_carry_their_strings(self):
        for sub, name in (("0x18", "=MS_A"), ("0x23", "=KC_S,T_A"),
                          ("0x55", "=TEMP1_S_KC"), ("0x56", "S_ST_DEF"),
                          ("0x90", "SC_S_A")):
            self.assertIn(name, self.subs[sub]["meaning"]
                          + self.subs[sub]["evidence"], sub)

    def test_the_key_code_pair_range_check(self):
        """0x55 validates each translated code to HID 0x04..0x91 or
        0xe0..0xe7."""
        self.assertEqual(m.halfwords(0x1800311C, 1), "298d")
        self.assertEqual(m.halfwords(0x18003122, 1), "2907")
        self.assertIn("0xe0..0xe7", self.subs["0x55"]["meaning"])

    def test_the_two_queries_are_one_query(self):
        self.assertEqual(self.queries["0x13"]["confidence"],
                         "static-handler-proven")
        self.assertIn("two modes", self.queries["0x13"]["meaning"])
        self.assertEqual(m.halfwords(0x180021B4, 1), "2201")

    def test_block_d_layout_closes_on_its_declared_size(self):
        bd = self.doc["block_d"]
        self.assertTrue(bd["arithmetic_closes"])
        self.assertEqual(4 + 2 * 0x1EE, 0x3E0)
        self.assertEqual([r["offset"] for r in bd["layout"]],
                         ["+0x000", "+0x004", "+0x1f2"])

    def test_block_d_entry_count_is_read_from_the_loop_bound(self):
        self.assertEqual(m.halfwords(0x1800585A, 1), "29f7")        # cmp #0xf7
        self.assertEqual(m.halfwords(0x18005830, 2), "eb0a 0741")   # + i*2
        self.assertIn("247", self.doc["block_d"]["layout"][1]["role"])

    def test_block_d_names_no_armoury_crate_field(self):
        self.assertIsNone(self.doc["block_d"]["ac_profile_match"])
        self.assertIn("NO MATCH IS CLAIMED",
                      self.doc["block_d"]["ac_profile_match_note"])

    def test_block_d_defaults_are_not_invented(self):
        self.assertIn("NOT RECOVERED", self.doc["block_d"]["defaults"])

    def test_the_bank_selector_is_not_claimed_to_be_the_layer(self):
        """Log 128 called it per-layer; the consumer diffs two banks."""
        sel = self.doc["hold_timer"]["buffer"]["selector"]
        self.assertIn("WITHDRAWN", sel)
        self.assertIn("BANK SELECTOR", sel)
        self.assertEqual(m.halfwords(0x18006094, 2), "eb09 00c0")
        self.assertEqual(m.halfwords(0x180060A4, 1), "42a8")

    def test_the_three_open_timer_questions_say_they_are_open(self):
        ht = self.doc["hold_timer"]
        self.assertIn("NONE FOUND", ht["buffer"]["wrap"])
        self.assertIn("NOT ESTABLISHED", ht["release_before_expiry"])
        self.assertIn("NOT ESTABLISHED", ht["threshold_writer"])

    def test_the_timer_mechanism_is_the_agreed_wording(self):
        self.assertEqual(self.doc["hold_timer"]["mechanism"],
                         "dual-role, hold-to-alternate, threshold in 10 ms "
                         "units")
        self.assertIsNone(self.doc["hold_timer"]["hal_match"])

    def test_every_hal_name_gets_a_disposition(self):
        disp = {d["hal_name"] for d in self.doc["hal_disposition"]}
        for name in self.doc["hal_names_without_an_opcode"]:
            self.assertIn(name, disp, name)

    def test_a_hal_name_with_no_carrier_is_a_finding(self):
        none_found = [d for d in self.doc["hal_disposition"]
                      if d["candidate_carrier"] is None]
        self.assertGreaterEqual(len(none_found), 10)
        for d in none_found:
            self.assertEqual(d["confidence"], "no plausible carrier found")
            self.assertTrue(d["evidence"])

    def test_named_carriers_are_graded_and_cited(self):
        for d in self.doc["hal_disposition"]:
            if d["candidate_carrier"] is not None:
                self.assertIn(d["confidence"],
                              ("strongly-inferred", "hypothesis"))
                self.assertTrue(d["evidence"], d["hal_name"])

    def test_speed_tap_and_dks_stay_hypotheses(self):
        by = {d["hal_name"]: d for d in self.doc["hal_disposition"]}
        for name in ("SetSpeedTap", "ChangeKey_DKS", "ChangeKey_ModTap"):
            self.assertEqual(by[name]["confidence"], "hypothesis", name)

    def test_the_four_new_carriers_are_strongly_inferred(self):
        by = {d["hal_name"]: d for d in self.doc["hal_disposition"]}
        for name in ("SetActuation_AllKey", "SetActuation_PreKey",
                     "SetRapidTrigger_AllKey", "SetRapidTrigger_PreKey"):
            self.assertEqual(by[name]["confidence"], "strongly-inferred", name)
            self.assertIsNotNone(by[name]["candidate_carrier"], name)

    def test_dead_zone_has_no_carrier(self):
        by = {d["hal_name"]: d for d in self.doc["hal_disposition"]}
        for name in ("SetDeadZone_AllKey", "SetDeadZone_PreKey"):
            self.assertIsNone(by[name]["candidate_carrier"], name)
