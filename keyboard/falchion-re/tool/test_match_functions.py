#!/usr/bin/env python3
"""Offline tests for the cross-release function matcher.

Uses synthetic inventories for the matching rules and the two real inventories
under `ghidra/inventories/` for the headline numbers, when they are present.
No device access.
"""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import match_functions as mf

ROOT = Path(__file__).resolve().parent.parent
INVENTORIES = ROOT / "ghidra/inventories"

HEADER = ("PROGRAM synthetic.bin\n"
          "IMAGE_BASE 00000000\n"
          "LANGUAGE ARM:LE:32:Cortex\n")


def func(entry, *, size=0x10, insns=8, blocks=2, bytes_sha="b" * 64,
         shape_sha="s" * 64, callers=1, callees="", consts="0x1,0x2",
         strings="", name=None, ranges=None):
    name = name or f"FUN_{entry:08x}"
    if ranges is None:
        ranges = ((entry, entry + size),)
    text = ";".join(f"{lo:08x}-{hi:08x}" for lo, hi in ranges)
    return (f"FUNC entry={entry:08x} name={name} size=0x{size:x} "
            f"ranges={text} insns={insns} "
            f"blocks={blocks} bytes_sha={bytes_sha} shape_sha={shape_sha} "
            f"callers={callers} callees={callees} consts={consts} "
            f"strings={strings}")


def inventory(*lines):
    return HEADER + "\n".join(lines) + "\nRESULT functions=%d\n" % len(lines)


def report(vendor_lines, installed_lines, base=0, flash_base=0,
           vendor_bytes=None, installed_bytes=None):
    return mf.build_report("synthetic", inventory(*vendor_lines),
                           inventory(*installed_lines), base, flash_base,
                           vendor_bytes, installed_bytes)


def confidences(result):
    return {(m.vendor.entry if m.vendor else None,
             m.installed.entry if m.installed else None): m.confidence
            for m in result.matches}


class Parsing(unittest.TestCase):

    def test_fields_round_trip(self):
        records, header = mf.parse_inventory(inventory(
            func(0x100, size=0x24, insns=9, blocks=3, callers=2,
                 callees="00000200,00000300", consts="0x1,0xff",
                 strings="hello,world")))
        self.assertEqual(header["program"], "synthetic.bin")
        record, = records
        self.assertEqual(record.entry, 0x100)
        self.assertEqual(record.size, 0x24)
        self.assertEqual(record.callees, (0x200, 0x300))
        self.assertEqual(record.consts, frozenset({0x1, 0xFF}))
        self.assertEqual(record.strings, frozenset({"hello", "world"}))

    def test_an_inventory_without_functions_is_refused(self):
        with self.assertRaises(ValueError):
            mf.parse_inventory(HEADER)

    def test_discontiguous_ranges_round_trip(self):
        records, _header = mf.parse_inventory(inventory(
            func(0x100, size=0x18, ranges=((0x100, 0x110), (0x140, 0x148)))))
        record, = records
        self.assertEqual(record.ranges, ((0x100, 0x110), (0x140, 0x148)))
        self.assertFalse(record.contiguous)
        self.assertEqual(record.extent, (0x100, 0x148))
        self.assertEqual(record.size, 0x18)

    def test_an_inventory_without_ranges_is_refused(self):
        """Old inventories predate real body ranges and must not be trusted."""
        legacy = (HEADER + "FUNC entry=00000100 name=F size=0x10 insns=4 "
                  "blocks=1 bytes_sha=" + "a" * 64 + " shape_sha=" + "b" * 64
                  + " callers=0 callees= consts= strings=\n")
        with self.assertRaises(ValueError) as caught:
            mf.parse_inventory(legacy)
        self.assertIn("predates real body ranges", str(caught.exception))

    def test_ranges_that_disagree_with_size_are_refused(self):
        broken = inventory(func(0x100, size=0x20,
                                ranges=((0x100, 0x110), (0x140, 0x148))))
        with self.assertRaises(ValueError) as caught:
            mf.parse_inventory(broken)
        self.assertIn("body ranges sum to", str(caught.exception))

    def test_body_bytes_skips_the_hole(self):
        records, _header = mf.parse_inventory(inventory(
            func(0x0, size=0x8, ranges=((0x0, 0x4), (0x8, 0xC)))))
        record, = records
        data = bytes(range(0x10))
        self.assertEqual(record.body_bytes(data, 0),
                         bytes([0, 1, 2, 3, 8, 9, 10, 11]))


class Tiers(unittest.TestCase):

    def test_identical_bytes_match_even_when_relocated(self):
        result = report([func(0x100, bytes_sha="a" * 64)],
                        [func(0x180, bytes_sha="a" * 64)])
        match, = result.matches
        self.assertEqual(match.confidence, "identical")
        self.assertTrue(match.moved)
        self.assertFalse(match.changed)
        self.assertIn("relocated", match.reason)

    def test_same_shape_different_bytes_is_structural(self):
        result = report([func(0x100, bytes_sha="a" * 64, shape_sha="z" * 64)],
                        [func(0x100, bytes_sha="c" * 64, shape_sha="z" * 64)])
        match, = result.matches
        self.assertEqual(match.confidence, "structural")
        self.assertTrue(match.changed)

    def test_duplicate_bytes_are_not_claimed_as_identical(self):
        """An ambiguous body hash must not produce a confident pairing."""
        result = report(
            [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x200, bytes_sha="a" * 64, shape_sha="p" * 64)],
            [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x200, bytes_sha="a" * 64, shape_sha="p" * 64)])
        self.assertNotIn("identical",
                         [match.confidence for match in result.matches])

    def test_scored_match_is_tentative(self):
        result = report(
            [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64, size=0x20,
                  insns=10, blocks=3, consts="0x1,0x2,0x3")],
            [func(0x100, bytes_sha="b" * 64, shape_sha="q" * 64, size=0x20,
                  insns=10, blocks=3, consts="0x1,0x2,0x3")])
        match, = result.matches
        self.assertEqual(match.confidence, "tentative")
        self.assertGreaterEqual(match.score, mf.TENTATIVE_FLOOR)

    def test_a_near_tie_stays_unmatched(self):
        """Two equally plausible candidates must not be guessed between."""
        vendor = [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64)]
        installed = [func(0x200, bytes_sha="b" * 64, shape_sha="q" * 64),
                     func(0x300, bytes_sha="c" * 64, shape_sha="r" * 64)]
        result = report(vendor, installed)
        self.assertEqual(
            sorted(match.confidence for match in result.matches),
            ["unmatched", "unmatched", "unmatched"])

    def test_unmatched_is_reported_from_both_sides(self):
        result = report(
            [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64, size=0x8,
                  insns=2, blocks=1, consts="0x1")],
            [func(0x900, bytes_sha="b" * 64, shape_sha="q" * 64, size=0x400,
                  insns=300, blocks=90, consts="0xdead")])
        confidence = confidences(result)
        self.assertEqual(confidence[(0x100, None)], "unmatched")
        self.assertEqual(confidence[(None, 0x900)], "unmatched")


class Shift(unittest.TestCase):

    def anchored(self, extra_vendor=(), extra_installed=()):
        vendor = [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64),
                  func(0x200, bytes_sha="b" * 64, shape_sha="q" * 64),
                  func(0x300, bytes_sha="c" * 64, shape_sha="r" * 64)]
        installed = [func(0x12C, bytes_sha="a" * 64, shape_sha="p" * 64),
                     func(0x22C, bytes_sha="b" * 64, shape_sha="q" * 64),
                     func(0x32C, bytes_sha="c" * 64, shape_sha="r" * 64)]
        return report(list(vendor) + list(extra_vendor),
                      list(installed) + list(extra_installed))

    def test_dominant_shift_is_measured_from_confident_matches(self):
        self.assertEqual(self.anchored().dominant_shift, 0x2C)

    def test_a_single_pair_does_not_establish_a_shift(self):
        result = report([func(0x100, bytes_sha="a" * 64)],
                        [func(0x180, bytes_sha="a" * 64)])
        self.assertIsNone(result.dominant_shift)

    def test_shift_consistent_duplicates_become_tentative_not_identical(self):
        result = self.anchored(
            extra_vendor=[func(0x400, bytes_sha="d" * 64, shape_sha="t" * 64),
                          func(0x500, bytes_sha="d" * 64, shape_sha="t" * 64)],
            extra_installed=[func(0x42C, bytes_sha="d" * 64, shape_sha="t" * 64),
                             func(0x52C, bytes_sha="d" * 64, shape_sha="t" * 64)])
        confidence = confidences(result)
        self.assertEqual(confidence[(0x400, 0x42C)], "tentative")
        self.assertEqual(confidence[(0x500, 0x52C)], "tentative")
        for match in result.matches:
            if match.confidence == "tentative":
                self.assertIn("byte-identical and consistent with the +0x2c shift",
                              match.reason)

    def test_a_shift_consistent_pair_with_different_bytes_is_not_taken(self):
        result = self.anchored(
            extra_vendor=[func(0x400, bytes_sha="d" * 64, shape_sha="t" * 64,
                               size=0x8, insns=2, blocks=1, consts="0x1"),
                          func(0x500, bytes_sha="d" * 64, shape_sha="t" * 64,
                               size=0x8, insns=2, blocks=1, consts="0x1")],
            extra_installed=[func(0x42C, bytes_sha="e" * 64, shape_sha="t" * 64,
                                  size=0x300, insns=200, blocks=70,
                                  consts="0xbeef"),
                             func(0x52C, bytes_sha="e" * 64, shape_sha="t" * 64,
                                  size=0x300, insns=200, blocks=70,
                                  consts="0xbeef")])
        confidence = confidences(result)
        self.assertNotIn((0x400, 0x42C), confidence)


class DiscontiguousBodies(unittest.TestCase):
    """Body bytes and gaps must come from the real ranges, not entry+size."""

    def test_body_diff_reads_the_real_ranges_not_the_span(self):
        vendor = bytearray(0x20)
        installed = bytearray(0x20)
        installed[0x14] = 0xFF          # inside the hole, not inside the body
        ranges = ((0x0, 0x10), (0x18, 0x20))
        result = report(
            [func(0x0, size=0x18, ranges=ranges, bytes_sha="a" * 64,
                  shape_sha="p" * 64)],
            [func(0x0, size=0x18, ranges=ranges, bytes_sha="a" * 64,
                  shape_sha="p" * 64)],
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        match, = result.matches
        self.assertEqual(match.differing_bytes, 0)
        region, = result.data_regions
        self.assertEqual((region.vendor_lo, region.vendor_hi), (0x14, 0x15))

    def test_a_hole_is_treated_as_data_not_as_code(self):
        vendor = bytearray(0x20)
        installed = bytearray(0x20)
        installed[0x12] = 0xFF
        ranges = ((0x0, 0x10), (0x18, 0x20))
        result = report(
            [func(0x0, size=0x18, ranges=ranges, bytes_sha="a" * 64,
                  shape_sha="p" * 64)],
            [func(0x0, size=0x18, ranges=ranges, bytes_sha="a" * 64,
                  shape_sha="p" * 64)],
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        self.assertEqual(mf.uncovered_spans(0, 0x20, [
            mf.parse_inventory(inventory(
                func(0x0, size=0x18, ranges=ranges)))[0][0]]),
            ((0x10, 0x18),))
        self.assertEqual(len(result.data_regions), 1)

    def test_a_different_range_shape_is_not_byte_compared(self):
        vendor = bytes(0x20)
        installed = bytes(0x20)
        result = report(
            [func(0x0, size=0x18, ranges=((0x0, 0x10), (0x18, 0x20)),
                  bytes_sha="a" * 64, shape_sha="p" * 64)],
            [func(0x0, size=0x18, ranges=((0x0, 0x18),),
                  bytes_sha="a" * 64, shape_sha="p" * 64)],
            vendor_bytes=vendor, installed_bytes=installed)
        match, = result.matches
        self.assertIsNone(match.differing_bytes)

    def test_discontiguity_is_counted_and_reported(self):
        result = report(
            [func(0x0, size=0x18, ranges=((0x0, 0x10), (0x18, 0x20)),
                  bytes_sha="a" * 64, shape_sha="p" * 64)],
            [func(0x0, size=0x18, ranges=((0x0, 0x10), (0x18, 0x20)),
                  bytes_sha="a" * 64, shape_sha="p" * 64)])
        self.assertEqual(result.discontiguous, (1, 1))
        self.assertIn("DISCONTIGUOUS_BODIES vendor=1 installed=1",
                      "\n".join(mf.report_lines(result)))


class UncoveredSpans(unittest.TestCase):

    def records(self, *lines):
        return mf.parse_inventory(inventory(*lines))[0]

    def test_spans_are_the_complement_of_the_merged_ranges(self):
        records = self.records(
            func(0x10, size=0x10, ranges=((0x10, 0x20),)),
            func(0x18, size=0x10, ranges=((0x18, 0x28),)))
        self.assertEqual(mf.uncovered_spans(0x0, 0x40, records),
                         ((0x0, 0x10), (0x28, 0x40)))

    def test_spans_that_cannot_be_paired_safely_are_never_compared(self):
        """A relocated lone function leaves no span pairing that checks out."""
        vendor = bytes(0x40)
        installed = bytes(0x40)
        result = report(
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64)],
            [func(0x10, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64)],
            vendor_bytes=vendor, installed_bytes=installed)
        self.assertEqual(result.spans_compared, 0)
        self.assertEqual(result.data_regions, ())
        self.assertEqual(len(result.unaligned_gaps), 2)
        self.assertIn("a span is compared only when its anchor key",
                      "\n".join(mf.report_lines(result)))

    def test_a_mispaired_span_is_caught_by_the_distance_check(self):
        """Same anchor key and same length, but the wrong distance past it."""
        vendor = bytearray(0x40)
        installed = bytearray(0x40)
        result = report(
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x28, size=0x18, bytes_sha="b" * 64, shape_sha="q" * 64)],
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x20, size=0x20, bytes_sha="b" * 64, shape_sha="q" * 64)],
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        gap, = result.unaligned_gaps
        self.assertEqual((gap.vendor_lo, gap.vendor_hi), (0x10, 0x28))
        self.assertEqual((gap.installed_lo, gap.installed_hi), (0x10, 0x20))
        self.assertEqual(result.spans_compared, 0)


class Gaps(unittest.TestCase):
    """Gaps are aligned by the functions bracketing them, never by raw offset."""

    def test_an_equal_length_gap_is_compared(self):
        vendor = bytearray(0x40)
        installed = bytearray(0x40)
        installed[0x20] = 0xFF
        result = report(
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x30, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x30, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        region, = result.data_regions
        self.assertEqual((region.vendor_lo, region.vendor_hi), (0x20, 0x21))
        self.assertEqual((region.installed_lo, region.installed_hi), (0x20, 0x21))
        self.assertEqual(region.shift, 0)
        self.assertEqual(result.unaligned_gaps, ())

    def test_a_leading_shift_pairs_by_anchor_and_flags_the_extra_span(self):
        """Anchor keying survives one side gaining a span at the head."""
        vendor = bytearray(0x40)
        installed = bytearray(0x40)
        vendor[0x20] = 0x11
        installed[0x24] = 0x11
        result = report(
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x30, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            [func(0x4, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x34, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        self.assertEqual((result.span_counts[0], result.span_counts[1]), (1, 2))
        # The span that both sides share pairs correctly and its differing byte
        # sits at the same aligned position, so nothing is reported as changed.
        self.assertEqual(result.spans_compared, 1)
        self.assertEqual(result.data_regions, ())
        # The extra head span exists only on the installed side.
        gap, = result.unaligned_gaps
        self.assertEqual((gap.installed_lo, gap.installed_hi), (0x0, 0x4))

    def test_a_shift_that_preserves_span_counts_is_compared_aligned(self):
        """The real Candidate B case: same span count, spans shifted."""
        vendor = bytearray(0x40)
        installed = bytearray(0x40)
        vendor[0x18] = 0x11
        installed[0x1C] = 0x11
        result = report(
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x20, size=0x20, bytes_sha="b" * 64, shape_sha="q" * 64)],
            [func(0x0, size=0x14, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x24, size=0x1C, bytes_sha="b" * 64, shape_sha="q" * 64)],
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        self.assertEqual((result.span_counts[0], result.span_counts[1]), (1, 1))
        self.assertEqual(result.spans_compared, 1)
        # vendor span 0x10..0x20 (0x10) vs installed 0x14..0x24 (0x10): the
        # differing byte is at the same aligned position, so nothing is reported.
        self.assertEqual(result.data_regions, ())
        self.assertEqual(result.unaligned_gaps, ())

    def test_an_unequal_gap_is_reported_not_compared(self):
        vendor = bytes(0x40)
        installed = bytes(0x50)
        result = report(
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x30, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            [func(0x0, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x40, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            vendor_bytes=vendor, installed_bytes=installed)
        self.assertEqual(result.data_regions, ())
        gap, = result.unaligned_gaps
        self.assertEqual((gap.vendor_length, gap.installed_length), (0x20, 0x30))

    def test_flash_addresses_are_translated(self):
        vendor = bytearray(0x40)
        installed = bytearray(0x40)
        installed[0x20] = 0xFF
        result = report(
            [func(0x18000000, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x18000030, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            [func(0x18000000, size=0x10, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x18000030, size=0x10, bytes_sha="b" * 64, shape_sha="q" * 64)],
            base=0x18000000, flash_base=0x21000,
            vendor_bytes=bytes(vendor), installed_bytes=bytes(installed))
        region, = result.data_regions
        self.assertEqual(region.flash_lo, 0x21020)


class Reporting(unittest.TestCase):

    def build(self):
        return report(
            [func(0x100, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x200, bytes_sha="b" * 64, shape_sha="q" * 64),
             func(0x300, bytes_sha="c" * 64, shape_sha="r" * 64),
             func(0x900, bytes_sha="x" * 64, shape_sha="y" * 64, size=0x8,
                  insns=2, blocks=1, consts="0x1")],
            [func(0x12C, bytes_sha="a" * 64, shape_sha="p" * 64),
             func(0x22C, bytes_sha="b" * 64, shape_sha="q" * 64),
             func(0x32C, bytes_sha="c" * 64, shape_sha="r" * 64)])

    def test_must_not_assume_equal_lists_relocations_and_absences(self):
        entries = mf.must_not_assume_equal(self.build())
        by_vendor = {vendor: (installed, reason)
                     for vendor, installed, reason in entries}
        self.assertEqual(by_vendor[0x100][0], 0x12C)
        self.assertIn("relocated", by_vendor[0x100][1])
        self.assertIsNone(by_vendor[0x900][0])
        self.assertIn("no installed counterpart", by_vendor[0x900][1])

    def test_review_ranking_puts_unmatched_first(self):
        ranked = mf.review_ranking(self.build())
        self.assertEqual(ranked[0].confidence, "unmatched")

    def test_json_is_deterministic_and_sorted(self):
        first = json.dumps(mf.to_dict(self.build()), sort_keys=True)
        second = json.dumps(mf.to_dict(self.build()), sort_keys=True)
        self.assertEqual(first, second)

        def check(node):
            if isinstance(node, dict):
                self.assertEqual(list(node), sorted(node))
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)
        check(json.loads(first))

    def test_report_states_its_limitations_accurately(self):
        text = "\n".join(mf.report_lines(self.build()))
        self.assertIn("spans no real body range covers", text)
        self.assertIn("never the sole signal", text)
        self.assertIn("can never raise a pairing above tentative", text)
        self.assertIn("DOMINANT_SHIFT", text)
        self.assertIn("DISCONTIGUOUS_BODIES", text)
        self.assertNotIn("only ever reported", text)


@unittest.skipUnless((INVENTORIES / "vendor_a.txt").exists(),
                     "run the Ghidra inventory step first")
class RealInventories(unittest.TestCase):
    """Headline numbers for the two real program pairs."""

    def load(self, tag, base, flash_base, vendor_bin, installed_bin):
        return mf.build_report(
            tag,
            (INVENTORIES / f"vendor_{tag}.txt").read_text(),
            (INVENTORIES / f"installed_{tag}.txt").read_text(),
            base, flash_base,
            (ROOT / "ghidra/imports" / vendor_bin).read_bytes(),
            (ROOT / "ghidra/imports" / installed_bin).read_bytes())

    def test_candidate_a_is_fully_matched_with_no_relocation(self):
        result = self.load(
            "a", 0x0, 0x11000,
            "vendor_app_a_slot0_flash11000_dst00000000_len058ac_a0f4ddd2.bin",
            "installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin")
        counts = mf.tally(result)
        self.assertEqual(counts.get("unmatched", 0), 0)
        self.assertEqual(result.vendor_count, result.installed_count)
        self.assertEqual(result.dominant_shift, 0)
        self.assertEqual(result.unaligned_gaps, (),
                         "every Candidate A span pairs cleanly")
        self.assertEqual(result.spans_compared, result.span_counts[0])
        body = sum(match.differing_bytes or 0 for match in result.matches)
        data = sum(region.length for region in result.data_regions)
        self.assertEqual(body + data, 131,
                         "must equal the slot-0 differing bytes from log 96")
        # The body/data split moves as the analysed function set grows, so only
        # the total is pinned. It was 0/131 before Phase 5A seeded the pointer
        # table targets and 2/129 after.
        self.assertLess(body, 50, "Candidate A's changed bytes are mostly data")

    def test_candidate_b_relocates_by_0x2c_and_is_fully_matched(self):
        result = self.load(
            "b", 0x18000000, 0x21000,
            "vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin",
            "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin")
        counts = mf.tally(result)
        self.assertEqual(counts.get("unmatched", 0), 0)
        self.assertEqual(result.dominant_shift, 0x2C)
        self.assertEqual(result.vendor_count, result.installed_count)

    def test_candidate_b_growth_is_distributed_not_one_insertion(self):
        """Log 98/99 read the growth as a single 44-byte gap; it is not.

        With the vector handlers seeded the function set roughly doubles and the
        same bytes resolve into code plus several smaller spans.
        """
        result = self.load(
            "b", 0x18000000, 0x21000,
            "vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin",
            "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin")
        self.assertGreater(len(result.unaligned_gaps), 1)
        size_delta = sum(match.installed.size - match.vendor.size
                         for match in result.matches
                         if match.vendor is not None
                         and match.installed is not None)
        self.assertGreater(size_delta, 0,
                           "matched bodies account for part of the growth")
        self.assertLess(result.spans_compared, result.span_counts[0],
                        "some spans cannot be paired safely, so the aligned "
                        "total is a lower bound")

    def test_candidate_b_aligned_change_is_far_below_the_raw_count(self):
        result = self.load(
            "b", 0x18000000, 0x21000,
            "vendor_app_b_slot1_flash21000_dst18000000_len1e354_aafcf2fd.bin",
            "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin")
        body = sum(match.differing_bytes or 0 for match in result.matches)
        data = sum(region.length for region in result.data_regions)
        self.assertLess(body + data, 5000,
                        "the aligned change must stay far below log 96's "
                        "101,112 raw differing bytes")
        self.assertGreater(body + data, 0)


if __name__ == "__main__":
    unittest.main()
