#!/usr/bin/env python3
"""Dependency-free tests for the analyzers and the offline image builder.

Uses the preserved 1.00.58 artifact read-only plus temporary copies. No device
access, and no test writes inside the repository.

Run: python3 tool/test_build_modified_image.py
"""
import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_boot_structures as abs_
import analyze_candidate_integrity as aci
import build_modified_image as bmi

SOURCE = aci.DEFAULT_BIN


@unittest.skipUnless(SOURCE.exists(), "preserved vendor image is absent")
class TestVersionLock(unittest.TestCase):
    def test_vendor_sha256_matches_the_lock(self):
        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(digest, bmi.EXPECTED_SOURCE_SHA256)
        self.assertEqual(len(bmi.EXPECTED_SOURCE_SHA256), 64)

    def test_wrong_source_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            impostor = Path(tmp, "not-vendor.bin")
            data = bytearray(SOURCE.read_bytes())
            data[bmi.CANDIDATE_B_LO] ^= 0xFF
            impostor.write_bytes(data)
            with self.assertRaises(ValueError) as ctx:
                bmi.load_source(impostor)
            self.assertIn("not the preserved M605 1.00.58 image", str(ctx.exception))

    def test_wrong_size_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            short = Path(tmp, "short.bin")
            short.write_bytes(SOURCE.read_bytes()[:0x1000])
            with self.assertRaises(ValueError):
                bmi.load_source(short)


@unittest.skipUnless(SOURCE.exists(), "preserved vendor image is absent")
class TestScatter(unittest.TestCase):
    def setUp(self):
        self.img = bmi.load_source(SOURCE)

    def test_stream_bounds_are_the_documented_ones(self):
        self.assertEqual(bmi.COMPRESSED_LO, 0x3F354)
        self.assertEqual(bmi.CANDIDATE_B_HI, 0x3F754)

    def test_decompresses_to_the_observed_shape(self):
        output, consumed, _blocks, _lit = bmi.scatter_decompress(
            self.img[bmi.COMPRESSED_LO:bmi.CANDIDATE_B_HI])
        self.assertEqual(len(output), 0x0B04)
        self.assertEqual(consumed, 0x3FE)
        trailing = self.img[bmi.COMPRESSED_LO + consumed:bmi.CANDIDATE_B_HI]
        self.assertEqual(len(trailing), 2)
        self.assertEqual(trailing, b"\x00\x00")

    def test_validate_scatter_passes_on_the_vendor_image(self):
        ok, detail = bmi.validate_scatter(self.img)
        self.assertTrue(ok, detail)

    def test_demo_offset_maps_to_the_documented_runtime_address(self):
        index, runtime = bmi.literal_runtime_address(self.img, 0x3F66F)
        self.assertEqual(index, 0x882)
        self.assertEqual(runtime, 0x1801EBD6)

    def test_control_byte_offset_is_rejected(self):
        literals = bmi.scatter_decompress(
            self.img[bmi.COMPRESSED_LO:bmi.CANDIDATE_B_HI])[3]
        control = next(i for i in range(bmi.COMPRESSED_SIZE) if i not in literals)
        with self.assertRaises(ValueError) as ctx:
            bmi.literal_runtime_address(self.img, bmi.COMPRESSED_LO + control)
        self.assertIn("control byte", str(ctx.exception))

    def test_offset_outside_the_stream_is_rejected(self):
        with self.assertRaises(ValueError):
            bmi.literal_runtime_address(self.img, bmi.CANDIDATE_B_LO)

    def test_corrupt_stream_fails_validation(self):
        broken = bytearray(self.img)
        broken[bmi.COMPRESSED_LO] = 0xFF
        ok, _detail = bmi.validate_scatter(broken)
        self.assertFalse(ok)

    def test_truncated_stream_raises(self):
        with self.assertRaises(ValueError):
            bmi.scatter_decompress(b"\x21\x41")


@unittest.skipUnless(SOURCE.exists(), "preserved vendor image is absent")
class TestPatchRestriction(unittest.TestCase):
    def test_candidate_b_patch_accepted(self):
        bmi.validate_patches([(bmi.CANDIDATE_B_LO, b"\x00"),
                              (bmi.CANDIDATE_B_HI - 1, b"\x00")])

    def test_empty_payload_refused(self):
        with self.assertRaises(ValueError) as ctx:
            bmi.validate_patches([(bmi.CANDIDATE_B_LO, b"")])
        self.assertIn("empty patch payload", str(ctx.exception))

    def test_overlapping_patches_refused(self):
        with self.assertRaises(ValueError) as ctx:
            bmi.validate_patches([(bmi.CANDIDATE_B_LO, b"ab"),
                                  (bmi.CANDIDATE_B_LO + 1, b"c")])
        self.assertIn("overlap", str(ctx.exception))

    def test_outside_candidate_b_refused(self):
        for off in (0x0, 0xFFFC, bmi.CANDIDATE_B_LO - 1, bmi.CANDIDATE_B_HI, 0x7BFFC):
            with self.assertRaises(ValueError) as ctx:
                bmi.validate_patches([(off, b"\x00")])
            self.assertIn("outside Candidate B", str(ctx.exception))

    def test_patch_straddling_the_upper_bound_refused(self):
        with self.assertRaises(ValueError):
            bmi.validate_patches([(bmi.CANDIDATE_B_HI - 1, b"ab")])


@unittest.skipUnless(SOURCE.exists(), "preserved vendor image is absent")
class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.original = bmi.load_source(SOURCE)

    def test_recompute_is_idempotent(self):
        rebuilt = bmi.recompute_integrity(bmi.load_source(SOURCE))
        self.assertEqual(rebuilt, self.original)

    def test_patch_preserves_crc_sum_and_word_sums(self):
        img, checks = bmi.build(SOURCE, [(0x3F66F, b"r")])
        self.assertTrue(all(checks.values()), checks)
        records = aci.parse_records(img, 0)
        for index, addr, length, stored, _dst in records:
            calc = aci.chunked_crc_sum(img, addr - aci.FLASH_BASE, length)
            self.assertEqual(calc, stored, f"record[{index}] CRC-sum not preserved")
        for name, (lo, hi) in aci.WORD_SUM_REGIONS.items():
            stored, calc = aci.word_sum_last(img, lo, hi)
            self.assertEqual(stored, calc, f"{name} word-sum not preserved")

    def test_patch_changes_only_the_byte_and_the_integrity_fields(self):
        img, _checks = bmi.build(SOURCE, [(0x3F66F, b"r")])
        changed = {i for i, (a, b) in enumerate(zip(self.original, img)) if a != b}
        allowed = {0x3F66F} | set(range(aci.REC0 + 0x10 + bmi.CRC_FIELD,
                                        aci.REC0 + 0x10 + bmi.CRC_FIELD + 4))
        allowed |= set(range(0x7BFFC, 0x7C000))
        self.assertTrue(changed <= allowed, changed - allowed)
        self.assertIn(0x3F66F, changed)

    def test_decompression_is_validated_after_patching(self):
        """A patch that corrupts the compressed stream must fail the build."""
        with self.assertRaises(ValueError) as ctx:
            bmi.build(SOURCE, [(bmi.COMPRESSED_LO, b"\xff")])
        self.assertIn("failed offline checks", str(ctx.exception))

    def test_existing_output_is_refused(self):
        out = Path(self.tmp.name, "mod.bin")
        out.write_bytes(b"precious")
        with self.assertRaises(FileExistsError):
            bmi.build(SOURCE, [(0x3F66F, b"r")], out)
        self.assertEqual(out.read_bytes(), b"precious")

    def test_output_written_when_absent(self):
        out = Path(self.tmp.name, "new.bin")
        img, _checks = bmi.build(SOURCE, [(0x3F66F, b"r")], out)
        self.assertEqual(out.read_bytes(), bytes(img))

    def test_cli_refuses_existing_output_without_traceback(self):
        out = Path(self.tmp.name, "cli.bin")
        out.write_bytes(b"precious")
        rc = bmi.main(["--patch", "0x3f66f=72", "--out", str(out)])
        self.assertEqual(rc, 1)
        self.assertEqual(out.read_bytes(), b"precious")

    def test_demo_writes_nothing(self):
        before = set(os.listdir(self.tmp.name))
        self.assertEqual(bmi.demo(SOURCE), 0)
        self.assertEqual(set(os.listdir(self.tmp.name)), before)

    def test_preserved_source_is_never_modified(self):
        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        bmi.build(SOURCE, [(0x3F66F, b"r")])
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(), digest)


@unittest.skipUnless(SOURCE.exists(), "preserved vendor image is absent")
class TestAnalyzers(unittest.TestCase):
    """Full image at base 0 and the app-only region at base 0x10000."""

    @classmethod
    def setUpClass(cls):
        cls.full = SOURCE.read_bytes()
        cls.app = cls.full[0x10000:0x7C000]

    def test_no_import_time_argv_dependence(self):
        """Both analyzers must parse an explicit argv, not read sys.argv on import."""
        for module in (abs_, aci):
            args = module.parse_args(["/tmp/x.bin", "--base", "0x10000"])
            self.assertEqual(args.base, 0x10000)
            self.assertEqual(str(args.image), "/tmp/x.bin")
            self.assertEqual(module.parse_args([]).base, 0)

    def test_integrity_full_image(self):
        records, word_sums, checks = aci.analyze(self.full, 0)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(checks.values()), checks)
        self.assertNotIn(None, word_sums.values())

    def test_integrity_app_only_states_skipped_region(self):
        _records, word_sums, checks = aci.analyze(self.app, 0x10000)
        self.assertIsNone(word_sums["bootloader"])
        self.assertIsNotNone(word_sums["application"])
        self.assertNotIn("bootloader word-sum", checks)
        self.assertTrue(all(checks.values()), checks)

    def test_boot_checks_full_image(self):
        present, skipped, _records, checks = abs_.known_boot_checks(self.full, 0)
        self.assertEqual(sorted(present), ["backup", "primary"])
        self.assertEqual(skipped, [])
        self.assertTrue(all(checks.values()), checks)

    def test_boot_checks_app_only_reports_skipped_container(self):
        present, skipped, _records, checks = abs_.known_boot_checks(self.app, 0x10000)
        self.assertEqual(present, ["backup"])
        self.assertEqual(skipped, ["primary"])
        self.assertTrue(all(checks.values()), checks)
        self.assertFalse(any(name.startswith("primary") for name in checks))

    def test_unresolved_points_are_recorded(self):
        text = " ".join(abs_.UNRESOLVED)
        self.assertIn("FUN_000029d4", text)
        self.assertIn("selected entry", text)

    def test_no_boots_if_and_only_if_claim(self):
        for module in (abs_, aci, bmi):
            doc = (module.__doc__ or "").lower()
            for phrase in ("if and only if", "iff", "will boot", "guarantees a boot"):
                self.assertNotIn(phrase, doc, f"{module.__name__} docstring: {phrase}")

    def test_app_only_image_is_the_backup_tool_region(self):
        self.assertEqual(len(self.app), 0x6C000)

    def test_out_of_range_base_is_reported_not_crashed(self):
        with self.assertRaises(ValueError):
            aci.analyze(self.app, 0x20000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
