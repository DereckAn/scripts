#!/usr/bin/env python3
"""Offline tests for the installed record extractor and runtime map.

Reads only the two preserved evidence binaries and in-memory mutations of them.
Writes only into a temporary directory. No device access.
"""
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_installed_records as ex
import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")


def installed_view():
    return fi.ImageView(INSTALLED.read_bytes(), 0x10000)


def vendor_view():
    return fi.ImageView(VENDOR.read_bytes(), 0)


def mutated(view, patch):
    data = bytearray(view.data)
    patch(data, view.base)
    return fi.ImageView(bytes(data), view.base)


class InstalledImage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.view = installed_view()
        cls.result = ex.extract(cls.view)

    def test_every_check_passes(self):
        failed = [check.name for check in self.result.checks if not check.ok]
        self.assertEqual(failed, [])

    def test_region_table_is_located_by_structure(self):
        self.assertEqual(self.result.region_table, 0x16750)

    def test_three_regions_with_identified_handlers(self):
        self.assertEqual(
            [(region.index, region.src, region.dst, region.size,
              region.handler_name) for region in self.result.regions],
            [(0, 0x60021000, 0x18000000, 0x1E380, "__scatterload_copy"),
             (1, 0x6003F380, 0x1801E380, 0xB04, "__scatterload_decompress"),
             (2, 0x6003F780, 0x1801EE84, 0x172E4, "__scatterload_zeroinit")])

    def test_runtime_ranges_are_contiguous_and_end_at_the_initial_sp(self):
        ranges = self.result.runtime
        self.assertEqual(ranges[0].lo, 0x18000000)
        for earlier, later in zip(ranges, ranges[1:]):
            self.assertEqual(earlier.hi, later.lo)
        self.assertEqual(ranges[-1].hi, self.result.entry_sp)
        self.assertEqual(self.result.entry_sp, 0x18036168)

    def test_only_the_decompressed_range_is_unmaterialized(self):
        unmaterialized = [(item.lo, item.hi) for item in self.result.runtime
                          if not item.materialized]
        self.assertEqual(unmaterialized, [(0x1801E380, 0x1801EE84)])

    def test_every_runtime_range_cites_its_own_descriptor_address(self):
        table = self.result.region_table
        cited = set()
        for item in self.result.runtime:
            self.assertIn("Candidate A region", item.basis)
            for index in range(len(self.result.regions)):
                address = f"0x{table + index * ex.REGION_ENTRY_SIZE:x}"
                if address in item.basis:
                    cited.add(address)
                    break
            else:
                self.fail(f"no descriptor address cited in: {item.basis}")
        self.assertEqual(len(cited), len(self.result.regions))

    def test_slices_named_for_slot_source_destination_length_and_hash(self):
        names = [item.name for item in self.result.slices]
        self.assertEqual(names, [
            "installed_app_a_slot0_flash11000_dst00000000_len058ac_f093979a.bin",
            "installed_rec1_slot1_flash21000_dstNA_len1e780_ccbd61f8.bin",
            "installed_app_b_slot1_flash21000_dst18000000_len1e380_be463863.bin",
        ])

    def test_every_active_record_is_extracted_in_full(self):
        """Not just the loadable part: every active record byte must be on disk."""
        records = fi.parse(self.view).records
        covered = ex.merge_spans(
            (item.source_lo, item.source_hi) for item in self.result.slices)
        for record in records:
            self.assertTrue(
                any(lo <= record.flash_off and record.flash_end <= hi
                    for lo, hi in covered),
                f"record slot {record.index} "
                f"0x{record.flash_off:x}..0x{record.flash_end:x} not covered "
                f"by {covered}")
        full = [item for item in self.result.slices
                if (item.source_lo, item.source_hi) == (0x21000, 0x3F780)]
        self.assertEqual(len(full), 1)
        self.assertIsNone(full[0].import_base)
        self.assertIn("not one runtime image", full[0].role)

    def test_the_compressed_tail_is_only_in_the_full_record_slice(self):
        spans = {(item.source_lo, item.source_hi) for item in self.result.slices}
        self.assertIn((0x21000, 0x3F780), spans)
        self.assertIn((0x21000, 0x3F380), spans)

    def test_every_extracted_byte_round_trips_to_its_source(self):
        for item in self.result.slices:
            data = self.view.read(item.source_lo, item.length)
            self.assertEqual(hashlib.sha256(data).hexdigest(), item.sha256)
            self.assertEqual(len(data), item.length)

    def test_entry_slice_import_base_is_zero_with_a_stated_basis(self):
        entry = self.result.slices[0]
        self.assertEqual(entry.import_base, 0x0)
        self.assertIn("linked at 0", entry.import_base_basis)
        self.assertIn("0x000014a9", entry.import_base_basis)

    def test_payload_slice_import_base_comes_from_the_scatter_region(self):
        payload = self.result.slices[2]
        self.assertEqual(payload.import_base, 0x18000000)
        self.assertIn("region 0 copies flash 0x21000..0x3f380",
                      payload.import_base_basis)

    def test_coverage_tiles_the_whole_image_without_gaps_or_overlap(self):
        runs = self.result.coverage
        self.assertEqual(runs[0].lo, self.view.base)
        self.assertEqual(runs[-1].hi, self.view.end)
        for earlier, later in zip(runs, runs[1:]):
            self.assertEqual(earlier.hi, later.lo)
        self.assertEqual(sum(run.length for run in runs), self.view.size)

    def test_fill_classification_marks_the_padding(self):
        fills = {(run.lo, run.hi): run.fill for run in self.result.coverage}
        self.assertEqual(fills[(0x168AC, 0x21000)], "ff")
        self.assertEqual(fills[(0x100A4, 0x11000)], "zero")

    def test_record_word_at_0xc_is_flagged_as_not_recovered_behaviour(self):
        text = "\n".join(ex.report_lines(self.result))
        self.assertIn("record word at +0xc is not read by FUN_0000511c", text)


class VendorImage(unittest.TestCase):
    """The same locator must work on the other release without vendor constants."""

    @classmethod
    def setUpClass(cls):
        cls.result = ex.extract(vendor_view())

    def test_every_check_passes(self):
        failed = [check.name for check in self.result.checks if not check.ok]
        self.assertEqual(failed, [])

    def test_vendor_full_record_slice_carries_the_vendor_length(self):
        names = [item.name for item in self.result.slices]
        self.assertIn(
            "vendor_rec1_slot1_flash21000_dstNA_len1e754_8fe68a13.bin", names)

    def test_vendor_regions_differ_in_size_but_share_the_structure(self):
        self.assertEqual(
            [(region.size, region.handler_name) for region in self.result.regions],
            [(0x1E354, "__scatterload_copy"), (0xB04, "__scatterload_decompress"),
             (0x172E8, "__scatterload_zeroinit")])
        self.assertEqual(self.result.entry_sp, 0x18036140)

    def test_slice_prefix_names_the_source_release(self):
        for item in self.result.slices:
            self.assertTrue(item.name.startswith("vendor_"), item.name)


class Refusals(unittest.TestCase):
    """Every unsupported situation must fail closed, not emit a partial map."""

    def test_no_region_table_is_refused(self):
        def patch(data, base):
            # Break record 1's address so no descriptor can reference it.
            table = fi.FWIN_OFF + fi.FWIN_REC0_OFF - base
            struct.pack_into("<I", data, table + fi.REC_STRIDE, 0x60023000)
        with self.assertRaises((ex.ExtractError, fi.ImageFormatError)):
            ex.extract(mutated(installed_view(), patch))

    def test_a_broken_stack_pointer_relationship_is_reported_as_a_failure(self):
        def patch(data, base):
            struct.pack_into("<I", data, 0x11000 - base, 0x18030000)
        result = ex.extract(mutated(installed_view(), patch))
        failed = [check.name for check in result.checks if not check.ok]
        self.assertTrue(any("initial stack pointer" in name for name in failed),
                        failed)

    def test_an_unknown_handler_is_reported_not_silently_accepted(self):
        def patch(data, base):
            struct.pack_into("<I", data, 0x16750 - base + 12, 0x00000200)
        result = ex.extract(mutated(installed_view(), patch))
        failed = [check.name for check in result.checks if not check.ok]
        self.assertTrue(any("handler" in name for name in failed), failed)
        self.assertIn("unidentified",
                      "\n".join(ex.report_lines(result)))

    def test_a_non_tiling_record_is_reported(self):
        def patch(data, base):
            struct.pack_into("<I", data, 0x16750 - base + 8, 0x1E000)
        result = ex.extract(mutated(installed_view(), patch))
        failed = [check.name for check in result.checks if not check.ok]
        self.assertTrue(any("tile record slot 1" in name for name in failed),
                        failed)


class Writing(unittest.TestCase):

    def test_write_emits_exactly_the_named_slices(self):
        view = installed_view()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = ex.extract(view, out, write=True)
            written = sorted(path.name for path in out.iterdir())
            self.assertEqual(written, sorted(item.name for item in result.slices))
            for item in result.slices:
                data = (out / item.name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), item.sha256)
                self.assertEqual(data, view.read(item.source_lo, item.length))

    def test_write_is_refused_when_any_check_fails(self):
        """A failed check means the map is untrustworthy: emit nothing."""
        def patch(data, base):
            struct.pack_into("<I", data, 0x11000 - base, 0x18030000)
        view = mutated(installed_view(), patch)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with self.assertRaises(ex.ExtractError) as caught:
                ex.extract(view, out, write=True)
            self.assertIn("refusing to write slices", str(caught.exception))
            self.assertEqual(list(out.iterdir()), [])

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ex.extract(installed_view(), out, write=False)
            self.assertEqual(list(out.iterdir()), [])

    def test_cli_refuses_to_write_under_dumps(self):
        code, out, _err = run_cli([
            str(INSTALLED), "--base", "0x10000", "--write",
            "--out", str(ROOT / "dumps/device")])
        self.assertEqual(code, 1)
        self.assertIn("refusing to write slices under dumps/", out)


def run_cli(argv):
    out, err = io.StringIO(), io.StringIO()
    saved_out, saved_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        code = ex.main(argv)
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):

    def test_default_run_reports_pass(self):
        code, out, _err = run_cli([])
        self.assertEqual(code, 0)
        self.assertIn("RESULT extraction_ok=True", out)
        self.assertIn("REGION_TABLE flash=0x16750", out)

    def test_json_is_deterministic_and_complete(self):
        _code, first, _err = run_cli(["--json"])
        _code, second, _err = run_cli(["--json"])
        self.assertEqual(first, second)
        payload = json.loads(first)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["regions"]), 3)
        self.assertEqual(len(payload["slices"]), 3)
        self.assertEqual(payload["entry"]["initial_sp"], 0x18036168)

    def test_unknown_source_is_refused_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = bytearray(INSTALLED.read_bytes())
            data[0x31000] ^= 0xFF
            path = Path(tmp) / "unvouched.bin"
            path.write_bytes(bytes(data))
            code, out, _err = run_cli([str(path), "--base", "0x10000"])
            self.assertEqual(code, 1)
            self.assertIn("unknown source image", out)

            code, out, err = run_cli([str(path), "--base", "0x10000",
                                      "--analysis-only"])
            self.assertEqual(code, 0)
            self.assertIn("WARNING", err)
            self.assertIn("RESULT extraction_ok=True", out)


if __name__ == "__main__":
    unittest.main()
