#!/usr/bin/env python3
"""Offline tests for the Phase 5B USB routing map.

Synthetic tables for the parser's bounds, the preserved region and host
captures for the real numbers. Every malformed input is asserted to RAISE: a
descriptor parser that silently accepts a truncated table would produce an
endpoint map that looks complete and is wrong, and a custom firmware built on
it would enumerate incorrectly. No device access, no writes outside a
temporary directory.
"""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_usb_routing as ur

READY = ((ur.IMPORTS / ur.REGIONS["installed"][0]).exists()
         and ur.DESCRIPTOR_LOG.exists() and ur.REPORT_LOG.exists())


def synthetic(num_interfaces=1, report_length=4, report_offset=0x08,
              flags=0x01, size=0x400, base=0x18000000):
    """A minimal region holding one parameter table."""
    data = bytearray(size)
    table = ur.TABLE_OFFSET
    struct.pack_into("<3H", data, table, 0x0B05, 0x1B7E, 0x0159)
    data[table + 0x10] = 0x20
    data[table + 0x11] = 0xFA
    data[table + 0x12] = num_interfaces
    for index in range(max(num_interfaces, 0)):
        record = table + ur.INTERFACE_ARRAY + index * ur.INTERFACE_STRIDE
        if record + ur.INTERFACE_STRIDE > len(data):
            break
        data[record + 0x02] = flags
        struct.pack_into("<2H", data, record + 0x04, 8, 0)
        struct.pack_into("<H", data, record + 0x0C, report_length)
        struct.pack_into("<I", data, record + 0x10, base + report_offset)
        data[record + 0x14] = 1
    return bytes(data)


class ParserBounds(unittest.TestCase):
    """Each of these must raise. None may return a partial map."""

    def parse(self, data, base=0x18000000):
        original = ur.REGIONS["installed"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "region.bin"
            path.write_bytes(data)
            saved_imports, ur.IMPORTS = ur.IMPORTS, Path(directory)
            ur.REGIONS["installed"] = ("region.bin", base)
            try:
                return ur.parse_region("installed")
            finally:
                ur.IMPORTS = saved_imports
                ur.REGIONS["installed"] = original

    def test_a_well_formed_table_parses(self):
        parsed, _data = self.parse(synthetic())
        self.assertEqual(parsed.num_interfaces, 1)
        self.assertEqual(parsed.interfaces[0].in_max_packet, 8)

    def test_a_region_too_short_for_the_table_raises(self):
        """Big enough for the header, too small for the 0x8c-byte table the
        firmware copies. The parser must refuse rather than read short."""
        data = synthetic()[:ur.TABLE_OFFSET + 0x20]
        with self.assertRaises(ur.RoutingError) as caught:
            self.parse(data)
        self.assertIn("does not fit", str(caught.exception))

    def test_zero_interfaces_raises(self):
        with self.assertRaises(ur.RoutingError):
            self.parse(synthetic(num_interfaces=0))

    def test_more_interfaces_than_the_firmware_accepts_raises(self):
        """FUN_18018b70 rejects bNumInterfaces > 5 and so must this."""
        with self.assertRaises(ur.RoutingError) as caught:
            self.parse(synthetic(num_interfaces=6))
        self.assertIn("outside 1..5", str(caught.exception))

    def test_an_interface_record_past_the_region_raises(self):
        """A defensive guard, tested honestly. With the real 0x8c table length
        five records always fit, so the guard is unreachable from a real
        image; shrinking the copied length exposes it without pretending the
        firmware could produce this."""
        saved, ur.TABLE_LENGTH = ur.TABLE_LENGTH, 0x20
        try:
            data = synthetic(num_interfaces=5)[:ur.TABLE_OFFSET + 0x30]
            with self.assertRaises(ur.RoutingError) as caught:
                self.parse(data)
            self.assertIn("runs past the region", str(caught.exception))
        finally:
            ur.TABLE_LENGTH = saved

    def test_five_records_fit_the_real_table_length(self):
        """Which is why the guard above cannot fire on a real image."""
        self.assertEqual(
            ur.INTERFACE_ARRAY + ur.MAX_INTERFACES * ur.INTERFACE_STRIDE,
            ur.TABLE_LENGTH)

    def test_a_report_pointer_outside_the_region_raises(self):
        with self.assertRaises(ur.RoutingError) as caught:
            self.parse(synthetic(report_offset=0x9000))
        self.assertIn("does not lie inside the region", str(caught.exception))

    def test_a_report_length_running_past_the_region_raises(self):
        with self.assertRaises(ur.RoutingError):
            self.parse(synthetic(report_offset=0x3F0, report_length=0x100))

    def test_an_endpoint_flag_of_zero_yields_no_endpoints(self):
        """An interface with neither bit set contributes 0x12 descriptor bytes
        and no endpoint, rather than being skipped."""
        parsed, _data = self.parse(synthetic(flags=0x00))
        self.assertEqual(parsed.interfaces[0].endpoints, 0)
        self.assertEqual(parsed.interfaces[0].descriptor_bytes,
                         ur.PER_INTERFACE_BYTES)

    def test_both_endpoint_flags_give_two_endpoints(self):
        parsed, _data = self.parse(synthetic(flags=0x03))
        self.assertEqual(parsed.interfaces[0].endpoints, 2)
        self.assertEqual(parsed.total_length,
                         ur.CONFIG_HEADER_BYTES + ur.PER_INTERFACE_BYTES
                         + 2 * ur.PER_ENDPOINT_BYTES)


class ItemWalk(unittest.TestCase):
    """The walk must refuse a malformed descriptor rather than report a
    partial item list as well-formed."""

    def test_a_short_form_size_of_three_means_four_bytes(self):
        items = ur.hid_items(bytes([0x27, 0xFF, 0xFF, 0x00, 0x00]))
        self.assertEqual(items, [("Global", b"\xff\xff\x00\x00")])

    def test_an_item_running_past_the_end_raises(self):
        with self.assertRaises(ur.RoutingError) as caught:
            ur.hid_items(bytes([0x27, 0xFF]))
        self.assertIn("not\nwell-formed".replace("\n", " "),
                      str(caught.exception))

    def test_a_truncated_descriptor_is_not_reported_well_formed(self):
        good = bytes([0x05, 0x59, 0x09, 0x01, 0xA1, 0x01, 0xC0])
        self.assertEqual(len(ur.hid_items(good)), 4)
        with self.assertRaises(ur.RoutingError):
            ur.hid_items(good[:-2])

    def test_item_kinds_are_decoded_from_the_prefix(self):
        items = ur.hid_items(bytes([0x05, 0x59, 0x09, 0x01, 0xA1, 0x01]))
        self.assertEqual([kind for kind, _data in items],
                         ["Global", "Local", "Main"])

    def test_a_missing_host_section_raises(self):
        original = ur.LAMPARRAY_HEADING
        ur.LAMPARRAY_HEADING = "Report Descriptor: (length is 99999)"
        try:
            with self.assertRaises(ur.RoutingError):
                ur.host_parsed_lamparray()
        finally:
            ur.LAMPARRAY_HEADING = original


class HostCaptures(unittest.TestCase):

    @unittest.skipUnless(READY, "preserved captures not present")
    def test_the_standard_descriptor_chain_walks_cleanly(self):
        blob, items = ur.host_standard_descriptors()
        self.assertEqual(sum(len(item) for _o, _k, item in items), len(blob))
        self.assertEqual([kind for _o, kind, _i in items][:2], [1, 2])

    def test_a_truncated_descriptor_chain_raises(self):
        original = ur.DESCRIPTOR_LOG
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.txt"
            # A descriptor whose bLength runs past the capture.
            path.write_text("00000000: 12 01 00 02  ....\n")
            ur.DESCRIPTOR_LOG = path
            try:
                with self.assertRaises(ur.RoutingError) as caught:
                    ur.host_standard_descriptors()
                self.assertIn("runs past", str(caught.exception))
            finally:
                ur.DESCRIPTOR_LOG = original

    def test_a_zero_length_descriptor_raises_instead_of_looping(self):
        original = ur.DESCRIPTOR_LOG
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "zero.txt"
            path.write_text("00000000: 00 01 00 02  ....\n")
            ur.DESCRIPTOR_LOG = path
            try:
                with self.assertRaises(ur.RoutingError):
                    ur.host_standard_descriptors()
            finally:
                ur.DESCRIPTOR_LOG = original


@unittest.skipUnless(READY, "preserved region or captures not present")
class RealEvidence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.analysis = ur.build()

    def test_every_check_passes(self):
        for item in self.analysis.checks:
            self.assertTrue(item["ok"], item["name"])

    def test_the_rebuilt_total_length_is_the_host_value(self):
        self.assertEqual(self.analysis.sets["installed"].total_length, 0x8D)

    def test_all_five_report_descriptors_live_in_the_region(self):
        installed = self.analysis.sets["installed"]
        self.assertEqual(len(installed.interfaces), 5)
        self.assertEqual([item.report_length for item in installed.interfaces],
                         [68, 34, 182, 23, 327])

    def test_interface_four_is_out_only(self):
        """The one interface with no IN endpoint, matching the host."""
        four = self.analysis.sets["installed"].interfaces[4]
        self.assertFalse(four.has_in)
        self.assertTrue(four.has_out)
        self.assertEqual(four.out_max_packet, 64)

    def test_both_releases_are_symmetric_except_bcddevice(self):
        installed = self.analysis.sets["installed"]
        vendor = self.analysis.sets["vendor"]
        self.assertEqual(installed.total_length, vendor.total_length)
        self.assertEqual(
            [item.report_length for item in installed.interfaces],
            [item.report_length for item in vendor.interfaces])
        self.assertNotEqual(installed.bcd_device, vendor.bcd_device)

    def test_the_report_pointers_track_each_release_base(self):
        for release, item in self.analysis.sets.items():
            for one in item.interfaces:
                self.assertEqual(one.report_pointer - item.base,
                                 one.report_offset,
                                 f"{release} interface {one.index}")

    def test_only_the_control_and_boot_endpoints_are_required(self):
        required = [route.endpoint for route in ur.ROUTES if not route.optional]
        self.assertEqual(sorted(required), ["0x00", "0x81"])

    def test_the_lamparray_basis_does_not_claim_byte_identity(self):
        """Log 108's correction, pinned. Interface 4 was unbound on the host,
        so no raw report-descriptor bytes for it exist in this repository and
        no claim of byte-identity is provable from it."""
        route, = [item for item in ur.ROUTES if item.endpoint == "0x0f"]
        lowered = route.kind_basis.lower()
        self.assertNotIn("byte-identical", lowered)
        self.assertIn("structurally", lowered)
        self.assertIn("cannot be checked", lowered)

    def test_byte_identity_is_claimed_only_where_raw_bytes_are_preserved(self):
        """The invariant, not a hand-listed set: any route whose basis claims
        byte-identity must name an interface this repository actually holds
        raw host bytes for. Interface 4 is the one that does not."""
        for route in ur.ROUTES:
            if "byte-identical" not in route.kind_basis:
                continue
            self.assertGreaterEqual(route.interface, 0, route.endpoint)
            self.assertTrue(ur.raw_bytes_available_for(route.interface),
                            f"{route.endpoint} claims byte-identity for "
                            f"interface {route.interface}, which has no raw "
                            "host bytes in this repository")
        claims = {route.endpoint for route in ur.ROUTES
                  if "byte-identical" in route.kind_basis}
        self.assertNotIn("0x0f", claims)
        self.assertTrue(claims, "the stronger claim must survive where it is "
                                "supported")

    def test_no_raw_host_bytes_exist_for_interface_four(self):
        self.assertFalse(ur.raw_bytes_available_for(ur.LAMPARRAY_INTERFACE))
        for index in range(4):
            self.assertTrue(ur.raw_bytes_available_for(index))

    def test_the_lamparray_item_walk_matches_the_host_listing(self):
        four = self.analysis.sets["installed"].interfaces[
            ur.LAMPARRAY_INTERFACE]
        data = self.analysis.raw["installed"][
            four.report_offset:four.report_offset + four.report_length]
        self.assertEqual(ur.hid_items(data), ur.host_parsed_lamparray())
        self.assertEqual(len(ur.host_parsed_lamparray()), 155)

    def test_every_route_carries_a_confidence_and_a_basis(self):
        allowed = {"observed", "strongly-inferred", "hypothesis", "unresolved"}
        for route in ur.ROUTES:
            self.assertIn(route.confidence, allowed)
            self.assertGreater(len(route.kind_basis), 40, route.endpoint)

    def test_json_is_deterministic(self):
        first = json.dumps(ur.to_dict(ur.build()), sort_keys=True)
        second = json.dumps(ur.to_dict(ur.build()), sort_keys=True)
        self.assertEqual(first, second)

    def test_the_notes_on_disk_are_current(self):
        payload = json.dumps(ur.to_dict(self.analysis), indent=2,
                             sort_keys=True) + "\n"
        stale = []
        for name, body in (("usb-routing.json", payload),
                           ("usb-routing.md", ur.markdown(self.analysis))):
            path = ur.NOTES / name
            if not path.exists() or path.read_text() != body:
                stale.append(name)
        self.assertEqual(stale, [],
                         "run python3 tool/map_usb_routing.py --write")

    def test_the_report_does_not_claim_timing(self):
        text = "\n".join(ur.report_lines(self.analysis))
        self.assertIn("Call-graph reachability is not timing", text)


if __name__ == "__main__":
    unittest.main()
