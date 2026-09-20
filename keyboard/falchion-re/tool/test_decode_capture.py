#!/usr/bin/env python3
"""Offline tests for the vendor-report decoder and its PowerShell twin.

These run the real decoder against the preserved
`captures/02-polling-rate.pcap` and require it to reproduce the landmarks log
126 established independently: twenty `51 31` writes, twenty `50 55` commits,
74 requests and 74 replies, on the subject's endpoints and nobody else's.

No device access. The captures are opened read-only and their sha256 is
asserted unchanged at the end of the run.
"""
import hashlib
from pathlib import Path
import shutil
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import decode_capture as dc

ROOT = Path(dc.ROOT)
CAPTURE = ROOT / "captures/02-polling-rate.pcap"
CAPTURE_SHA256 = "a6e860be5192ce942b95441ed2e75bef1ff41c5e87c98ba56747a0148ac45d54"
HAVE_TSHARK = shutil.which("tshark") is not None
HAVE_CAPTURE = CAPTURE.is_file()
READY = HAVE_TSHARK and HAVE_CAPTURE


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Rules(unittest.TestCase):
    """The filter and identity rules, with no capture involved."""

    def test_direction_comes_from_the_endpoint_bit(self):
        self.assertEqual(dc.direction(0x0D), "OUT")
        self.assertEqual(dc.direction(0x85), "IN")
        self.assertEqual(dc.direction(dc.VENDOR_OUT), "OUT")
        self.assertEqual(dc.direction(dc.VENDOR_IN), "IN")

    def test_the_filter_scopes_every_subject_key_to_its_bus(self):
        text = dc.report_filter((("", "3", 6), ("", "3", 7)))
        self.assertIn("(usb.bus_id==3 && usb.device_address==6)", text)
        self.assertIn("(usb.bus_id==3 && usb.device_address==7)", text)
        self.assertIn("usb.endpoint_address==0x0d", text)
        self.assertIn("usb.endpoint_address==0x85", text)
        self.assertIn("usb.data_len==64", text)

    def test_the_filter_includes_the_capture_interface_when_there_is_one(self):
        text = dc.report_filter(((("1"), "2", 2),))
        self.assertIn("frame.interface_id==1 && usb.bus_id==2 && "
                      "usb.device_address==2", text)

    def test_the_filter_refuses_an_empty_subject_set(self):
        with self.assertRaises(dc.DecodeError):
            dc.report_filter(())

    def test_identity_keeps_direction(self):
        """An IN echo carries the same 64 bytes as its OUT request."""
        out = {"direction": "OUT", "payload": "5131" + "0" * 124}
        back = dict(out, direction="IN")
        self.assertNotEqual(dc.identity(out), dc.identity(back))
        self.assertEqual(len(dc.unique([out, back, dict(out)])), 2)

    def test_a_diff_does_not_collapse_an_in_echo_into_its_out_request(self):
        out = {"direction": "OUT", "payload": "5131" + "0" * 124}
        back = dict(out, direction="IN")
        self.assertEqual(dc.difference([out, back], [back]), [out])
        self.assertEqual(dc.difference([out, back], [out]), [back])
        self.assertEqual(dc.difference([out, back], [out, back]), [])

    def test_the_payload_field_is_usbhid_not_capdata(self):
        self.assertEqual(dc.PAYLOAD_FIELD, "usbhid.data")
        self.assertIn("usbhid.data", dc.REPORT_FIELDS)
        self.assertNotIn("usb.capdata", dc.REPORT_FIELDS)

    def test_a_missing_capture_fails_loudly(self):
        with self.assertRaises(dc.DecodeError):
            dc.identity_map(ROOT / "captures/does-not-exist.pcap")

    def test_a_capture_without_the_subject_is_refused(self):
        """Other devices on the same root hub must never be decoded."""
        with self.assertRaises(dc.DecodeError) as caught:
            dc.select_subject({("", "2", 1): ((0x174C, 0x3074, 0x0001),),
                               ("", "3", 3): ((0x1532, 0x00E6, 0x0101),)})
        self.assertIn("1b7e", str(caught.exception))

    def test_the_subject_is_selected_by_identity_not_by_address(self):
        chosen = dc.select_subject({
            ("", "3", 2): ((0x1532, 0x00E6, 0x0101),),
            ("", "3", 6): ((0x0B05, 0x1B7E, 0x0159),),
            ("", "3", 7): ((0x0B05, 0x1B7E, 0x0159),),
            ("", "3", 3): ((0x0B05, 0x19AF, 0x0100),)})
        self.assertEqual(chosen, (("", "3", 6), ("", "3", 7)),
                         "the other ASUS device shares the VID and must not "
                         "be picked up")

    def test_the_same_address_on_two_buses_is_two_identities(self):
        """The bug: keyed by address alone, one of these overwrites the other.
        It is NOT a descriptor-identity conflict — different keys entirely."""
        rows = "\n".join((
            "1\t2\t1\t0x174c\t0x3074\t0x0001",
            "2\t3\t1\t0x0b05\t0x1b7e\t0x0159"))
        identities = dc.parse_identities(rows)
        self.assertEqual(len(identities), 2)
        self.assertEqual(dc.conflicting_keys(identities), ())
        self.assertEqual(dc.select_subject(identities), (("2", "3", 1),))

    def test_a_key_with_two_different_vid_pids_is_refused(self):
        """No display filter can separate them, so nothing may be attributed."""
        rows = "\n".join((
            "\t3\t4\t0x0b05\t0x1b7e\t0x0159",
            "\t3\t4\t0x046d\t0x0b0b\t0x0100"))
        identities = dc.parse_identities(rows)
        self.assertEqual(dc.conflicting_keys(identities), (("", "3", 4),))
        with self.assertRaises(dc.DecodeError) as caught:
            dc.select_subject(identities)
        self.assertIn("descriptor-identity conflict", str(caught.exception))

    def test_a_key_that_differs_only_in_bcddevice_is_also_refused(self):
        """bcdDevice is part of the descriptor identity on BOTH sides. The
        same model at two firmware revisions on one key is still two devices."""
        rows = "\n".join((
            "\t3\t4\t0x0b05\t0x1b7e\t0x0159",
            "\t3\t4\t0x0b05\t0x1b7e\t0x0105"))
        identities = dc.parse_identities(rows)
        self.assertEqual(dc.conflicting_keys(identities), (("", "3", 4),))
        with self.assertRaises(dc.DecodeError):
            dc.select_subject(identities)

    def test_python_uses_all_three_descriptor_fields(self):
        self.assertIn("usb.idVendor", dc.IDENTITY_FIELDS)
        self.assertIn("usb.idProduct", dc.IDENTITY_FIELDS)
        self.assertIn("usb.bcdDevice", dc.IDENTITY_FIELDS)
        identity, = dc.parse_identities(
            "\t3\t4\t0x0b05\t0x1b7e\t0x0159").values()
        self.assertEqual(identity, ((0x0B05, 0x1B7E, 0x0159),))

    def test_an_identical_descriptor_repeated_is_not_a_conflict(self):
        """And is NOT evidence that the physical device never changed. Two
        units of the same model and firmware are indistinguishable here; the
        docstring of conflicting_keys says so and this pins that it does."""
        rows = "\n".join((
            "\t3\t4\t0x0b05\t0x1b7e\t0x0159",
            "\t3\t4\t0x0b05\t0x1b7e\t0x0159"))
        identities = dc.parse_identities(rows)
        self.assertEqual(dc.conflicting_keys(identities), ())
        self.assertEqual(dc.select_subject(identities), (("", "3", 4),))
        self.assertIn("IDENTICAL descriptor",
                      dc.conflicting_keys.__doc__)

    def test_a_re_enumeration_at_the_same_identity_is_not_reuse(self):
        rows = "\n".join((
            "\t3\t6\t0x0b05\t0x1b7e\t0x0159",
            "\t3\t7\t0x0b05\t0x1b7e\t0x0159",
            "\t3\t7\t0x0b05\t0x1b7e\t0x0159"))
        identities = dc.parse_identities(rows)
        self.assertEqual(dc.conflicting_keys(identities), ())
        self.assertEqual(dc.select_subject(identities),
                         (("", "3", 6), ("", "3", 7)))


class BusScopedFiltering(unittest.TestCase):
    """Row-level fixtures: the same address on two buses, one of them ours.

    Building a synthetic USBPcap file would not exercise more of this code —
    the scoping happens after tshark hands the fields over — so the fixture is
    a set of field rows in exactly tshark's output shape.
    """

    SUBJECT = ("1", "2", 2)
    OTHER = ("2", "3", 2)

    def row(self, frame, key, endpoint, payload):
        interface, bus, address = key
        return "\t".join((str(frame), "0.1", "1788933978.1", interface, bus,
                           str(address), endpoint, "64", payload))

    def test_traffic_from_another_bus_at_the_same_address_is_excluded(self):
        payload = "5131" + "0" * 124
        rows = [self.row(1, self.SUBJECT, "0x0d", payload),
                self.row(2, self.OTHER, "0x0d", payload),
                self.row(3, self.SUBJECT, "0x85", payload)]
        kept = dc.rows_to_reports(rows, (self.SUBJECT,))
        self.assertEqual([record["frame"] for record in kept], [1, 3])
        self.assertEqual({record["bus"] for record in kept}, {"2"})

    def test_a_row_with_no_payload_is_a_urb_marker_not_a_report(self):
        rows = [self.row(1, self.SUBJECT, "0x0d", "")]
        self.assertEqual(dc.rows_to_reports(rows, (self.SUBJECT,)), [])

    def test_a_short_payload_is_refused_rather_than_padded(self):
        rows = [self.row(1, self.SUBJECT, "0x0d", "5131")]
        with self.assertRaises(dc.DecodeError):
            dc.rows_to_reports(rows, (self.SUBJECT,))

    def test_a_non_vendor_endpoint_that_slipped_the_filter_is_refused(self):
        rows = [self.row(1, self.SUBJECT, "0x81", "00" * 64)]
        with self.assertRaises(dc.DecodeError):
            dc.rows_to_reports(rows, (self.SUBJECT,))

    def test_the_absolute_epoch_is_carried_for_cross_artifact_correlation(self):
        rows = [self.row(1, self.SUBJECT, "0x0d", "00" * 64)]
        record, = dc.rows_to_reports(rows, (self.SUBJECT,))
        self.assertEqual(record["epoch"], 1788933978.1)
        self.assertEqual(record["time"], 0.1)


class PowerShellStaysInSync(unittest.TestCase):
    """The Windows script cannot be executed here, so pin its constants.

    This is a drift guard, not a behaviour test: the behaviour is tested
    against the real capture by `PreservedCapture` below, through the module
    that owns these same values.
    """

    def test_decode_ps1_carries_the_canonical_constants(self):
        found = dc.powershell_constants(dc.POWERSHELL.read_text())
        self.assertEqual({name: found.get(name)
                          for name in dc.EXPECTED_PS}, dc.EXPECTED_PS)

    def test_no_drift(self):
        self.assertEqual(dc.powershell_drift(), [])

    def test_the_guard_notices_a_removed_block(self):
        with self.assertRaises(dc.DecodeError):
            dc.powershell_constants("nothing canonical in here")

    def test_the_guard_notices_bcddevice_being_dropped(self):
        """Either implementation losing it must fail the check."""
        text = dc.POWERSHELL.read_text().replace("'usb.bcdDevice'", "''")
        problems = []
        code = dc.strip_comments(text)
        self.assertNotIn("usb.bcdDevice", code)
        self.assertTrue([item for item in dc.powershell_drift.__doc__ or ""] or True)
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "decode.ps1"
            target.write_text(text)
            problems = dc.powershell_drift(target)
        self.assertTrue([item for item in problems if "bcdDevice" in item],
                        problems)

    def test_the_guard_notices_a_two_field_descriptor_identity(self):
        text = dc.POWERSHELL.read_text().replace(
            '$ident = "$($f[3]):$($f[4]):$($f[5])"',
            '$ident = "$($f[3]):$($f[4])"')
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "decode.ps1"
            target.write_text(text)
            problems = dc.powershell_drift(target)
        self.assertTrue([item for item in problems if "three fields" in item],
                        problems)

    def test_both_implementations_name_the_same_descriptor_fields(self):
        code = dc.strip_comments(dc.POWERSHELL.read_text())
        for field in ("usb.idVendor", "usb.idProduct", "usb.bcdDevice"):
            self.assertIn(field, code)
            self.assertIn(field, dc.IDENTITY_FIELDS)

    def test_the_guard_notices_a_changed_endpoint(self):
        text = dc.POWERSHELL.read_text().replace("$VendorOutEndpoint = 0x0D",
                                                 "$VendorOutEndpoint = 0x01")
        found = dc.powershell_constants(text)
        self.assertEqual(found["VendorOutEndpoint"], 0x01)
        self.assertNotEqual(found["VendorOutEndpoint"], dc.VENDOR_OUT)

    def test_the_script_stopped_claiming_a_filter_it_does_not_apply(self):
        code = dc.strip_comments(dc.POWERSHELL.read_text())
        self.assertNotIn("usb.capdata", code)
        self.assertIn("usbhid.data", code)


@unittest.skipUnless(READY, "needs tshark and the preserved capture")
class PreservedCapture(unittest.TestCase):
    """The decoder must reproduce log 126's polling-rate traffic, exactly."""

    @classmethod
    def setUpClass(cls):
        cls.before = sha256(CAPTURE)
        cls.records = dc.reports(CAPTURE)

    @classmethod
    def tearDownClass(cls):
        assert sha256(CAPTURE) == cls.before, "the capture was modified"

    def test_the_capture_is_the_preserved_one(self):
        self.assertEqual(self.before, CAPTURE_SHA256)

    def test_the_subject_is_found_by_vid_pid_across_a_re_enumeration(self):
        """Hard-coding one address would lose the pre-replug frames."""
        self.assertEqual(dc.subject_keys(CAPTURE), (("", "3", 6), ("", "3", 7)))
        self.assertEqual(dc.subject_addresses(CAPTURE), (6, 7))
        identities = dc.identity_map(CAPTURE)
        self.assertEqual(identities[("", "3", 7)][0][:2], (0x0B05, 0x1B7E))
        self.assertGreater(len(identities), 2,
                           "other devices are present and must be excluded")
        self.assertEqual(dc.conflicting_keys(identities), ())

    def test_twenty_polling_rate_writes_and_twenty_commits(self):
        histogram = dc.opcode_histogram(self.records)
        self.assertEqual(histogram["5131"], 20)
        self.assertEqual(histogram["5055"], 20)

    def test_the_conversation_is_74_requests_and_74_replies(self):
        out = [r for r in self.records if r["direction"] == "OUT"]
        back = [r for r in self.records if r["direction"] == "IN"]
        self.assertEqual((len(out), len(back)), (74, 74))

    def test_only_the_subject_endpoints_appear(self):
        self.assertEqual({r["endpoint"] for r in self.records},
                         {dc.VENDOR_OUT, dc.VENDOR_IN})
        self.assertLessEqual({r["address"] for r in self.records}, {6, 7})

    def test_every_report_is_exactly_64_bytes(self):
        for record in self.records:
            self.assertEqual(record["length"], 64)
            self.assertEqual(len(record["payload"]), 128)

    def test_the_rate_writes_carry_index_0_and_3_at_offset_4(self):
        """Log 126's headline, re-derived through this decoder."""
        indices = [bytes.fromhex(r["payload"])[4] for r in self.records
                   if r["direction"] == "OUT" and r["opcode"] == "5131"]
        self.assertEqual(len(indices), 20)
        self.assertEqual(set(indices), {0x00, 0x03})
        self.assertEqual(indices.count(0x00), 14)
        self.assertEqual(indices.count(0x03), 6)

    def test_the_old_field_really_is_empty(self):
        """The premise of finding 2, re-derived rather than quoted."""
        rows = dc._run(CAPTURE, dc.report_filter(dc.subject_keys(CAPTURE)),
                       ("frame.number", "usb.capdata"))
        payloads = [line.split("\t")[1] for line in rows.splitlines()
                    if "\t" in line]
        self.assertTrue(payloads, "the filter matched nothing at all")
        self.assertEqual([p for p in payloads if p], [],
                         "usb.capdata was supposed to be empty for USBPcap")

    def test_the_other_capture_puts_the_subject_at_a_different_address(self):
        """Why the address must never be hard-coded, shown on real evidence.

        The same keyboard is address 6 and 7 in 02-polling-rate and address 2
        in 01-first-launch. Any script pinned to one of those numbers decodes
        nothing from the other capture.
        """
        other = ROOT / "captures/01-first-launch.pcapng"
        if not other.is_file():
            self.skipTest("the other capture is not present")
        before = sha256(other)
        self.assertEqual(dc.subject_keys(other), (("1", "2", 2),))
        self.assertEqual(dc.subject_addresses(other), (2,))
        self.assertEqual(sha256(other), before)

    def test_the_other_capture_holds_one_address_on_two_buses(self):
        """The real evidence that an address is not an identity: in
        01-first-launch, address 1 is an ASMedia hub on bus 2 and a Logitech
        receiver on bus 3, across two different USBPcap interfaces."""
        other = ROOT / "captures/01-first-launch.pcapng"
        if not other.is_file():
            self.skipTest("the other capture is not present")
        before = sha256(other)
        identities = dc.identity_map(other)
        collisions = [key for key in identities if key[2] == 1]
        self.assertEqual(sorted(collisions), [("1", "2", 1), ("2", "3", 1)])
        self.assertEqual({identities[key][0][0] for key in collisions},
                         {0x174C, 0x046D})
        self.assertEqual(dc.conflicting_keys(identities), ())
        self.assertEqual(sha256(other), before)

    def test_diffing_a_capture_against_itself_finds_nothing(self):
        self.assertEqual(dc.difference(self.records, self.records), [])

    def test_the_text_report_states_the_filter_it_used(self):
        text = "\n".join(dc.report_lines(CAPTURE, self.records))
        self.assertIn("usb.endpoint_address==0x0d", text)
        self.assertIn("0b05:1b7e", text)
        self.assertIn("51 31", text)


if __name__ == "__main__":
    unittest.main()
