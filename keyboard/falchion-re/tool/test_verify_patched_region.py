#!/usr/bin/env python3
"""Tests for the Phase 8 artefact validator.

The two that matter most are the failure demonstrations. A validator that only
ever passes proves nothing, so this file shows that (a) corrupting a control
byte changes the token structure and is detected, and (b) a patched literal
that a later back-reference copies IS caught as propagation — demonstrated on a
synthetic stream small enough to reason about by hand.

No device access, no writes outside a temporary directory.
"""
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))

import verify_patched_region as vp

READY = (all(path.exists() for path, _base in vp.SOURCES.values())
         and all((vp.GENERATED / name).exists()
                 for pair in vp.ARTEFACTS.values() for name in pair))


class SyntheticStream(unittest.TestCase):
    """A stream small enough to check by hand.

    control 0x1d = literal field 5 (emits 4), bit 3 set (back-reference),
    copy field 1 (emits 1 + 2 = 3 bytes). Then four literals and a distance.
    """

    STREAM = b"\x1dABCD\x04"
    LENGTH = 7

    def test_the_synthetic_stream_decodes_as_reasoned(self):
        decoded = vp.decode(self.STREAM, self.LENGTH)
        self.assertEqual(decoded.output, b"ABCDABC")
        self.assertEqual(decoded.consumed, len(self.STREAM))
        self.assertEqual(len(decoded.tokens), 1)

    def test_provenance_separates_literals_from_copies(self):
        decoded = vp.decode(self.STREAM, self.LENGTH)
        kinds = [kind for kind, _ in decoded.provenance]
        self.assertEqual(kinds, ["literal"] * 4 + ["copy"] * 3)
        self.assertEqual([off for _kind, off in decoded.provenance[:4]],
                         [1, 2, 3, 4])

    def test_a_patched_literal_that_is_later_copied_IS_detected(self):
        """The propagation case, demonstrated. Output byte 0 is a literal,
        and the back-reference copies it to byte 4 — so patching byte 0 would
        silently change byte 4 as well."""
        decoded = vp.decode(self.STREAM, self.LENGTH)
        reads = vp.propagation_reads(decoded, 0, 1)
        self.assertEqual(reads, ((0, 4),))

    def test_patching_that_literal_really_does_propagate(self):
        """Not just detected in theory — the decoded output proves it."""
        patched = bytearray(self.STREAM)
        patched[1] = ord("Z")               # the literal for output byte 0
        after = vp.decode(bytes(patched), self.LENGTH)
        self.assertEqual(after.output, b"ZBCDZBC")
        differing = [i for i in range(self.LENGTH)
                     if after.output[i] != b"ABCDABC"[i]]
        self.assertEqual(differing, [0, 4],
                         "one patched literal changed two output bytes")

    def test_a_literal_with_no_later_reader_does_not_propagate(self):
        """Output byte 3 is a literal the back-reference never reaches."""
        decoded = vp.decode(self.STREAM, self.LENGTH)
        self.assertEqual(vp.propagation_reads(decoded, 3, 4), ())
        patched = bytearray(self.STREAM)
        patched[4] = ord("Z")
        after = vp.decode(bytes(patched), self.LENGTH)
        differing = [i for i in range(self.LENGTH)
                     if after.output[i] != b"ABCDABC"[i]]
        self.assertEqual(differing, [3])

    def test_corrupting_a_control_byte_changes_the_token_structure(self):
        """The other failure mode: a patch landing on a token parameter."""
        before = vp.decode(self.STREAM, self.LENGTH)
        corrupted = bytearray(self.STREAM)
        corrupted[0] = 0x2D                 # copy field 1 -> 2
        after = vp.decode(bytes(corrupted), self.LENGTH)
        self.assertNotEqual(before.tokens, after.tokens)

    def test_corrupting_a_distance_byte_changes_the_output_wholesale(self):
        corrupted = bytearray(self.STREAM)
        corrupted[5] = 0x02                 # distance 4 -> 2
        after = vp.decode(bytes(corrupted), self.LENGTH)
        self.assertNotEqual(after.output, b"ABCDABC")

    def test_a_truncated_stream_raises_rather_than_returning_short(self):
        with self.assertRaises(vp.VerifyError) as caught:
            vp.decode(self.STREAM[:-1], self.LENGTH)
        self.assertIn("exhausted", str(caught.exception))

    def test_a_back_reference_before_the_start_raises(self):
        with self.assertRaises(vp.VerifyError) as caught:
            vp.decode(b"\x1dABCD\x40", self.LENGTH)
        self.assertIn("distance", str(caught.exception))

    def test_an_overlapping_back_reference_repeats_what_it_wrote(self):
        decoded = vp.decode(b"\x1aA\x01", 4)
        self.assertEqual(decoded.output, b"AAAA")


class IndependentPrimitives(unittest.TestCase):

    def test_the_chunked_crc_sums_per_chunk_results(self):
        data = bytes(range(256)) * 0x400          # 0x40000 bytes
        expected = 0
        for start in range(0, len(data), 0x10000):
            expected = (expected + zlib.crc32(data[start:start + 0x10000])) \
                & vp.M32
        self.assertEqual(vp.independent_chunked_crc(data, 0, len(data)),
                         expected)

    def test_the_chunked_crc_differs_from_a_single_crc(self):
        """Which is the whole reason the chunked form had to be recovered."""
        data = bytes(range(256)) * 0x400
        self.assertNotEqual(vp.independent_chunked_crc(data, 0, len(data)),
                            zlib.crc32(data))

    def test_the_word_sum_is_a_plain_little_endian_sum(self):
        data = struct.pack("<4I", 1, 2, 3, 0xFFFFFFFF)
        self.assertEqual(vp.independent_word_sum(data, 0, len(data)),
                         (1 + 2 + 3 + 0xFFFFFFFF) & vp.M32)

    def test_the_validator_imports_nothing_from_the_builder(self):
        source = Path(vp.__file__).read_text()
        for banned in ("build_offline_image", "build_modified_image"):
            self.assertNotIn(banned, source, banned)


@unittest.skipUnless(READY, "artefacts or evidence not present")
class RealArtefacts(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.payload = vp.to_dict()

    def test_every_check_passes_for_both_releases(self):
        for item in vp.all_checks(self.payload):
            self.assertTrue(item["ok"], item["name"])

    def test_both_releases_were_validated(self):
        self.assertEqual(sorted(self.payload["releases"]),
                         ["installed", "vendor"])

    def test_no_decoded_byte_changed_outside_the_span(self):
        for name, release in self.payload["releases"].items():
            self.assertEqual(release["decoded_diff_outside_span"], [], name)

    def test_there_is_no_propagation_in_either_release(self):
        for name, release in self.payload["releases"].items():
            self.assertEqual(release["propagation_reads"], 0, name)

    def test_the_rollback_is_byte_identical_in_both_releases(self):
        for name, release in self.payload["releases"].items():
            self.assertEqual(release["rollback_sha256"],
                             release["source_sha256"], name)

    def test_the_literal_offsets_are_the_same_in_both_releases(self):
        """The stream position is identical; only the flash offset relocates."""
        installed = self.payload["releases"]["installed"]
        vendor = self.payload["releases"]["vendor"]
        self.assertEqual(installed["literal_stream_offsets"],
                         vendor["literal_stream_offsets"])
        self.assertEqual(
            installed["literal_flash_offsets"][0]
            - vendor["literal_flash_offsets"][0], 0x2C,
            "the flash offsets differ by exactly the measured relocation")

    def test_the_patched_images_differ_from_their_sources(self):
        for name, release in self.payload["releases"].items():
            self.assertNotEqual(release["artefact_sha256"],
                                release["source_sha256"], name)

    def test_every_artefact_name_carries_untested(self):
        for release in self.payload["releases"].values():
            self.assertIn("UNTESTED", release["artefact"])
            self.assertIn("UNTESTED", release["rollback"])

    def test_acceptance_is_never_claimed(self):
        self.assertIn("NOT CLAIMED", self.payload["acceptance"])
        text = "\n".join(vp.report_lines())
        self.assertIn("NOT CLAIMED", text)
        for word in ("will boot", "boots correctly", "verified to boot"):
            self.assertNotIn(word, text.lower())

    def test_the_notes_on_disk_are_current(self):
        stale = [name for name, body in vp.bodies().items()
                 if not (vp.NOTES / name).exists()
                 or (vp.NOTES / name).read_text() != body]
        self.assertEqual(stale, [],
                         "run python3 tool/verify_patched_region.py --write")

    def test_json_is_deterministic(self):
        self.assertEqual(vp.bodies(), vp.bodies())

    def test_the_replacement_is_marked_as_a_test_build(self):
        self.assertIn("UNTESTED", self.payload["replacement_string"])
        self.assertEqual(len(self.payload["replacement_string"]),
                         len(self.payload["original_string"]))


@unittest.skipUnless(READY, "artefacts or evidence not present")
class MissingArtefact(unittest.TestCase):

    def test_a_missing_artefact_fails_closed(self):
        original = vp.GENERATED
        vp.GENERATED = Path("/nonexistent-generated-dir")
        try:
            with self.assertRaises(vp.VerifyError) as caught:
                vp.verify_release("installed")
            self.assertIn("missing", str(caught.exception))
        finally:
            vp.GENERATED = original


if __name__ == "__main__":
    unittest.main()
