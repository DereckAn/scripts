import os
import tempfile
import unittest
from unittest import mock

from tool import enter_bootloader as eb


def descriptor(page=0xFF00, count=64, report_id=None):
    out = bytearray([0x06, page & 0xFF, page >> 8, 0x09, 0x01, 0xA1, 0x01])
    if report_id is not None:
        out += bytes([0x85, report_id])
    out += bytes([0x75, 8, 0x95, count, 0x81, 2, 0x75, 8, 0x95, count, 0x91, 2, 0xC0])
    return bytes(out)


class TestFrame(unittest.TestCase):
    def test_exact_payload(self):
        self.assertEqual(eb.PAYLOAD[:7], bytes.fromhex("7b aa 41 53 55 53 aa"))
        self.assertEqual(eb.PAYLOAD[7:], bytes(57))
        self.assertEqual(eb.HIDRAW_WRITE, b"\0" + eb.PAYLOAD)
        self.assertEqual(len(eb.HIDRAW_WRITE), 65)

    def test_guard_rejects_every_difference(self):
        eb.guard_exact_write(eb.HIDRAW_WRITE)
        for index in (0, 1, 7, 64):
            changed = bytearray(eb.HIDRAW_WRITE)
            changed[index] ^= 1
            with self.assertRaises(eb.UnsafeWrite):
                eb.guard_exact_write(changed)

    def test_emit_is_one_write(self):
        writes = []
        eb.emit_once("/dev/fake", opener=lambda *_: 9,
                     writer=lambda fd, data: writes.append((fd, data)) or len(data),
                     closer=lambda fd: None)
        self.assertEqual(writes, [(9, eb.HIDRAW_WRITE)])


class TestSelection(unittest.TestCase):
    def add(self, root, name, pid, desc):
        base = os.path.join(root, name, "device")
        os.makedirs(base)
        with open(os.path.join(base, "uevent"), "w", encoding="utf-8") as fh:
            fh.write(f"HID_ID=0003:00000B05:0000{pid:04X}\n")
        with open(os.path.join(base, "report_descriptor"), "wb") as fh:
            fh.write(desc)

    def test_selects_only_ff00_64_byte_unnumbered_node(self):
        with tempfile.TemporaryDirectory() as root:
            self.add(root, "hidraw1", eb.PID_APP, descriptor(page=1, count=8))
            self.add(root, "hidraw2", eb.PID_APP, descriptor())
            node = eb.select_application_node(root, "/dev")
            self.assertEqual(node, "/dev/hidraw2")

    def test_refuses_when_already_in_bootloader(self):
        with tempfile.TemporaryDirectory() as root:
            self.add(root, "hidraw2", eb.PID_APP, descriptor())
            self.add(root, "hidraw3", eb.PID_BOOT, descriptor())
            with self.assertRaises(eb.SelectionError):
                eb.select_application_node(root, "/dev")


class TestCli(unittest.TestCase):
    def test_default_dry_run_never_enumerates_or_opens(self):
        with mock.patch.object(eb, "select_application_node",
                               side_effect=AssertionError("device selection attempted")):
            self.assertEqual(eb.main([]), 0)

    def test_run_without_ack_is_refused_before_selection(self):
        with mock.patch.object(eb, "select_application_node",
                               side_effect=AssertionError("device selection attempted")):
            self.assertEqual(eb.main(["--run"]), 2)


if __name__ == "__main__":
    unittest.main()
