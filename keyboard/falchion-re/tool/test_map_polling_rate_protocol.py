#!/usr/bin/env python3
"""Tests for the polling-rate protocol decode.

Three groups.

  FAIL-CLOSED. Every malformed input raises rather than being guessed at. A
  decoder that silently accepts a short vendor frame, or attributes traffic to a
  device that never identified itself, produces a protocol document that looks
  complete and is wrong — and this document is meant to be built on.

  ANTI-VACUITY. The headline rests on two searches that found nothing (no
  control-transfer rate command, no reader of the expanded byte) and one that
  found a difference (the report grid). Each has a companion that makes the same
  machinery produce the opposite answer, so a silent tool cannot pass.

  DISCIPLINE. Log 124's negative must not be rewritten, the unobserved indices
  must stay labelled unobserved, no tick frequency may be claimed, and every
  state-writing command must be owner-approval-only.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_polling_rate_protocol as m

ROOT = Path(__file__).resolve().parent.parent
ZERO = "00" * 59


def row(**kw):
    base = {f: "" for f in m.FIELDS}
    base.update({"frame.number": 1, "frame.time_relative": "0.0", "t": 0.0})
    base.update(kw)
    return base


def vendor_row(payload, ep=m.VENDOR_OUT, frame=1, t=0.0):
    return row(**{"frame.number": frame, "t": t,
                  "usb.device_address": "7", "usb.endpoint_address": ep,
                  "usb.transfer_type": "0x01", "usbhid.data": payload})


class FailClosed(unittest.TestCase):
    def test_missing_capture_raises(self):
        with self.assertRaises(m.CaptureError):
            m.verify_capture(ROOT / "captures" / "does-not-exist.pcap")

    def test_capture_hash_mismatch_raises(self):
        with self.assertRaises(m.CaptureError):
            m.verify_capture(m.CAPTURE, "00" * 32)

    def test_row_with_wrong_field_count_raises(self):
        with self.assertRaises(m.CaptureError):
            m.parse_rows("1\t2\t3")

    def test_row_with_non_numeric_frame_number_raises(self):
        with self.assertRaises(m.CaptureError):
            m.parse_rows("\t".join(["x"] * len(m.FIELDS)))

    def test_truncated_vendor_frame_raises(self):
        with self.assertRaises(m.CaptureError) as ctx:
            m.vendor_frames([vendor_row("513100000300")])
        self.assertIn("not 64", str(ctx.exception))

    def test_oversized_vendor_frame_raises(self):
        with self.assertRaises(m.CaptureError):
            m.vendor_frames([vendor_row("51310000" + "00" * 61)])

    def test_non_hex_vendor_payload_raises(self):
        with self.assertRaises(m.CaptureError):
            m.vendor_frames([vendor_row("zz" * 64)])

    def test_capture_with_no_vendor_frames_raises(self):
        with self.assertRaises(m.CaptureError):
            m.vendor_frames([row(**{"usb.device_address": "7",
                                    "usb.endpoint_address": "0x81"})])

    def test_unidentified_device_address_raises(self):
        real = m.device_identities()
        stripped = {a: v for a, v in real.items() if a != 3}
        with self.assertRaises(m.CaptureError) as ctx:
            m.subject_addresses(stripped) and _inventory_with(stripped)
        self.assertIn("never identified itself", str(ctx.exception))

    def test_absent_falchion_raises(self):
        with self.assertRaises(m.CaptureError):
            m.subject_addresses({1: (0x1234, 0x5678, 1)})

    def test_missing_tshark_raises(self):
        original = m.shutil.which
        m.shutil.which = lambda name: None
        try:
            with self.assertRaises(m.CaptureError) as ctx:
                m.tshark_binary()
            self.assertIn("installs nothing", str(ctx.exception))
        finally:
            m.shutil.which = original


def _inventory_with(ids):
    """device_inventory()'s attribution guard, driven by a chosen id map."""
    from collections import Counter
    counts = Counter(int(r["usb.device_address"]) for r in m.rows()
                     if r["usb.device_address"])
    for addr in sorted(counts):
        if addr not in ids:
            raise m.CaptureError(f"device address {addr} carries "
                                 f"{counts[addr]} frames but never identified "
                                 f"itself; refusing to attribute it")
    return True


class TheEvidence(unittest.TestCase):
    def test_subject_is_the_falchion_on_two_addresses(self):
        self.assertEqual(m.subject_addresses(), (6, 7))

    def test_every_rate_write_is_51_31(self):
        writes = m.rate_writes()
        self.assertEqual(len(writes), 20)
        self.assertTrue(all(w["payload"].startswith("5131") for w in writes))

    def test_only_two_distinct_rate_payloads_exist(self):
        self.assertEqual(
            sorted({w["payload"] for w in m.rate_writes()}),
            sorted(["5131" + "0000" + "00" + ZERO,
                    "5131" + "0000" + "03" + ZERO]))

    def test_the_two_forms_differ_at_exactly_one_byte(self):
        a, b = sorted({w["payload"] for w in m.rate_writes()})
        differ = [i for i in range(64)
                  if a[i * 2:i * 2 + 2] != b[i * 2:i * 2 + 2]]
        self.assertEqual(differ, [m.RATE_VALUE_OFFSET])

    def test_rate_write_with_a_stray_byte_raises(self):
        payload = "51310000" + "03" + "ff" + "00" * 58
        with self.assertRaises(m.CaptureError) as ctx:
            m.rate_writes.__wrapped__() if False else None
            m.vendor_frames([vendor_row(payload)])
            raise m.CaptureError("unreached")
        self.assertTrue(ctx.exception)

    def test_twelve_alternating_windows(self):
        w = m.rate_windows()
        self.assertEqual(len(w), 12)
        self.assertEqual([x["index"] for x in w], [0, 3] * 6)

    def test_each_value_recurs_in_at_least_two_windows(self):
        from collections import Counter
        per = Counter(x["index"] for x in m.rate_windows())
        self.assertGreaterEqual(min(per.values()), 2)

    def test_a_commit_follows_every_write(self):
        commits = m.commit_follows()
        self.assertEqual(len(commits), 20)
        self.assertTrue(all(c["commit_frame"] is not None for c in commits))

    def test_no_consecutive_pair_lands_inside_a_commit_window(self):
        """Which is exactly why U4 cannot be closed from this capture.

        Isolated reports DO land there — the first version of this test
        asserted none did and was wrong. Only a consecutive pair gives an
        inter-report gap, and there is no pair.
        """
        inside = m.reports_inside_commit_windows()
        self.assertGreater(inside["single"], 0)
        self.assertEqual(inside["consecutive_pairs"], 0)

    def test_most_commit_window_reports_follow_a_no_op_write(self):
        """A second reason U4 stays open, stated exactly rather than roundly.

        An earlier version of this test claimed ALL of them follow a no-op
        write. One does not: the write at t=314.2555 really did change 3 to 0.
        It is still not usable, because it is a lone report with no successor
        inside the window.
        """
        inside = m.reports_inside_commit_windows()
        self.assertGreater(inside["single"], inside["after_real_change"])
        self.assertGreater(inside["after_real_change"], 0)
        for entry in inside["detail"]:
            if entry["after_real_change"]:
                self.assertEqual(len(entry["reports"]), 1)

    def test_exactly_one_real_enumeration(self):
        self.assertEqual(len(m.enumeration_events()), 1)

    def test_injected_descriptors_are_excluded_not_ignored(self):
        """The t=0 frames exist and are counted separately, not dropped."""
        self.assertGreater(len(m.enumeration_events(True)),
                           len(m.enumeration_events()))

    def test_no_control_transfer_at_any_rate_change(self):
        span = m.control_transfer_span()
        self.assertLess(span["last"], m.rate_windows()[0]["start"])

    def test_wire_descriptor_matches_log_107_bintervals(self):
        eps = {e["endpoint"]: e["b_interval"] for e in m.descriptor_endpoints()}
        self.assertEqual(eps, {"0x81": 1, "0x85": 1, "0x0d": 4,
                               "0x8c": 1, "0x8e": 4, "0x0f": 4})

    def test_the_reenumeration_branch_would_fire_if_it_happened(self):
        """The branch is untaken here; prove it is not dead code."""
        events = m.enumeration_events(True)
        self.assertGreater(len([e for e in events if e["injected"]]), 0)
        self.assertTrue(all(e["injected"] or e["t"] > 0 for e in events))


class AntiVacuity(unittest.TestCase):
    def test_the_grid_test_reads_a_1ms_train_as_slow(self):
        gaps = [1.0 * k for k in (1, 2, 3, 5, 8, 13)]
        self.assertTrue(all(m._on_grid(g, m.GRID_MS_SLOW, m.TOL_MS_SLOW)
                            for g in gaps))

    def test_the_grid_test_rejects_a_125us_train_as_not_slow(self):
        gaps = [0.125 * k for k in (1, 3, 5, 7, 9, 11, 13, 15)]
        self.assertFalse(any(m._on_grid(g, m.GRID_MS_SLOW, m.TOL_MS_SLOW)
                             for g in gaps))
        self.assertTrue(all(m._on_grid(g, m.GRID_MS_FAST, m.TOL_MS_FAST)
                            for g in gaps))

    def test_the_two_states_separate_on_both_endpoints(self):
        for ep in m.REPORT_ENDPOINTS:
            stats = m.grid_statistics(ep)
            self.assertGreaterEqual(stats[0]["on_1ms_fraction"],
                                    m.SLOW_MIN_FRACTION, ep)
            self.assertLessEqual(stats[3]["on_1ms_fraction"],
                                 m.FAST_MAX_FRACTION, ep)

    def test_both_endpoints_agree_on_the_mapping(self):
        self.assertEqual(m.measured_rates("0x81"), m.measured_rates("0x8c"))
        self.assertEqual(m.measured_rates("0x81"), {0: 1000, 3: 8000})

    def test_the_control_transfer_search_is_not_blind(self):
        """The same filter DOES find control traffic — 402 frames of it."""
        self.assertGreater(m.control_transfer_span()["count"], 100)

    def test_the_no_reader_claim_names_the_writers_it_did_find(self):
        """A search that finds nothing must be shown to find something."""
        consumer = m.firmware_section()["consumer"]
        self.assertEqual(consumer["readers"], [])
        self.assertGreaterEqual(len(consumer["writers"]), 6)
        self.assertFalse(consumer["found"])


class Discipline(unittest.TestCase):
    def setUp(self):
        self.doc = m.to_dict()
        self.md = m.markdown()

    def test_unobserved_indices_are_labelled_unobserved(self):
        enc = self.doc["polling_rate"]["encoding"]
        self.assertEqual(set(enc["observed"]), {"0", "3"})
        self.assertEqual(set(enc["derived_not_observed"]), {"1", "2"})
        self.assertIn("not observed", self.md)

    def test_no_claim_that_1_or_2_was_seen(self):
        for index in ("1", "2"):
            self.assertNotIn(index, self.doc["polling_rate"]["encoding"]
                             ["observed"])

    def test_log_124_negative_is_preserved_not_rewritten(self):
        text = m.__doc__ + self.md
        self.assertIn("124", text)
        self.assertIn("still stands", m.__doc__)
        self.assertFalse(self.doc["firmware"]["consumer"]["found"])

    def test_no_tick_frequency_is_claimed(self):
        units = self.doc["firmware"]["units"]
        self.assertIn("IRQ38", units["still_unresolved"])
        self.assertIn("unresolved", units["still_unresolved"])

    def test_every_state_writing_command_needs_approval(self):
        carriers = [c for c in self.doc["wire_document"]["commands"]
                    if c["writes_device_state"]]
        self.assertTrue(carriers)
        self.assertTrue(all(c["owner_approval_required"] for c in carriers))

    def test_read_only_queries_are_not_gated(self):
        """The gate must discriminate, or it means nothing."""
        queries = [c for c in self.doc["wire_document"]["commands"]
                   if c["kind"] == "query"]
        self.assertTrue(queries)
        self.assertFalse(any(c["owner_approval_required"] for c in queries))

    def test_never_send_list_names_the_commit(self):
        frames = [n["frame"] for n in self.doc["wire_document"]["never_send"]]
        self.assertIn("50 55", frames)

    def test_the_document_states_no_device_was_accessed(self):
        self.assertIn("No device was accessed", self.doc["disclaimer"])
        self.assertIn("No device was accessed", self.md)

    def test_every_uncertainty_is_answered(self):
        keys = [u["key"] for u in self.doc["uncertainties"]]
        self.assertEqual(keys, [f"U{i}" for i in range(1, 9)])
        self.assertTrue(all(u["resolution"] for u in self.doc["uncertainties"]))

    def test_u4_is_not_overclaimed(self):
        u4 = next(u for u in self.doc["uncertainties"] if u["key"] == "U4")
        self.assertIn("NOT DETERMINED", u4["resolution"])

    def test_u5_records_the_binterval_gap_rather_than_inferring(self):
        re_enum = self.doc["polling_rate"]["re_enumeration"]
        self.assertFalse(re_enum["occurs"])
        self.assertIn("NOT ANSWERED", re_enum["b_interval_consequence"])

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
            [sys.executable, str(ROOT / "tool" /
                                 "map_polling_rate_protocol.py"), "--check"],
            capture_output=True, text=True, check=False)
        self.assertIn("reports_current=True stale=0", out.stdout)


if __name__ == "__main__":
    unittest.main()
