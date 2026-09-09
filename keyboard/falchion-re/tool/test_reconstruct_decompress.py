#!/usr/bin/env python3
"""Offline tests for the scatter-region decompressor.

Hand-built streams for the format rules, the preserved images for the real
numbers. Every failure path is asserted to *fail*: a decompressor that quietly
returns plausible bytes when the stream is truncated or corrupted is worse than
one that refuses, because the wrong bytes would be disassembled as if they were
code. No device access, no writes outside a temporary directory.
"""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import falchion_image as fi
import reconstruct_decompress as rd

READY = rd.INSTALLED.exists() and rd.VENDOR.exists()


class Format(unittest.TestCase):
    """The rules the handler's instructions encode, checked one at a time."""

    def test_a_literal_field_of_n_emits_n_minus_one_bytes(self):
        # control 0x14: literal field 4, bit 3 clear, copy field 1 zero byte.
        out, consumed, stats = rd.decompress(b"\x14ABC", 4)
        self.assertEqual(out, b"ABC\x00")
        self.assertEqual(consumed, 4)
        self.assertEqual((stats["literal_bytes"], stats["zero_bytes"]), (3, 1))

    def test_a_zero_literal_field_takes_the_count_from_the_next_byte(self):
        out, _consumed, _stats = rd.decompress(b"\x10\x04ABC", 4)
        self.assertEqual(out, b"ABC\x00")

    def test_a_zero_copy_field_takes_the_count_from_the_next_byte(self):
        out, _consumed, _stats = rd.decompress(b"\x04\x01ABC", 4)
        self.assertEqual(out, b"ABC\x00")

    def test_bit_three_selects_a_back_reference_of_field_plus_two(self):
        # Produce "ABC\x00", then copy 3 bytes from 4 back.
        out, _consumed, stats = rd.decompress(b"\x14ABC\x19\x04", 7)
        self.assertEqual(out, b"ABC\x00ABC")
        self.assertEqual(stats["copy_bytes"], 3)

    def test_an_overlapping_back_reference_repeats_what_it_just_wrote(self):
        """Distance 1 must repeat the last byte as the copy advances, which is
        how the handler emits a run: one `strb` at a time, no block move."""
        # control 0x1a: one literal "A", bit 3 set, copy field 1 -> 3 bytes.
        out, consumed, stats = rd.decompress(b"\x1aA\x01", 4)
        self.assertEqual(out, b"AAAA")
        self.assertEqual((consumed, stats["copy_bytes"]), (3, 3))

    def test_a_cleared_bit_three_emits_exactly_the_copy_field_in_zeros(self):
        # control 0x41: literal field 1 (no literals), bit 3 clear, copy
        # field 4 -> four zero bytes and nothing else.
        out, consumed, stats = rd.decompress(b"\x41", 4)
        self.assertEqual(out, b"\x00\x00\x00\x00")
        self.assertEqual((consumed, stats["zero_bytes"]), (1, 4))


class FailsClosed(unittest.TestCase):
    """Each of these must raise. None may return bytes."""

    def test_a_truncated_stream_raises_instead_of_returning_short(self):
        with self.assertRaises(rd.DecompressError) as caught:
            rd.decompress(b"\x14AB", 4)
        self.assertIn("exhausted", str(caught.exception))

    def test_a_stream_that_ends_mid_token_raises(self):
        with self.assertRaises(rd.DecompressError):
            rd.decompress(b"\x14ABC\x19", 7)

    def test_a_back_reference_before_the_start_of_output_raises(self):
        with self.assertRaises(rd.DecompressError) as caught:
            rd.decompress(b"\x14ABC\x19\x40", 7)
        self.assertIn("distance", str(caught.exception))

    def test_a_back_reference_at_the_very_first_byte_raises(self):
        with self.assertRaises(rd.DecompressError):
            rd.decompress(b"\x19\x01", 3)

    def test_asking_for_the_wrong_length_can_overshoot_it(self):
        """Which is why reconstruct() checks the produced length against the
        descriptor rather than trusting the decoder to stop on the mark."""
        out, _consumed, _stats = rd.decompress(b"\x14ABC", 2)
        self.assertGreater(len(out), 2)

    @unittest.skipUnless(READY, "preserved images not present")
    def test_a_modified_handler_makes_the_tool_refuse(self):
        data = bytearray(rd.INSTALLED.read_bytes())
        offset = 0x11000 + rd.HANDLER_SPAN[0] - 0x10000
        data[offset] ^= 0xFF
        view = fi.ImageView(bytes(data), 0x10000)
        with self.assertRaises(rd.DecompressError) as caught:
            rd.reconstruct(view, "tampered")
        self.assertIn("does not match", str(caught.exception))

    @unittest.skipUnless(READY, "preserved images not present")
    def test_a_corrupted_compressed_stream_does_not_decode_to_the_descriptor(self):
        """Flip one byte of the real stream: it must raise, or produce a
        different length, or produce different bytes. It must not be ignored."""
        data = bytearray(rd.INSTALLED.read_bytes())
        good, _link = rd.build()
        (result, payload), _vendor = good
        data[result.source_lo - 0x10000 + 0x20] ^= 0xFF
        view = fi.ImageView(bytes(data), 0x10000)
        try:
            spoiled, spoiled_bytes = rd.reconstruct(view, "installed")
        except rd.DecompressError:
            return
        self.assertNotEqual(spoiled_bytes, payload)
        self.assertFalse(all(check.ok for check in spoiled.checks)
                         and spoiled.output_sha256 == result.output_sha256)


class Writing(unittest.TestCase):

    def test_it_refuses_to_write_under_dumps(self):
        with self.assertRaises(rd.DecompressError):
            rd.write_outputs((), rd.ROOT / "dumps/anywhere")

    @unittest.skipUnless(READY, "preserved images not present")
    def test_writing_is_exclusive_and_idempotent(self):
        results, _link = rd.build()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "imports"
            first = rd.write_outputs(results, out)
            self.assertEqual(len(first), 2)
            self.assertEqual(rd.write_outputs(results, out), ())

    @unittest.skipUnless(READY, "preserved images not present")
    def test_it_refuses_to_overwrite_different_content(self):
        results, _link = rd.build()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "imports"
            out.mkdir()
            (out / results[0][0].name).write_bytes(b"not the region")
            with self.assertRaises(rd.DecompressError):
                rd.write_outputs(results, out)


@unittest.skipUnless(READY, "preserved images not present")
class RealImages(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.results, cls.link = rd.build()

    def test_the_handler_is_byte_identical_in_both_releases(self):
        digests = {result.handler_sha256 for result, _payload in self.results}
        self.assertEqual(digests, {rd.HANDLER_SHA256},
                         "one decoder covers both releases only because the "
                         "handler bytes are the same in both")

    def test_both_regions_fill_their_descriptor_exactly(self):
        for result, payload in self.results:
            self.assertEqual(result.produced_length, result.declared_length)
            self.assertEqual(len(payload), 0xB04)

    def test_the_unconsumed_tail_is_zero_padding_to_a_word(self):
        for result, _payload in self.results:
            self.assertLess(result.padding_length, 4)
            self.assertEqual(
                (result.consumed_length + result.padding_length) % 4, 0)

    def test_every_structural_check_passes(self):
        for result, _payload in self.results:
            for check in result.checks:
                self.assertTrue(check.ok, check.name)
        for check in self.link.checks:
            self.assertTrue(check.ok, check.name)

    def test_the_two_releases_differ_only_where_the_releases_differ(self):
        by_delta = dict(self.link.deltas)
        self.assertIn(rd.RELOCATION_DELTA, by_delta)
        self.assertGreater(len(by_delta[rd.RELOCATION_DELTA]),
                           len(self.link.differing_words) // 2)
        self.assertLess(self.link.differing_bytes, self.link.length // 20)

    def test_the_output_is_deterministic(self):
        again, _link = rd.build()
        self.assertEqual([hashlib.sha256(payload).hexdigest()
                          for _result, payload in again],
                         [result.output_sha256
                          for result, _payload in self.results])

    def test_the_report_does_not_claim_the_device_was_observed(self):
        text = "\n".join(rd.report_lines(self.results, self.link))
        self.assertIn("STRUCTURAL", text)
        self.assertIn("nothing here observed the device", text)


if __name__ == "__main__":
    unittest.main()
