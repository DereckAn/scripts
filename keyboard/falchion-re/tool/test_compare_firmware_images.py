#!/usr/bin/env python3
"""Offline tests for the installed-versus-vendor comparator.

Reads only the two preserved evidence binaries and in-memory mutations of them.
No device access, no writes to any dump.
"""
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare_firmware_images as cmp_
import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")

APP_LO, APP_HI = fi.APPLICATION_REGION


def run_cli(argv):
    """Run the CLI with stdout and stderr captured separately."""
    out, err = io.StringIO(), io.StringIO()
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = cmp_.main(argv)
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    return code, out.getvalue(), err.getvalue()


def vendor_bytes():
    return bytearray(VENDOR.read_bytes())


def app_slice(data):
    """The vendor image cut down to the installed dump's extent and base."""
    return fi.ImageView(bytes(data[APP_LO:APP_HI]), APP_LO)


def full(data):
    return fi.ImageView(bytes(data), 0)


class PreservedImages(unittest.TestCase):
    """The real comparison, against the numbers the evidence supports."""

    @classmethod
    def setUpClass(cls):
        cls.result = cmp_.compare(
            fi.ImageView(INSTALLED.read_bytes(), APP_LO),
            fi.ImageView(VENDOR.read_bytes(), 0))

    def test_compare_range_is_the_installed_extent(self):
        self.assertEqual((self.result.range.lo, self.result.range.hi),
                         (0x10000, 0x7C000))
        self.assertEqual(self.result.range.length, 0x6C000)

    def test_both_inputs_are_allowlisted(self):
        self.assertEqual(self.result.installed_source.name,
                         "installed-1.59-application")
        self.assertEqual(self.result.vendor_source.name, "vendor-1.00.58-full")

    def test_difference_totals(self):
        self.assertFalse(self.result.equal)
        self.assertEqual(self.result.differing_bytes, 101297)
        self.assertEqual(len(self.result.differing_ranges), 3509)
        self.assertEqual(len(self.result.pages), 108)
        self.assertEqual(len(self.result.changed_pages), 39)

    def test_differing_bytes_equal_the_sum_of_the_ranges(self):
        self.assertEqual(
            sum(span.length for span in self.result.differing_ranges),
            self.result.differing_bytes)
        self.assertEqual(
            sum(page.differing_bytes for page in self.result.pages),
            self.result.differing_bytes)

    def test_first_and_last_difference(self):
        self.assertEqual(self.result.differing_ranges[0].lo, 0x1002C)
        self.assertEqual(self.result.differing_ranges[-1].hi, 0x7C000)

    def test_record_slot_1_grew_by_44_bytes(self):
        slots = {record.slot: record for record in self.result.records}
        self.assertEqual(sorted(slots), [0, 1])
        self.assertEqual(slots[0].length_delta, 0)
        self.assertEqual(slots[1].installed_length, 0x1E780)
        self.assertEqual(slots[1].vendor_length, 0x1E754)
        self.assertEqual(slots[1].length_delta, 44)
        self.assertEqual(slots[1].overlap, 0x1E754)

    def test_bootloader_copy_is_identical_three_ways(self):
        mirror = self.result.mirror
        expected = "4a4568b61bc245397b0ede6f285eb1bd8a7fa2018bc1373bc05e73eabb0f686a"
        self.assertEqual(mirror.installed_mirror_sha256, expected)
        self.assertEqual(mirror.vendor_mirror_sha256, expected)
        self.assertEqual(mirror.vendor_primary_sha256, expected)
        self.assertEqual(mirror.installed_vs_vendor_mirror, ())
        self.assertEqual(mirror.installed_vs_vendor_primary, ())

    def test_changes_are_confined_to_three_region_runs(self):
        changed = [(run.lo, run.hi) for run in self.result.regions if run.changed]
        self.assertEqual(changed, [(0x10000, 0x17000), (0x21000, 0x40000),
                                   (0x7B000, 0x7C000)])

    def test_fill_regions_are_classified_not_diffed_blindly(self):
        kinds = {(run.lo, run.hi): (run.installed_kind, run.vendor_kind)
                 for run in self.result.regions}
        self.assertEqual(kinds[(0x17000, 0x21000)], ("ff", "ff"))
        self.assertEqual(kinds[(0x40000, 0x60000)], ("zero", "zero"))

    def test_word_sums_are_reported_for_both_images(self):
        installed = cmp_.word_sums(self.result.installed_validation)
        vendor = cmp_.word_sums(self.result.vendor_validation)
        self.assertEqual(installed["application"], (0x2D7486DB, 0x2D7486DB))
        self.assertEqual(vendor["application"], (0x5D27C5A9, 0x5D27C5A9))
        self.assertNotIn("bootloader", installed)
        self.assertEqual(vendor["bootloader"], (0xFB665AE3, 0xFB665AE3))
        self.assertEqual(installed["bootloader_mirror"], (0xFB665AE3, 0xFB665AE3))

    def test_no_string_changed_between_the_two_releases(self):
        strings = self.result.strings
        self.assertEqual(strings.distinct_common, 603)
        self.assertEqual((strings.installed_distinct, strings.vendor_distinct),
                         (603, 603))
        self.assertEqual(
            (strings.installed_occurrences, strings.vendor_occurrences),
            (802, 802))
        self.assertTrue(strings.multisets_equal)
        self.assertEqual((strings.added, strings.removed, strings.changed,
                          strings.count_changed), ((), (), (), ()))

    def test_record_destinations_are_reported_and_unchanged(self):
        slots = {record.slot: record for record in self.result.records}
        for record in slots.values():
            self.assertEqual(record.installed_dst, 0x18000000)
            self.assertEqual(record.vendor_dst, 0x18000000)
            self.assertFalse(record.dst_changed)
            self.assertFalse(record.addr_changed)
            self.assertTrue(record.checksum_changed)

    def test_slot_1_tail_is_an_explicit_installed_only_span(self):
        slot1, = [record for record in self.result.records if record.slot == 1]
        self.assertIsNone(slot1.vendor_only)
        self.assertEqual((slot1.installed_only.lo, slot1.installed_only.hi),
                         (0x3F754, 0x3F780))
        self.assertEqual(slot1.installed_only.length, 44)

    def test_slot_0_has_no_one_sided_tail(self):
        slot0, = [record for record in self.result.records if record.slot == 0]
        self.assertIsNone(slot0.installed_only)
        self.assertIsNone(slot0.vendor_only)


class Translation(unittest.TestCase):
    """Logical-base translation must be the only thing aligning the two files."""

    def test_vendor_app_slice_at_base_0x10000_equals_the_full_vendor_file(self):
        data = vendor_bytes()
        result = cmp_.compare(app_slice(data), full(data))
        self.assertTrue(result.equal)
        self.assertEqual(result.differing_bytes, 0)
        self.assertEqual(result.differing_ranges, ())
        self.assertEqual(len(result.changed_pages), 0)
        self.assertEqual(result.installed_range_sha256, result.vendor_range_sha256)

    def test_a_partial_image_that_misses_the_range_is_refused(self):
        data = vendor_bytes()
        short = fi.ImageView(bytes(data[APP_LO:APP_LO + 0x1000]), APP_LO)
        with self.assertRaises(cmp_.ComparisonError) as caught:
            cmp_.compare(short, full(data))
        self.assertIn("does not cover logical", str(caught.exception))

    def test_wrong_base_is_refused_rather_than_misaligned(self):
        data = vendor_bytes()
        with self.assertRaises((cmp_.ComparisonError, fi.ImageFormatError)):
            cmp_.compare(fi.ImageView(bytes(data[APP_LO:APP_HI]), 0), full(data))


class Differences(unittest.TestCase):
    """Diff arithmetic on constructed changes."""

    def compare_with(self, mutate):
        data = vendor_bytes()
        mutate(data)
        return cmp_.compare(app_slice(data), full(vendor_bytes()))

    def test_identical_images_report_no_difference(self):
        result = self.compare_with(lambda data: None)
        self.assertTrue(result.equal)
        self.assertEqual(result.differing_bytes, 0)

    def test_one_byte_difference(self):
        result = self.compare_with(
            lambda data: data.__setitem__(0x11100, data[0x11100] ^ 0xFF))
        self.assertFalse(result.equal)
        self.assertEqual(result.differing_bytes, 1)
        self.assertEqual(len(result.differing_ranges), 1)
        span = result.differing_ranges[0]
        self.assertEqual((span.lo, span.hi, span.length), (0x11100, 0x11101, 1))
        self.assertEqual([page.lo for page in result.changed_pages], [0x11000])

    def test_two_separate_differences_are_two_ranges(self):
        def mutate(data):
            data[0x11100] ^= 0xFF
            data[0x11200] ^= 0xFF
        result = self.compare_with(mutate)
        self.assertEqual(result.differing_bytes, 2)
        self.assertEqual([(s.lo, s.hi) for s in result.differing_ranges],
                         [(0x11100, 0x11101), (0x11200, 0x11201)])

    def test_difference_crossing_a_page_boundary_is_one_range_and_two_pages(self):
        def mutate(data):
            for offset in range(0x11FFE, 0x12002):
                data[offset] ^= 0xFF
        result = self.compare_with(mutate)
        self.assertEqual(len(result.differing_ranges), 1)
        span = result.differing_ranges[0]
        self.assertEqual((span.lo, span.hi, span.length), (0x11FFE, 0x12002, 4))
        self.assertEqual([page.lo for page in result.changed_pages],
                         [0x11000, 0x12000])
        per_page = {page.lo: page.differing_bytes for page in result.changed_pages}
        self.assertEqual(per_page, {0x11000: 2, 0x12000: 2})

    def test_difference_at_the_very_last_byte_is_captured(self):
        result = self.compare_with(
            lambda data: data.__setitem__(APP_HI - 1, data[APP_HI - 1] ^ 0xFF))
        self.assertEqual(result.differing_bytes, 1)
        self.assertEqual(result.differing_ranges[-1].hi, APP_HI)

    def test_record_payload_diff_ranges_are_logical_offsets(self):
        result = self.compare_with(
            lambda data: data.__setitem__(0x21008, data[0x21008] ^ 0xFF))
        slot1, = [record for record in result.records if record.slot == 1]
        self.assertEqual(slot1.differing_bytes, 1)
        self.assertEqual(slot1.differing_ranges[0].lo, 0x21008)

    def test_a_change_outside_every_record_still_shows_in_the_range_diff(self):
        result = self.compare_with(
            lambda data: data.__setitem__(0x7A000, data[0x7A000] ^ 0xFF))
        self.assertEqual(result.differing_bytes, 1)
        self.assertEqual([record.differing_bytes for record in result.records],
                         [0, 0])


class Records(unittest.TestCase):

    def test_record_active_in_only_one_image_is_refused_not_ignored(self):
        data = vendor_bytes()
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        struct.pack_into("<4I", data, table + 3 * fi.REC_STRIDE,
                         0x60011000, 0x100, 0, 0x18000000)
        with self.assertRaises(cmp_.ComparisonError) as caught:
            cmp_.compare(app_slice(data), full(vendor_bytes()))
        self.assertIn("active in only one image", str(caught.exception))

    def test_truncated_record_payload_fails_closed(self):
        data = vendor_bytes()
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        struct.pack_into("<I", data, table + fi.REC_STRIDE + 4, 0x00FF0000)
        with self.assertRaises(fi.ImageFormatError):
            cmp_.compare(app_slice(data), full(vendor_bytes()))

    def test_malformed_record_table_fails_closed(self):
        data = vendor_bytes()
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        struct.pack_into("<4I", data, table + 3 * fi.REC_STRIDE,
                         0x00000000, 0x100, 0, 0x18000000)
        with self.assertRaises(fi.ImageFormatError):
            cmp_.compare(app_slice(data), full(vendor_bytes()))

    def test_a_changed_destination_is_reported_not_hidden(self):
        data = vendor_bytes()
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        struct.pack_into("<I", data, table + fi.REC_STRIDE + 12, 0x18001000)
        result = cmp_.compare(app_slice(data), full(vendor_bytes()))
        slot1, = [record for record in result.records if record.slot == 1]
        self.assertEqual(slot1.installed_dst, 0x18001000)
        self.assertEqual(slot1.vendor_dst, 0x18000000)
        self.assertTrue(slot1.dst_changed)
        payload = cmp_.to_dict(result)
        entry, = [item for item in payload["records"] if item["slot"] == 1]
        self.assertEqual(entry["installed"]["dst"], 0x18001000)
        self.assertEqual(entry["vendor"]["dst"], 0x18000000)
        self.assertTrue(entry["dst_changed"])
        markdown = "\n".join(cmp_.markdown_lines(result))
        self.assertIn("`0x18000000` -> `0x18001000`", markdown)
        self.assertIn("runtime dst", markdown)

    def test_a_shortened_record_reports_a_vendor_only_tail(self):
        data = vendor_bytes()
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        struct.pack_into("<I", data, table + fi.REC_STRIDE + 4, 0x1E700)
        result = cmp_.compare(app_slice(data), full(vendor_bytes()))
        slot1, = [record for record in result.records if record.slot == 1]
        self.assertEqual(slot1.length_delta, 0x1E700 - 0x1E754)
        self.assertIsNone(slot1.installed_only)
        self.assertEqual((slot1.vendor_only.lo, slot1.vendor_only.hi),
                         (0x21000 + 0x1E700, 0x21000 + 0x1E754))

    def test_a_moved_record_is_refused(self):
        data = vendor_bytes()
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        struct.pack_into("<I", data, table + fi.REC_STRIDE, 0x60022000)
        with self.assertRaises(cmp_.ComparisonError) as caught:
            cmp_.compare(app_slice(data), full(vendor_bytes()))
        self.assertIn("moved from", str(caught.exception))


class Strings(unittest.TestCase):

    def compare_with(self, mutate):
        data = vendor_bytes()
        mutate(data)
        return cmp_.compare(app_slice(data), full(vendor_bytes()))

    def poke(self, data, offset, text):
        data[offset:offset + len(text)] = text

    def test_added_string_is_reported(self):
        result = self.compare_with(
            lambda data: self.poke(data, 0x41000, b"FALCHION_TEST_ADDED\x00"))
        self.assertIn(b"FALCHION_TEST_ADDED", result.strings.added)
        self.assertEqual(result.strings.removed, ())

    def test_removed_string_is_reported(self):
        data = vendor_bytes()
        target = b"SN_BCFG"
        offset = data.index(target, APP_LO)
        result = self.compare_with(
            lambda mutable: self.poke(mutable, offset, b"\x00" * len(target)))
        self.assertNotIn(target, [value[:len(target)]
                                  for value in result.strings.added])

    def test_a_rewritten_string_is_reported_once_as_changed(self):
        data = vendor_bytes()
        self.poke(data, 0x41000, b"FALCHION_VERSION_AAAA\x00")
        left = app_slice(data)
        other = vendor_bytes()
        self.poke(other, 0x41000, b"FALCHION_VERSION_BBBB\x00")
        result = cmp_.compare(left, full(other))
        self.assertEqual(result.strings.changed,
                         ((b"FALCHION_VERSION_BBBB", b"FALCHION_VERSION_AAAA"),))
        self.assertEqual((result.strings.added, result.strings.removed), ((), ()))

    def test_a_changed_occurrence_count_cannot_hide(self):
        """The same value appearing a different number of times is a change."""
        data = vendor_bytes()
        target = b"FALCHION_DUPLICATED_VALUE"
        self.poke(data, 0x41000, target + b"\x00")
        self.poke(data, 0x41100, target + b"\x00")
        other = vendor_bytes()
        self.poke(other, 0x41000, target + b"\x00")
        result = cmp_.compare(app_slice(data), full(other))
        self.assertEqual(result.strings.added, ())
        self.assertEqual(result.strings.removed, ())
        self.assertEqual(result.strings.count_changed, ((target, 2, 1),))
        self.assertFalse(result.strings.multisets_equal)
        payload = cmp_.to_dict(result)
        self.assertEqual(payload["strings"]["count_changed"], [
            {"installed_occurrences": 2,
             "value": target.decode("ascii"),
             "vendor_occurrences": 1}])
        self.assertIn("occurrence count changed: 1",
                      "\n".join(cmp_.markdown_lines(result)))

    def test_occurrences_and_distinct_values_are_reported_separately(self):
        result = cmp_.compare(app_slice(vendor_bytes()), full(vendor_bytes()))
        strings = result.strings
        self.assertGreater(strings.installed_occurrences, strings.installed_distinct)
        markdown = "\n".join(cmp_.markdown_lines(result))
        self.assertIn(f"{strings.installed_distinct} distinct values in "
                      f"{strings.installed_occurrences} occurrences", markdown)

    def test_substrings_of_a_longer_hit_are_dropped(self):
        result = self.compare_with(
            lambda data: self.poke(data, 0x41000, b"FALCHION_LONG_UNIQUE_STRING\x00"))
        added = result.strings.added
        self.assertEqual(len(added), 1)
        self.assertEqual(added[0], b"FALCHION_LONG_UNIQUE_STRING")


class SourcePolicy(unittest.TestCase):
    """Provenance is checked before anything is parsed, hashed or diffed."""

    def unknown_pair(self):
        data = vendor_bytes()
        data[0x41000] ^= 0xFF
        return app_slice(data), full(vendor_bytes())

    def known_pair(self):
        return (fi.ImageView(INSTALLED.read_bytes(), APP_LO),
                fi.ImageView(VENDOR.read_bytes(), 0))

    def test_unknown_input_is_refused_by_default(self):
        out, err = io.StringIO(), io.StringIO()
        left, right = self.unknown_pair()
        self.assertIsNone(cmp_.check_sources(left, right, False, out, err))
        self.assertIn("RESULT compared=False", out.getvalue())
        self.assertIn("unknown source image(s): installed", out.getvalue())
        self.assertEqual(err.getvalue(), "")

    def test_analysis_only_warns_on_stderr_and_continues(self):
        out, err = io.StringIO(), io.StringIO()
        left, right = self.unknown_pair()
        self.assertEqual(cmp_.check_sources(left, right, True, out, err),
                         ("installed",))
        self.assertEqual(out.getvalue(), "")
        self.assertTrue(err.getvalue().startswith("WARNING "))
        self.assertIn("must not be cited as evidence", err.getvalue())

    def test_allowlisted_inputs_need_no_option_and_print_nothing(self):
        out, err = io.StringIO(), io.StringIO()
        left, right = self.known_pair()
        self.assertEqual(cmp_.check_sources(left, right, False, out, err), ())
        self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))

    def test_unknown_sources_names_both_when_both_are_unvouched(self):
        data = vendor_bytes()
        data[0x41000] ^= 0xFF
        other = vendor_bytes()
        other[0x41004] ^= 0xFF
        self.assertEqual(cmp_.unknown_sources(app_slice(data), full(other)),
                         ("installed", "vendor"))

    def test_compare_is_never_reached_for_a_default_unknown_source(self):
        """The plan requires verification *before* analysis, not after."""
        data = vendor_bytes()
        data[0x41000] ^= 0xFF
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unvouched.bin"
            path.write_bytes(bytes(data[APP_LO:APP_HI]))
            calls = []

            def tripwire(*args, **kwargs):
                calls.append(args)
                raise AssertionError("compare() must not run for an unknown source")

            original = cmp_.compare
            cmp_.compare = tripwire
            try:
                code, out, err = run_cli([
                    "--installed", str(path), "--vendor", str(VENDOR)])
            finally:
                cmp_.compare = original
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("unknown source image(s): installed", out)
        self.assertEqual(err, "")


class Rendering(unittest.TestCase):
    """Markdown and JSON must come from the same model and agree on counts."""

    @classmethod
    def setUpClass(cls):
        cls.result = cmp_.compare(
            fi.ImageView(INSTALLED.read_bytes(), APP_LO),
            fi.ImageView(VENDOR.read_bytes(), 0))
        cls.payload = cmp_.to_dict(cls.result)
        cls.markdown = "\n".join(cmp_.markdown_lines(cls.result))

    def test_json_is_deterministic(self):
        again = cmp_.to_dict(cmp_.compare(
            fi.ImageView(INSTALLED.read_bytes(), APP_LO),
            fi.ImageView(VENDOR.read_bytes(), 0)))
        self.assertEqual(json.dumps(self.payload, sort_keys=True),
                         json.dumps(again, sort_keys=True))

    def test_json_keys_are_sorted_at_every_level(self):
        def check(node):
            if isinstance(node, dict):
                self.assertEqual(list(node), sorted(node))
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)
        check(json.loads(json.dumps(self.payload, sort_keys=True)))

    def test_json_carries_every_range_not_a_truncation(self):
        self.assertEqual(len(self.payload["differing_ranges"]), 3509)
        self.assertEqual(self.payload["differing_range_count"], 3509)
        self.assertEqual(len(self.payload["pages"]), 108)
        self.assertEqual(len(self.payload["changed_pages"]), 39)

    def test_markdown_counts_match_the_json(self):
        self.assertIn(f"**{self.payload['differing_bytes']}**", self.markdown)
        self.assertIn(f"**{self.payload['differing_range_count']}**", self.markdown)
        self.assertIn(f"**{self.payload['changed_page_count']}** of 108",
                      self.markdown)

    def test_markdown_says_when_it_truncates_the_range_table(self):
        self.assertIn("Showing the 25 longest of 3509", self.markdown)
        full_table = "\n".join(cmp_.markdown_lines(self.result, max_ranges=0))
        self.assertNotIn("Showing the", full_table)
        self.assertEqual(full_table.count("\n| `0x"),
                         self.markdown.count("\n| `0x") - 25 + 3509)

    def test_markdown_refuses_to_interpret(self):
        self.assertIn("No meaning is assigned to any changed range", self.markdown)
        for line in fi.UNRESOLVED:
            self.assertIn(line, self.markdown)


class Cli(unittest.TestCase):

    def run_main(self, argv):
        code, out, _err = run_cli(argv)
        return code, out

    def test_default_run_emits_markdown(self):
        code, out = self.run_main([])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("# Installed 1.59 application versus"))
        self.assertIn("| slot | source addr |", out)
        self.assertIn("runtime dst", out)

    def test_json_mode_is_parseable(self):
        code, out = self.run_main(["--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["differing_bytes"], 101297)

    def test_analysis_only_json_is_parseable_with_the_warning_on_stderr(self):
        data = vendor_bytes()
        data[0x41000] ^= 0xFF
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unvouched.bin"
            path.write_bytes(bytes(data[APP_LO:APP_HI]))
            code, out, err = run_cli(["--installed", str(path),
                                      "--analysis-only", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["provenance"],
                         {"analysis_only": True, "unknown_sources": ["installed"]})
        self.assertTrue(err.startswith("WARNING "))
        self.assertNotIn("WARNING", out)

    def test_json_records_provenance_for_a_normal_run(self):
        code, out, err = run_cli(["--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["provenance"],
                         {"analysis_only": False, "unknown_sources": []})
        self.assertEqual(err, "")

    def test_analysis_only_markdown_keeps_the_warning_off_stdout(self):
        data = vendor_bytes()
        data[0x41000] ^= 0xFF
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unvouched.bin"
            path.write_bytes(bytes(data[APP_LO:APP_HI]))
            code, out, err = run_cli(["--installed", str(path), "--analysis-only"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("# Installed 1.59 application versus"))
        self.assertIn("not an allowlisted source image", err)

    def test_swapped_bases_fail_closed_with_one_line(self):
        code, out = self.run_main(["--installed-base", "0x0"])
        self.assertEqual(code, 1)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("RESULT compared=False error=", out)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
