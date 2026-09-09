#!/usr/bin/env python3
"""Tests for the polling-rate reader.

Four groups.

  FAIL-CLOSED. Every missing or malformed input raises rather than being
  guessed at. This model claims to have found what two prior steps could not,
  so a parser that silently accepted a truncated census or a missing slice
  would manufacture the finding.

  THE EVIDENCE. The reader table, the gate, the veneer decode and the units,
  each pinned to the bytes and the census records they are read from.

  ANTI-VACUITY. The step's core move is that a search which found nothing was
  looking for the wrong shape. Every "found nothing" and every "found exactly
  this" has a companion that makes the same machinery produce the other answer.

  DISCIPLINE. Log 124 must not be rewritten, the clock CONFIGURATION must stay
  unresolved, the 2000/4000 answer must stay negative, and nothing may be
  patched.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_polling_rate_reader as m

ROOT = Path(__file__).resolve().parent.parent


class FailClosed(unittest.TestCase):
    def test_missing_slice_raises(self):
        with self.assertRaises(m.ReaderError):
            m.slice_bytes("no-such-image.bin")

    def test_address_outside_a_slice_raises(self):
        with self.assertRaises(m.ReaderError):
            m.word(m.APP[0], m.APP[1], 0x1FFFFFFC)

    def test_halfword_run_past_the_end_raises(self):
        with self.assertRaises(m.ReaderError):
            m.halfwords(m.ENTRY[0], m.ENTRY[1], 0x58A0, 64)

    def test_missing_inventory_raises(self):
        with self.assertRaises(m.ReaderError):
            m.functions("no-such-inventory.txt")

    def test_a_veneer_that_is_not_one_raises(self):
        """Pointed at ordinary code the decoder must refuse, not invent."""
        with self.assertRaises(m.ReaderError):
            m.decode_veneer(m.ENTRY[0], m.ENTRY[1], 0x000004BA)

    def test_a_veneer_past_the_end_raises(self):
        with self.assertRaises(m.ReaderError):
            m.decode_veneer(m.ENTRY[0], m.ENTRY[1], 0x58A8)

    def test_a_truncated_census_line_is_not_accepted(self):
        self.assertIsNone(m.ACCESS_RE.match(
            "ACCESS target=0x1801e736 width=1 dir=read instr=180053c4"))

    def test_a_census_line_with_a_bad_direction_is_not_accepted(self):
        self.assertIsNone(m.ACCESS_RE.match(
            "ACCESS target=0x1801e736 width=1 dir=sideways instr=180053c4 "
            "func=18004a7e base=r0@0x1801e734 off=2 stored=unknown"))

    def test_owner_returns_none_rather_than_guessing(self):
        self.assertIsNone(m.owner(0x18007A18))


class TheEvidence(unittest.TestCase):
    def test_exactly_four_readers(self):
        reads = [r for r in m.reader_table() if r["direction"] == "read"]
        self.assertEqual([r["instruction"] for r in reads],
                         [f"{a:#x}" for a in sorted(m.READ_SITES)])

    def test_every_reader_is_the_actuation_compare(self):
        for r in m.reader_table():
            if r["direction"] == "read":
                self.assertEqual(r["function"], "FUN_18004a7e")

    def test_every_reader_uses_an_immediate_offset_of_two(self):
        """The whole reason log 126's literal search could not see them."""
        for r in m.reader_table():
            if r["direction"] == "read":
                self.assertEqual(r["offset"], 2)
                self.assertEqual(int(r["base"].split("@")[1], 16), m.KEY_STATE)

    def test_six_writers_and_only_five_are_in_the_census(self):
        writes = [r for r in m.reader_table() if r["direction"] == "write"]
        self.assertEqual(len(writes), 6)
        self.assertEqual(sum(1 for w in writes if w["census_func"] is None), 1)

    def test_the_sixth_writer_is_in_code_with_no_function_body(self):
        writes = [r for r in m.reader_table() if r["direction"] == "write"]
        orphan = [w for w in writes if w["census_func"] is None][0]
        self.assertEqual(orphan["function"], "NO FUNCTION BODY")
        self.assertEqual(int(orphan["instruction"], 16),
                         m.WRITE_SITE_WITHOUT_FUNCTION)

    def test_the_gate_reads_the_profile_block_the_handler_writes(self):
        self.assertTrue(m.tick_gate()["profile_literal_is_the_profile_block"])

    def test_the_gate_is_two_way_not_a_ladder(self):
        self.assertEqual(m.tick_gate()["divisor_by_index"],
                         {"0": 8, "1": 8, "2": 8, "3": 1})

    def test_the_veneer_decoder_reproduces_a_target_ghidra_resolved(self):
        """Log 119 resolved 0x4062 -> 0x18004a7e independently."""
        self.assertEqual(
            m.decode_veneer(m.ENTRY[0], m.ENTRY[1], 0x00004062), 0x18004A7E)

    def test_every_gated_veneer_matches_log_119(self):
        for v in m.tick_gate()["gated"]:
            self.assertTrue(v["matches_log_119"], v)

    def test_the_sample_fetch_is_on_both_paths(self):
        """Hall acquisition is never gated by the rate, which is a design fact
        a replacement has to preserve."""
        gated = {v["veneer"] for v in m.tick_gate()["gated"]}
        ungated = {v["veneer"] for v in m.tick_gate()["ungated"]}
        self.assertIn("0x4044", gated & ungated)

    def test_the_tick_job_is_identical_in_both_releases(self):
        self.assertTrue(m.tick_gate()["identical_in_both_releases"])

    def test_irq38_is_eight_kilohertz(self):
        self.assertEqual(m.period_model()["irq38_hz"], 8000)
        self.assertEqual(m.period_model()["irq38_period_us"], 125.0)

    def test_the_fast_state_is_predicted_not_fitted(self):
        p = m.period_model()
        self.assertTrue(p["prediction_holds"])
        self.assertEqual(p["derived_from"].split(" ")[1], "0")

    def test_the_parameter_unit_is_rate_invariant(self):
        u = m.units_model()
        self.assertTrue(u["rate_invariant"])
        self.assertEqual(u["parameter_unit_ms"], 10.0)

    def test_the_threshold_array_is_log_125s_keymap_bank(self):
        ta = m.threshold_addressing()
        self.assertTrue(ta["agrees_with_log_125"])
        self.assertEqual(ta["layer_stride_bytes"], "0xd84")

    def test_every_cited_instruction_is_present_in_the_image(self):
        for addr, expected in m.APP_BYTES.items():
            self.assertEqual(
                m.halfwords(m.APP[0], m.APP[1], addr,
                            len(expected.split())), expected, hex(addr))
        for addr, expected in m.ENTRY_BYTES.items():
            self.assertEqual(
                m.halfwords(m.ENTRY[0], m.ENTRY[1], addr,
                            len(expected.split())), expected, hex(addr))


class AntiVacuity(unittest.TestCase):
    def test_the_census_filter_finds_other_addresses(self):
        """A filter that only ever matched one address would prove nothing."""
        self.assertGreater(len(m.census()), 1000)
        for neighbour in (m.KEY_STATE, m.KEY_STATE + 4, m.KEY_STATE + 9):
            self.assertTrue(m.census_for(neighbour), hex(neighbour))

    def test_the_census_is_silent_where_it_should_be(self):
        """It resolves nothing for the byte in the second-context export."""
        rows = m.census_for(m.MULTIPLIER, files=frozenset({"ram18038000.txt",
                                                           "bootloader.txt"}))
        self.assertEqual(rows, [])

    def test_the_second_context_carries_no_nearby_literal(self):
        """And the same scan DOES find them in the application."""
        near = (lambda v: abs(v - m.KEY_STATE) <= 0x100)
        self.assertEqual(m.literal_slots(m.SECOND[0], m.SECOND[1], near), ())
        self.assertGreater(
            len(m.literal_slots(m.APP[0], m.APP[1], near)), 50)

    def test_the_entry_image_carries_no_nearby_literal_either(self):
        near = (lambda v: abs(v - m.KEY_STATE) <= 0x40)
        self.assertEqual(m.literal_slots(m.ENTRY[0], m.ENTRY[1], near), ())

    def test_the_literal_load_decoder_finds_the_gates_own_loads(self):
        """It must find 0x4cc, 0x4d4 and 0x4de, which are read by hand above."""
        sites = {a for a, _, _, _ in
                 m.literal_load_sites(m.ENTRY[0], m.ENTRY[1])}
        for addr in (0x000004CC, 0x000004D4, 0x000004DE):
            self.assertIn(addr, sites, hex(addr))

    def test_the_literal_load_decoder_resolves_the_gates_slots(self):
        want = {0x000004CC: 0x5B4, 0x000004D4: 0x5B8, 0x000004DE: 0x5BC}
        got = {a: s for a, _, s, _ in
               m.literal_load_sites(m.ENTRY[0], m.ENTRY[1]) if a in want}
        self.assertEqual(got, want)

    def test_the_vendor_release_carries_the_same_reads(self):
        rows = m.census_for(m.MULTIPLIER_VENDOR,
                            files=frozenset({"vendor_b.txt"}))
        reads = sorted(r["instr"] for r in rows if r["dir"] == "read")
        self.assertEqual(reads, sorted(m.READ_SITES_VENDOR))
        self.assertTrue(all(r["func"] == m.READER_FUNC
                            for r in rows if r["dir"] == "read"))

    def test_owner_picks_the_smallest_containing_body(self):
        """Log 126 attributed a site wrongly by taking the first match."""
        self.assertEqual(m.owner(0x180053C4), "FUN_18004a7e")
        self.assertEqual(m.owner(0x18002B50), "FUN_18001fbe")


class Discipline(unittest.TestCase):
    def setUp(self):
        self.doc = m.to_dict()
        self.md = m.markdown()

    def test_log_124_is_refined_not_rewritten(self):
        text = m.__doc__ + json.dumps(self.doc)
        self.assertIn("124", text)
        self.assertIn("sealed record", json.dumps(self.doc["supersedes"]))

    def test_log_124s_own_model_is_untouched(self):
        """Its statement was correct for its evidence; it stays its record."""
        import map_polling_rate as old
        self.assertEqual(old.units_status()["irq38_period"], "UNRESOLVED")

    def test_the_clock_configuration_stays_unresolved(self):
        self.assertIn("clock CONFIGURATION",
                      self.doc["period"]["does_not_resolve"])
        self.assertIn("clock_frequency",
                      self.doc["period"]["does_not_resolve"])

    def test_the_dependency_map_still_lists_clock_frequency_unresolved(self):
        import map_platform_dependencies as dep
        entry = next(s for s in dep.SERVICES if s.key == "clock_frequency")
        self.assertEqual(entry.classification, "unresolved")

    def test_the_dependency_map_points_here_without_stating_a_frequency(self):
        """The map classifies services; the number belongs in this model."""
        import re
        import map_platform_dependencies as dep
        entry = next(s for s in dep.SERVICES if s.key == "clock_frequency")
        self.assertIn("polling-rate-reader.json", entry.evidence_boundary)
        self.assertIn("LOG 127", entry.evidence_boundary)
        for unit in ("hz", "mhz", "khz"):
            self.assertIsNone(
                re.search(rf"\b\d+\s*{unit}\b",
                          entry.evidence_boundary.lower()), unit)

    def test_the_period_is_not_claimed_as_observed(self):
        """It rests on one unproven assumption and must say so."""
        p = self.doc["period"]
        self.assertEqual(p["confidence"], "strongly-inferred")
        self.assertIn("not separately proven", p["kind_basis"])
        self.assertTrue(p["would_be_refuted_by"])

    def test_the_2000_4000_answer_is_negative(self):
        f = self.doc["feasibility_2000_4000"]
        self.assertEqual(f["answer"], "NO")
        self.assertIn("two-way branch", f["because"])

    def test_the_2000_4000_answer_names_the_second_site(self):
        f = self.doc["feasibility_2000_4000"]
        self.assertEqual(len(f["what_would_actually_be_required"]), 2)
        self.assertIn("ENTRY image", f["what_would_actually_be_required"][1])

    def test_nothing_was_patched(self):
        self.assertTrue(self.doc["feasibility_2000_4000"]["nothing_was_patched"])
        self.assertIn("nothing was patched", self.doc["disclaimer"].lower())
        for banned in ("patch applied", "wrote to the image", "flashed"):
            self.assertNotIn(banned, self.md.lower(), banned)

    def test_the_unnamed_record_fields_are_not_named(self):
        """+0x20/+0x22 are outside what log 125 mapped; do not invent a name."""
        note = self.doc["threshold_addressing"]["note"]
        self.assertIn("does not name them", note)

    def test_the_document_states_no_device_was_accessed(self):
        self.assertIn("No device was accessed", self.doc["disclaimer"])
        self.assertIn("No device was accessed", self.md)

    def test_the_search_record_names_a_boundary_for_every_step(self):
        self.assertEqual(len(self.doc["search"]), len(m.SEARCH_STEPS))
        for s in self.doc["search"]:
            self.assertTrue(s["boundary"], s["step"])

    def test_the_json_is_deterministic(self):
        self.assertEqual(json.dumps(m.to_dict(), sort_keys=True),
                         json.dumps(m.to_dict(), sort_keys=True))

    def test_every_check_passes_on_the_real_evidence(self):
        failed = [c for c in self.doc["checks"] if not c["ok"]]
        self.assertEqual(failed, [], failed)

    def test_written_notes_are_current(self):
        for name, body in m.bodies().items():
            self.assertEqual((ROOT / "notes" / name).read_text(), body, name)

    def test_main_check_reports_current(self):
        out = subprocess.run(
            [sys.executable,
             str(ROOT / "tool" / "map_polling_rate_reader.py"), "--check"],
            capture_output=True, text=True, check=False)
        self.assertIn("reports_current=True stale=0", out.stdout)


if __name__ == "__main__":
    unittest.main()
