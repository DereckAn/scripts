#!/usr/bin/env python3
"""Mutation tests for the Phase 7 offline builder.

Two rules shape this file.

INDEPENDENCE. The validators here do NOT use the builder's mutation helpers.
Where a built image's integrity must be checked, this module recomputes the
chunked CRC and the word-sum from `zlib` and `struct` directly, so a bug shared
between the builder and its checker cannot hide.

EVERY REFUSAL MUST BE CLEAN. A rejected build must raise BuildError, leave no
output file and no manifest behind. A traceback or a partial file is a failure
even when the operation was correctly rejected, so `assert_clean_refusal` checks
the directory afterwards every time.

No device access. Every build runs against a COPY of the evidence in a
temporary directory; neither evidence binary is ever opened for writing.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_offline_image as bo
import falchion_image as fi

VENDOR = bo.Path(__file__).resolve().parent.parent / "dumps/vendor/M605_V01_00_58.bin"
INSTALLED = (bo.Path(__file__).resolve().parent.parent
             / "dumps/device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59"
               "_app_0x10000_0x7bfff.bin")
READY = VENDOR.exists() and INSTALLED.exists()

M32 = 0xFFFFFFFF


# --- independent reimplementations -------------------------------------------
def independent_chunked_crc(data, start, length, chunk=0x10000):
    """The audited algorithm, written from the log rather than imported."""
    acc, pos, rem = 0, start, length
    while rem:
        size = min(rem, chunk)
        acc = (acc + zlib.crc32(data[pos:pos + size])) & M32
        pos += size & 0xFFFFFFFC
        rem -= size
    return acc


def independent_word_sum(data, start, end):
    words = struct.unpack(f"<{(end - start) // 4}I", data[start:end])
    return sum(words) & M32


class BuilderCase(unittest.TestCase):
    """Shared fixtures: a scratch copy of each evidence file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.out = self.dir / "out"
        self.out.mkdir()
        if READY:
            self.vendor = self.dir / "vendor.bin"
            self.installed = self.dir / "installed.bin"
            shutil.copyfile(VENDOR, self.vendor)
            shutil.copyfile(INSTALLED, self.installed)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_clean_refusal(self, source, patches, expect):
        """The build must raise BuildError and leave the output dir empty."""
        before = sorted(p.name for p in self.out.iterdir())
        with self.assertRaises(bo.BuildError) as caught:
            bo.build(source, patches, self.out)
        self.assertIn(expect, str(caught.exception).lower())
        after = sorted(p.name for p in self.out.iterdir())
        self.assertEqual(before, after,
                         "a refused build left a file behind")


@unittest.skipUnless(READY, "evidence binaries not present")
class NoOp(BuilderCase):

    def test_the_installed_adapter_noop_is_byte_identical(self):
        path, manifest = bo.build(self.installed, [], self.out, "noop")
        self.assertEqual(path.read_bytes(), INSTALLED.read_bytes())
        self.assertEqual(manifest["output_sha256"], manifest["source_sha256"])
        self.assertEqual(manifest["adapter_base"], 0x10000)

    def test_the_vendor_adapter_noop_is_byte_identical(self):
        path, manifest = bo.build(self.vendor, [], self.out, "noop")
        self.assertEqual(path.read_bytes(), VENDOR.read_bytes())
        self.assertEqual(manifest["output_sha256"], manifest["source_sha256"])
        self.assertEqual(manifest["adapter_base"], 0x0)

    def test_the_noop_still_recomputes_and_still_matches(self):
        """Recomputing a correct sum must reproduce the same bytes; that is
        what makes the byte-identity check meaningful rather than a bypass."""
        _path, manifest = bo.build(self.vendor, [], self.out, "noop")
        self.assertTrue(any(item["field"] == "application_word_sum"
                            for item in manifest["recomputed_fields"]))

    def test_the_output_name_carries_the_untested_marker(self):
        path, _manifest = bo.build(self.installed, [], self.out, "noop")
        self.assertIn(bo.UNTESTED_MARKER, path.name)


@unittest.skipUnless(READY, "evidence binaries not present")
class SourceGate(BuilderCase):

    def test_a_wrong_hash_is_refused(self):
        data = bytearray(self.vendor.read_bytes())
        data[0x30000] ^= 0xFF
        bad = self.dir / "bad.bin"
        bad.write_bytes(bytes(data))
        self.assert_clean_refusal(bad, [], "not an allowlisted mutation source")

    def test_a_truncated_source_is_refused(self):
        short = self.dir / "short.bin"
        short.write_bytes(self.vendor.read_bytes()[:0x1000])
        self.assert_clean_refusal(short, [], "not an allowlisted mutation source")

    def test_an_empty_source_is_refused(self):
        empty = self.dir / "empty.bin"
        empty.write_bytes(b"")
        self.assert_clean_refusal(empty, [], "not an allowlisted mutation source")

    def test_a_padded_source_of_the_right_hash_prefix_is_refused(self):
        """Size is part of the allowlist, not just the digest."""
        padded = self.dir / "padded.bin"
        padded.write_bytes(self.vendor.read_bytes() + b"\x00" * 16)
        self.assert_clean_refusal(padded, [],
                                  "not an allowlisted mutation source")

    def test_the_adapter_is_chosen_by_the_source_not_by_a_flag(self):
        """There is no --base to get wrong. A wrong base is the classic way
        to corrupt an offset-driven tool, so the CLI must not offer one."""
        source = Path(bo.__file__).read_text()
        self.assertNotIn('"--base"', source)
        self.assertNotIn("'--base'", source)
        # and the adapter really is derived from the bytes
        for path, expected in ((self.installed, "installed-1.59-application"),
                               (self.vendor, "vendor-1.00.58-full")):
            with self.subTest(expected=expected):
                out = self.out / expected
                out.mkdir()
                _p, manifest = bo.build(path, [], out)
                self.assertEqual(manifest["adapter"], expected)


class PatchParsing(unittest.TestCase):

    def test_a_patch_without_original_bytes_is_refused(self):
        with self.assertRaises(bo.BuildError) as caught:
            bo.parse_patch("0x3f66f=72")
        self.assertIn("mandatory", str(caught.exception))

    def test_an_empty_patch_is_refused(self):
        with self.assertRaises(bo.BuildError):
            bo.Patch(0x3F66F, b"", b"")

    def test_a_length_changing_patch_is_refused(self):
        with self.assertRaises(bo.BuildError) as caught:
            bo.Patch(0x3F66F, b"\x52", b"\x72\x73")
        self.assertIn("may not change a record's length", str(caught.exception))

    def test_a_malformed_patch_string_is_refused(self):
        for text in ("garbage", "0x10=zz:00", "=52:72", "0x10=52"):
            with self.assertRaises(bo.BuildError):
                bo.parse_patch(text)

    def test_a_well_formed_patch_parses(self):
        patch = bo.parse_patch("0x3f66f=52:72")
        self.assertEqual((patch.flash_off, patch.original, patch.replacement),
                         (0x3F66F, b"\x52", b"\x72"))


@unittest.skipUnless(READY, "evidence binaries not present")
class RejectedRegions(BuilderCase):
    """Each rejected region class, one test each."""

    def patch(self, offset, original=b"\x00", replacement=b"\x01"):
        return [bo.Patch(offset, original, replacement)]

    def test_a_patch_in_the_primary_bootloader_is_refused(self):
        self.assert_clean_refusal(self.vendor, self.patch(0x2000),
                                  "primary bootloader")

    def test_a_patch_in_the_backup_bootloader_is_refused(self):
        self.assert_clean_refusal(self.vendor, self.patch(0x62000),
                                  "backup bootloader")

    def test_a_patch_in_the_fwin_header_is_refused(self):
        self.assert_clean_refusal(self.vendor, self.patch(bo.FWIN_HEADER_LO),
                                  "sn_fwin header")

    def test_a_patch_in_the_record_table_is_refused(self):
        self.assert_clean_refusal(self.vendor,
                                  self.patch(bo.RECORD_TABLE_LO + 4),
                                  "record table metadata")

    def test_a_patch_on_a_record_checksum_field_is_refused(self):
        """The checksum field lives inside the record table, so this is the
        same refusal reached by a different intent."""
        offset = bo.RECORD_TABLE_LO + bo.RECORD_CHECKSUM_OFF
        self.assert_clean_refusal(self.vendor, self.patch(offset),
                                  "record table metadata")

    def test_a_patch_on_each_word_sum_field_is_refused(self):
        for name, (_covered, field_off) in bo.WORD_SUMS.items():
            with self.subTest(name=name):
                if not (0 <= field_off < len(VENDOR.read_bytes())):
                    continue
                self.assert_clean_refusal(self.vendor, self.patch(field_off),
                                          f"{name} word-sum field itself")

    def test_a_patch_outside_every_record_is_refused(self):
        """Inside the adapter, outside any active record's payload."""
        self.assert_clean_refusal(self.vendor, self.patch(0x79000),
                                  "does not lie wholly inside one active "
                                  "record")

    def test_a_patch_past_the_end_of_the_image_is_refused(self):
        self.assert_clean_refusal(self.vendor, self.patch(0x900000),
                                  "outside the")

    def test_a_patch_straddling_a_record_boundary_is_refused(self):
        view = fi.ImageView(VENDOR.read_bytes(), 0)
        spans = bo.active_records(view)
        edge = spans[0].hi - 1
        self.assert_clean_refusal(self.vendor,
                                  [bo.Patch(edge, b"\x00\x00", b"\x01\x01")],
                                  "does not lie wholly inside one active "
                                  "record")

    def test_an_installed_source_refuses_a_primary_bootloader_offset(self):
        """It is outside the adapter entirely, so the refusal names that."""
        self.assert_clean_refusal(self.installed, self.patch(0x2000),
                                  "outside the")


@unittest.skipUnless(READY, "evidence binaries not present")
class PatchIntegrity(BuilderCase):

    def good_patch(self):
        data = VENDOR.read_bytes()
        return [bo.Patch(0x3F66F, data[0x3F66F:0x3F670], b"\x72")]

    def test_a_wrong_original_byte_is_refused(self):
        self.assert_clean_refusal(self.vendor,
                                  [bo.Patch(0x3F66F, b"\xAA", b"\x72")],
                                  "expected original bytes")

    def test_overlapping_patches_are_refused(self):
        data = VENDOR.read_bytes()
        patches = [bo.Patch(0x3F66F, data[0x3F66F:0x3F671], b"\x72\x73"),
                   bo.Patch(0x3F670, data[0x3F670:0x3F671], b"\x74")]
        self.assert_clean_refusal(self.vendor, patches, "overlaps")

    def test_a_good_patch_builds_and_changes_exactly_the_asserted_byte(self):
        path, manifest = bo.build(self.vendor, self.good_patch(), self.out)
        built = path.read_bytes()
        source = VENDOR.read_bytes()
        differing = [i for i in range(len(source)) if source[i] != built[i]]
        # the patched byte, the record's 4-byte CRC field, the 4-byte word-sum
        self.assertIn(0x3F66F, differing)
        self.assertLessEqual(len(differing), 1 + 4 + 4)
        self.assertEqual(len(manifest["patches"]), 1)


@unittest.skipUnless(READY, "evidence binaries not present")
class IndependentVerification(BuilderCase):
    """These checks do not use the builder's integrity helpers."""

    def test_the_recomputed_record_crc_matches_an_independent_computation(self):
        data = VENDOR.read_bytes()
        patches = [bo.Patch(0x3F66F, data[0x3F66F:0x3F670], b"\x72")]
        path, manifest = bo.build(self.vendor, patches, self.out)
        built = path.read_bytes()
        view = fi.ImageView(built, 0)
        for span in bo.active_records(view):
            field = (bo.RECORD_TABLE_LO + span.index * fi.REC_STRIDE
                     + bo.RECORD_CHECKSUM_OFF)
            stored, = struct.unpack_from("<I", built, field)
            expected = independent_chunked_crc(built, span.lo, span.length)
            self.assertEqual(stored, expected,
                             f"record {span.index}")

    def test_the_recomputed_word_sum_matches_an_independent_computation(self):
        data = VENDOR.read_bytes()
        patches = [bo.Patch(0x3F66F, data[0x3F66F:0x3F670], b"\x72")]
        path, _manifest = bo.build(self.vendor, patches, self.out)
        built = path.read_bytes()
        lo, hi = bo.WORD_SUMS["application"][0]
        stored, = struct.unpack_from("<I", built, bo.WORD_SUMS["application"][1])
        self.assertEqual(stored, independent_word_sum(built, lo, hi))

    def test_the_word_sum_covers_the_updated_record_crc(self):
        """Dependency order: if the word-sum were computed first it would be
        stale. This proves the order by construction."""
        data = VENDOR.read_bytes()
        patches = [bo.Patch(0x3F66F, data[0x3F66F:0x3F670], b"\x72")]
        path, _manifest = bo.build(self.vendor, patches, self.out)
        built = path.read_bytes()
        lo, hi = bo.WORD_SUMS["application"][0]
        crc_field = bo.RECORD_TABLE_LO + 1 * fi.REC_STRIDE + bo.RECORD_CHECKSUM_OFF
        self.assertTrue(lo <= crc_field < hi,
                        "the record CRC field must lie inside the word-sum's "
                        "covered range for this test to mean anything")
        self.assertEqual(
            struct.unpack_from("<I", built, bo.WORD_SUMS["application"][1])[0],
            independent_word_sum(built, lo, hi))


@unittest.skipUnless(READY, "evidence binaries not present")
class Output(BuilderCase):

    def test_an_output_collision_is_refused_and_leaves_the_original(self):
        path, _manifest = bo.build(self.installed, [], self.out, "noop")
        original = path.read_bytes()
        with self.assertRaises(bo.BuildError) as caught:
            bo.build(self.installed, [], self.out, "noop")
        self.assertIn("refusing to overwrite", str(caught.exception))
        self.assertEqual(path.read_bytes(), original)

    def test_a_manifest_accompanies_every_output(self):
        path, manifest = bo.build(self.installed, [], self.out, "noop")
        side = path.with_suffix(".manifest.json")
        self.assertTrue(side.exists())
        self.assertEqual(json.loads(side.read_text()), manifest)

    def test_the_manifest_carries_every_required_field(self):
        _path, manifest = bo.build(self.installed, [], self.out, "noop")
        for key in ("adapter", "adapter_base", "boot_checks", "output_sha256",
                    "output_size", "patches", "recomputed_fields",
                    "source_sha256", "source_size", "tool_version",
                    "unresolved_risks", "validations", "word_sum_status"):
            self.assertIn(key, manifest, key)

    def test_the_manifest_records_the_original_byte_assertions(self):
        data = VENDOR.read_bytes()
        patches = [bo.Patch(0x3F66F, data[0x3F66F:0x3F670], b"\x72")]
        _path, manifest = bo.build(self.vendor, patches, self.out)
        entry, = manifest["patches"]
        self.assertEqual(entry["original"], data[0x3F66F:0x3F670].hex())
        self.assertEqual(entry["replacement"], "72")

    def test_the_unresolved_risks_are_never_empty(self):
        _path, manifest = bo.build(self.installed, [], self.out, "noop")
        self.assertTrue(manifest["unresolved_risks"])
        joined = " ".join(manifest["unresolved_risks"])
        self.assertIn("not evidence that the image will boot", joined)

    def test_the_installed_adapter_reports_the_primary_word_sum_unavailable(self):
        _path, manifest = bo.build(self.installed, [], self.out, "noop")
        self.assertEqual(manifest["word_sum_status"]["primary_bootloader"],
                         "unavailable")
        self.assertIn("primary_bootloader",
                      " ".join(manifest["unresolved_risks"]))

    def test_the_builder_never_claims_acceptance(self):
        path, manifest = bo.build(self.installed, [], self.out, "noop")
        text = "\n".join(bo.report_lines(path, manifest))
        self.assertIn("acceptance is NOT claimed", text)


class WordSumPolicy(unittest.TestCase):

    def test_only_the_application_word_sum_is_permitted(self):
        self.assertEqual(bo.PERMITTED_RECOMPUTE, ("application",))

    def test_the_backup_word_sum_is_policy_gated(self):
        self.assertEqual(bo.POLICY_GATED_RECOMPUTE, ("backup_bootloader",))

    def test_the_primary_word_sum_is_in_neither_list(self):
        self.assertNotIn("primary_bootloader", bo.PERMITTED_RECOMPUTE)
        self.assertNotIn("primary_bootloader", bo.POLICY_GATED_RECOMPUTE)

    def test_the_installed_adapter_marks_the_primary_unavailable(self):
        adapter = bo.adapters()["installed-1.59-application"]
        self.assertEqual(adapter.word_sum_status()["primary_bootloader"],
                         "unavailable")

    def test_the_vendor_adapter_can_see_all_three_ranges(self):
        adapter = bo.adapters()["vendor-1.00.58-full"]
        self.assertEqual(
            set(adapter.word_sum_status().values()), {"available"})


DEVICE_PATTERNS = (
    r"/dev/hidraw", r"\bhid\b", r"\busb\.core\b", r"\bhidapi\b",
    r"\bopen\(\s*[\"']/dev/", r"\bwrite_report\b", r"\bsend_feature\b",
    r"\bctrl_transfer\b", r"\bendpoint\b", r"\benumerate\b",
    r"\bdfu-util\b", r"\bsudo\b", r"\bioctl\b",
)


class NoDeviceCode(unittest.TestCase):
    """Requirement 9: the builder must contain no device framing."""

    def hits(self, text):
        return tuple(pattern for pattern in DEVICE_PATTERNS
                     if re.search(pattern, text, re.IGNORECASE))

    def test_the_builder_module_contains_no_device_framing(self):
        source = Path(bo.__file__).read_text()
        self.assertEqual(self.hits(source), (),
                         "the builder matched device framing")

    def test_the_detector_actually_detects(self):
        """Anti-vacuity: a detector that never fires proves nothing."""
        for bad in ("open('/dev/hidraw6','wb')",
                    "import hid",
                    "dev.ctrl_transfer(0x21, 9, 0, 0, data)",
                    "d.write_report(payload)",
                    "sudo chmod 666 /dev/hidraw6",
                    "usb.core.find(idVendor=0x0b05)"):
            self.assertNotEqual(self.hits(bad), (), bad)

    def test_ordinary_builder_prose_is_not_flagged(self):
        for fine in ("the application region word-sum at 0x7bffc",
                     "each affected record's chunked-CRC sum",
                     "exclusive create, never overwrite"):
            self.assertEqual(self.hits(fine), (), fine)

    def test_the_builder_imports_nothing_device_shaped(self):
        source = Path(bo.__file__).read_text()
        imports = re.findall(r"^\s*(?:import|from)\s+([\w.]+)", source,
                             re.MULTILINE)
        for name in imports:
            self.assertNotIn(name.split(".")[0],
                             {"usb", "hid", "hidapi", "serial", "fcntl",
                              "termios", "socket", "http", "urllib",
                              "requests", "subprocess"}, name)


if __name__ == "__main__":
    unittest.main()
