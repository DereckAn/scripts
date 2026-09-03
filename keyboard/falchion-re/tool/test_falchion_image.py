#!/usr/bin/env python3
"""Offline tests for the shared Falchion image-format library.

Reads only the two preserved evidence binaries and in-memory mutations of them.
No device access, no writes to any dump.
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

import analyze_boot_structures as abs_
import analyze_candidate_integrity as aci
import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")

VENDOR_SHA = "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d"
INSTALLED_SHA = "fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b"

REC_TABLE = fi.FWIN_OFF + fi.FWIN_REC0_OFF


def rec_field_off(view, index, field):
    """File index of a record field, for building malformed variants."""
    return view.index(REC_TABLE + index * fi.REC_STRIDE) + field * 4


class Evidence(unittest.TestCase):
    """The library must never disturb or misread the preserved binaries."""

    @classmethod
    def setUpClass(cls):
        cls.vendor = fi.ImageView(VENDOR.read_bytes(), 0)
        cls.installed = fi.ImageView(INSTALLED.read_bytes(), 0x10000)

    def test_source_hashes_unchanged(self):
        self.assertEqual(self.vendor.sha256(), VENDOR_SHA)
        self.assertEqual(self.installed.sha256(), INSTALLED_SHA)

    def test_full_vendor_image_validates(self):
        result = fi.validate(self.vendor)
        self.assertTrue(result.ok)
        self.assertEqual([c.name for c in result.layout.containers],
                         ["primary", "backup"])
        self.assertEqual(result.layout.skipped_containers, ())
        self.assertEqual(result.skipped_word_sums, ())
        self.assertEqual(result.source.name, "vendor-1.00.58-full")

    def test_installed_partial_image_matches_log_92(self):
        result = fi.validate(self.installed)
        self.assertTrue(result.ok)
        self.assertEqual([(r.index, r.addr, r.length, r.stored_checksum, r.dst)
                          for r in result.layout.records],
                         [(0, 0x60011000, 0x58AC, 0x7D552485, 0x18000000),
                          (1, 0x60021000, 0x1E780, 0xEB0A9879, 0x18000000)])
        app, = [w for w in result.word_sums if w.name == "application"]
        self.assertEqual((app.stored, app.computed), (0x2D7486DB, 0x2D7486DB))
        self.assertEqual(result.layout.skipped_containers, ("primary",))
        self.assertEqual(result.skipped_word_sums, ("bootloader",))
        self.assertEqual(result.source.name, "installed-1.59-application")

    def test_record_lengths_come_from_their_own_image(self):
        """The 1.59 application record is 44 bytes longer than 1.00.58's."""
        vendor = fi.parse(self.vendor).records
        installed = fi.parse(self.installed).records
        self.assertEqual(vendor[1].length, 0x1E754)
        self.assertEqual(installed[1].length, 0x1E780)
        self.assertEqual(installed[1].length - vendor[1].length, 44)
        self.assertEqual(vendor[0].length, installed[0].length)

    def test_bootloader_mirror_word_sum_is_present_in_both(self):
        """[0x61000,0x71000) is the copy of [0,0x10000); its guard is 0x70ffc."""
        for view in (self.vendor, self.installed):
            mirror, = [w for w in fi.validate(view).word_sums
                       if w.name == "bootloader_mirror"]
            self.assertEqual(mirror.hi - 4, 0x70FFC)
            self.assertEqual((mirror.stored, mirror.computed),
                             (0xFB665AE3, 0xFB665AE3))

    def test_installed_bootloader_mirror_equals_the_vendor_bootloader(self):
        """The bootloader under static analysis exists on the device.

        Phase 4 rests on this: the installed dump's mirrored copy is byte-for-byte
        the vendor 1.00.58 bootloader region. It says nothing about the unread
        installed primary region [0,0x10000) or about ROM/first-stage behaviour.
        """
        lo, hi = 0x61000, 0x71000
        installed_mirror = self.installed.read(lo, hi - lo)
        self.assertEqual(installed_mirror, self.vendor.read(lo, hi - lo))
        self.assertEqual(installed_mirror, self.vendor.read(0x0, 0x10000))
        self.assertEqual(
            hashlib.sha256(installed_mirror).hexdigest(),
            "4a4568b61bc245397b0ede6f285eb1bd8a7fa2018bc1373bc05e73eabb0f686a")

    def test_fwin_version_is_the_container_format_string(self):
        self.assertEqual(fi.parse(self.vendor).fwin.version, "v1.0.00")
        self.assertEqual(fi.parse(self.installed).fwin.version, "v1.0.00")


class AnalyzerParity(unittest.TestCase):
    """The shared library must agree with the already-accepted analyzers."""

    def views(self):
        return ((VENDOR.read_bytes(), 0), (INSTALLED.read_bytes(), 0x10000))

    def test_records_match_analyze_candidate_integrity(self):
        for data, base in self.views():
            expected = aci.parse_records(data, base)
            got = [(r.index, r.addr, r.length, r.stored_checksum, r.dst)
                   for r in fi.parse(fi.ImageView(data, base)).records]
            self.assertEqual(got, expected)

    def test_checksums_match_analyze_candidate_integrity(self):
        for data, base in self.views():
            _records, word_sums, checks = aci.analyze(data, base)
            result = fi.validate(fi.ImageView(data, base))
            mine = {c.name: c.ok for c in result.checks}
            for name, ok in checks.items():
                self.assertIn(name, mine, name)
                self.assertEqual(mine[name], ok, name)
            for name, pair in word_sums.items():
                got = [w for w in result.word_sums if w.name == name]
                if pair is None:
                    self.assertEqual(got, [])
                    self.assertIn(name, result.skipped_word_sums)
                else:
                    self.assertEqual((got[0].stored, got[0].computed), pair, name)

    def test_boot_checks_match_analyze_boot_structures(self):
        for data, base in self.views():
            present, skipped, _records, checks = abs_.known_boot_checks(data, base)
            result = fi.validate(fi.ImageView(data, base))
            self.assertEqual([c.name for c in result.layout.containers], present)
            self.assertEqual(list(result.layout.skipped_containers), skipped)
            mine = {c.name: c.ok for c in result.checks}
            for name, ok in checks.items():
                self.assertIn(name, mine, name)
                self.assertEqual(mine[name], ok, name)

    def test_hole_scanning_deliberately_diverges_from_the_old_analyzers(self):
        """Parity is asserted on the preserved images only.

        `analyze_candidate_integrity.py` still stops at the first zero address or
        zero length, which log 75 shows the bootloader does not do. On a table
        with a hole the shared library is right and the older analyzers are not,
        so they and `build_modified_image.py` must be reconciled before Phase 7
        mutates any record.
        """
        data = bytearray(VENDOR.read_bytes())
        view = fi.ImageView(bytes(data), 0)
        struct.pack_into("<4I", data, rec_field_off(view, 3, 0),
                         0x60011000, 0x100, 0, 0x18000000)
        holed = bytes(data)
        self.assertEqual(
            [r.index for r in fi.parse(fi.ImageView(holed, 0)).records],
            [0, 1, 3])
        self.assertEqual([r[0] for r in aci.parse_records(holed, 0)], [0, 1])

    def test_chunked_crc_sum_matches_analyze_candidate_integrity(self):
        for data, base in self.views():
            view = fi.ImageView(data, base)
            for record in fi.parse(view).records:
                self.assertEqual(
                    fi.chunked_crc_sum(view, record.flash_off, record.length),
                    aci.chunked_crc_sum(data, view.index(record.flash_off),
                                        record.length))


class Malformed(unittest.TestCase):
    """Every malformed input must fail closed with ImageFormatError."""

    def setUp(self):
        self.data = bytearray(VENDOR.read_bytes())
        self.view = fi.ImageView(bytes(self.data), 0)

    def mutated(self, base=0):
        return fi.ImageView(bytes(self.data), base)

    def test_absent_containers_are_reported_not_dropped(self):
        app_only = fi.ImageView(bytes(self.data[0x10000:0x7C000]), 0x10000)
        layout = fi.parse(app_only)
        self.assertEqual(layout.skipped_containers, ("primary",))
        self.assertEqual([c.name for c in layout.containers], ["backup"])

    def test_missing_fwin_header_fails_closed(self):
        truncated = fi.ImageView(bytes(self.data[:fi.FWIN_OFF]), 0)
        with self.assertRaises(fi.ImageFormatError):
            fi.parse(truncated)

    def test_out_of_range_record_length_fails_closed(self):
        struct.pack_into("<I", self.data, rec_field_off(self.view, 1, 1),
                         0x00FF0000)
        with self.assertRaises(fi.ImageFormatError) as caught:
            fi.parse(self.mutated())
        self.assertIn("absent from image base", str(caught.exception))

    def test_record_address_below_flash_base_fails_closed(self):
        struct.pack_into("<I", self.data, rec_field_off(self.view, 1, 0), 0x1000)
        with self.assertRaises(fi.ImageFormatError) as caught:
            fi.parse(self.mutated())
        self.assertIn("below", str(caught.exception))

    def set_slot(self, index, addr, length, checksum=0, dst=0x18000000):
        struct.pack_into("<4I", self.data, rec_field_off(self.view, index, 0),
                         addr, length, checksum, dst)

    def test_active_slot_after_a_zero_length_hole_is_not_dropped(self):
        """The defect this test exists for: FUN_0000511c keeps scanning holes.

        Slot 2 is already a zero-length hole in both preserved images. An active
        slot 3 behind it must appear, keep its physical index, and contribute its
        own checksum dependency.
        """
        self.set_slot(3, 0x60011000, 0x100, checksum=0xDEADBEEF)
        layout = fi.parse(self.mutated())
        self.assertEqual([r.index for r in layout.records], [0, 1, 3])
        result = fi.validate(self.mutated())
        names = {c.name for c in result.checks}
        self.assertIn("record[3] checksum", names)
        self.assertFalse(result.ok)
        self.assertIn("record[3] checksum",
                      {c.name for c in result.checks if not c.ok})

    def test_zero_address_with_nonzero_length_fails_bounds(self):
        self.set_slot(3, 0x00000000, 0x100)
        with self.assertRaises(fi.ImageFormatError) as caught:
            fi.parse(self.mutated())
        message = str(caught.exception)
        self.assertIn("record[3]", message)
        self.assertIn("below the mapped flash base", message)

    def test_all_eight_slots_populated_are_all_parsed(self):
        for index in range(fi.MAX_RECORDS):
            self.set_slot(index, 0x60011000 + index * 0x100, 0x100)
        layout = fi.parse(self.mutated())
        self.assertEqual([r.index for r in layout.records], list(range(8)))
        checks = {c.name for c in fi.validate(self.mutated()).checks}
        for index in range(fi.MAX_RECORDS):
            self.assertIn(f"record[{index}] checksum", checks)

    def test_truncated_eight_slot_table_fails_closed(self):
        table = fi.FWIN_OFF + fi.FWIN_REC0_OFF
        cut = table + 4 * fi.REC_STRIDE
        with self.assertRaises(fi.ImageFormatError) as caught:
            fi.parse(fi.ImageView(bytes(self.data[:cut]), 0))
        self.assertIn("truncated", str(caught.exception))

    def test_table_with_no_active_slot_fails_closed(self):
        for index in range(fi.MAX_RECORDS):
            self.set_slot(index, 0x60011000, 0)
        with self.assertRaises(fi.ImageFormatError) as caught:
            fi.parse(self.mutated())
        self.assertIn("nonzero length", str(caught.exception))

    def test_nonzero_address_with_zero_length_stays_a_hole(self):
        """Slot 2 already carries addr 0x60021000 with length 0 in both images."""
        layout = fi.parse(self.view)
        self.assertEqual([r.index for r in layout.records], [0, 1])
        raw = struct.unpack_from("<4I", self.data,
                                 rec_field_off(self.view, 2, 0))
        self.assertEqual(raw[0], 0x60021000)
        self.assertEqual(raw[1], 0)

    def test_wrong_base_fails_closed_instead_of_misreading(self):
        with self.assertRaises(fi.ImageFormatError):
            fi.parse(fi.ImageView(bytes(self.data[0x10000:0x7C000]), 0x20000))

    def test_negative_base_rejected(self):
        with self.assertRaises(fi.ImageFormatError):
            fi.ImageView(b"\x00" * 16, -1)

    def test_unaligned_image_size_rejected(self):
        with self.assertRaises(fi.ImageFormatError):
            fi.ImageView(b"\x00" * 15, 0)

    def test_empty_image_fails_closed(self):
        with self.assertRaises(fi.ImageFormatError):
            fi.parse(fi.ImageView(b"", 0))

    def test_zero_length_crc_rejected(self):
        with self.assertRaises(fi.ImageFormatError):
            fi.chunked_crc_sum(self.view, 0x11000, 0)

    def test_word_sum_range_bounds(self):
        with self.assertRaises(fi.ImageFormatError):
            fi.word_sum(self.view, 0x1000, 0x1000)
        with self.assertRaises(fi.ImageFormatError):
            fi.word_sum(self.view, 0x1000, 0x1002)
        with self.assertRaises(fi.ImageFormatError):
            fi.word_sum(self.view, 0x70000, 0x90000)

    def test_index_boundaries_are_inclusive_of_the_last_byte(self):
        view = fi.ImageView(b"\x00" * 16, 0x1000)
        self.assertEqual(view.index(0x100C, 4), 0xC)
        with self.assertRaises(fi.ImageFormatError):
            view.index(0x100C, 5)
        with self.assertRaises(fi.ImageFormatError):
            view.index(0xFFC, 4)


class ChecksumFailure(unittest.TestCase):
    """A wrong checksum is a FAIL result, not an exception."""

    def setUp(self):
        self.data = bytearray(VENDOR.read_bytes())

    def failed_checks(self):
        result = fi.validate(fi.ImageView(bytes(self.data), 0))
        self.assertFalse(result.ok)
        return {c.name for c in result.checks if not c.ok}

    def test_record_payload_change_fails_only_the_dependent_fields(self):
        self.data[0x11100] ^= 0xFF
        failed = self.failed_checks()
        self.assertIn("record[0] checksum", failed)
        self.assertIn("application word-sum", failed)
        self.assertNotIn("record[1] checksum", failed)
        self.assertNotIn("bootloader word-sum", failed)

    def test_mirror_region_change_fails_its_own_word_sum(self):
        self.data[0x61500] ^= 0xFF
        failed = self.failed_checks()
        self.assertIn("bootloader_mirror word-sum", failed)
        self.assertIn("application word-sum", failed)
        self.assertNotIn("bootloader word-sum", failed)

    def test_gate_and_magic_regressions_are_reported(self):
        struct.pack_into("<I", self.data, fi.FWIN_OFF + fi.FWIN_GATE_OFF, 0)
        self.data[0:8] = b"XXXXXXXX"
        failed = self.failed_checks()
        self.assertIn("SN_FWIN CRC-enable gate nonzero", failed)
        self.assertIn("primary SNC7320A magic", failed)


class SourcePolicy(unittest.TestCase):
    """Mutation must refuse anything not explicitly allowlisted."""

    def test_both_preserved_images_are_supported(self):
        self.assertEqual(
            fi.require_supported_source(
                fi.ImageView(VENDOR.read_bytes(), 0)).name,
            "vendor-1.00.58-full")
        self.assertEqual(
            fi.require_supported_source(
                fi.ImageView(INSTALLED.read_bytes(), 0x10000)).name,
            "installed-1.59-application")

    def test_changed_byte_is_refused(self):
        data = bytearray(VENDOR.read_bytes())
        data[0x11100] ^= 0xFF
        view = fi.ImageView(bytes(data), 0)
        self.assertIsNone(fi.find_source(view))
        with self.assertRaises(fi.UnsupportedSourceError):
            fi.require_supported_source(view)

    def test_right_bytes_wrong_base_is_refused(self):
        view = fi.ImageView(VENDOR.read_bytes(), 0x10000)
        with self.assertRaises(fi.UnsupportedSourceError):
            fi.require_supported_source(view)

    def test_unknown_image_still_parses_for_analysis(self):
        data = bytearray(VENDOR.read_bytes())
        data[0x11100] ^= 0xFF
        result = fi.validate(fi.ImageView(bytes(data), 0))
        self.assertIsNone(result.source)
        self.assertEqual(len(result.layout.records), 2)


class MachineReadable(unittest.TestCase):
    """Later phases must consume JSON, never the human report."""

    def setUp(self):
        self.result = fi.validate(fi.ImageView(VENDOR.read_bytes(), 0))

    def test_json_is_deterministic(self):
        first = json.dumps(fi.to_dict(self.result), sort_keys=True)
        second = json.dumps(fi.to_dict(
            fi.validate(fi.ImageView(VENDOR.read_bytes(), 0))), sort_keys=True)
        self.assertEqual(first, second)

    def test_json_carries_the_facts_and_the_caveats(self):
        payload = fi.to_dict(self.result)
        self.assertEqual(payload["sha256"], VENDOR_SHA)
        self.assertEqual(payload["base"], 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["records"][1]["length"], 0x1E754)
        self.assertEqual(len(payload["unresolved"]), 3)
        self.assertEqual(payload["source"], "vendor-1.00.58-full")

    def test_models_are_immutable(self):
        with self.assertRaises(Exception):
            self.result.layout.records[0].length = 1
        with self.assertRaises(Exception):
            self.result.checks[0].ok = False


class Cli(unittest.TestCase):

    def run_main(self, argv):
        buffer = io.StringIO()
        stdout, sys.stdout = sys.stdout, buffer
        try:
            code = fi.main(argv)
        finally:
            sys.stdout = stdout
        return code, buffer.getvalue()

    def test_vendor_image_reports_pass(self):
        code, out = self.run_main([str(VENDOR)])
        self.assertEqual(code, 0)
        self.assertIn("RESULT known_checks_ok=True", out)
        self.assertIn("UNRESOLVED", out)

    def test_installed_image_reports_skips(self):
        code, out = self.run_main([str(INSTALLED), "--base", "0x10000"])
        self.assertEqual(code, 0)
        self.assertIn("SKIP primary container", out)
        self.assertIn("SKIP bootloader word-sum", out)

    def test_json_mode_is_parseable(self):
        _code, out = self.run_main([str(VENDOR), "--json"])
        self.assertEqual(json.loads(out)["sha256"], VENDOR_SHA)

    def test_malformed_image_prints_one_line_and_no_partial_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.bin"
            path.write_bytes(b"\x00" * 0x1000)
            code, out = self.run_main([str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("RESULT known_checks_ok=False error=", out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("PASS", out)


if __name__ == "__main__":
    unittest.main()
