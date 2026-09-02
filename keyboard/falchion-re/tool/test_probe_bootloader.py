import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backup_firmware as bf
import probe_bootloader as pb


class FakeTransport:
    def __init__(self, replies):
        self.replies = list(replies)
        self.writes = []
        self.closed = False

    def write(self, report):
        self.writes.append(bytes(report))

    def read(self, timeout):
        return self.replies.pop(0)

    def close(self):
        self.closed = True


def status(flags=0, error=0):
    return bytes([bf.R_STATUS, flags, error]) + bytes(61)


def buffer_reply(data=bytes(pb.PROBE_LEN)):
    return bytes([bf.R_READDATA]) + data + bytes(63 - len(data))


class TestSequence(unittest.TestCase):
    def test_exact_four_report_probe(self):
        fake = FakeTransport([status(), buffer_reply(), status()])
        guarded = pb.ExactSequenceTransport(fake)
        before, data, after = pb.run_probe(guarded)
        self.assertEqual(fake.writes, [report for _label, report in pb.SEQUENCE])
        self.assertEqual(before, status())
        self.assertEqual(data, buffer_reply())
        self.assertEqual(after, status())

    def test_any_changed_report_is_rejected(self):
        for index, (_label, expected) in enumerate(pb.SEQUENCE):
            fake = FakeTransport([])
            guarded = pb.ExactSequenceTransport(fake)
            guarded.index = index
            changed = bytearray(expected)
            changed[0] ^= 1
            with self.assertRaises(pb.ExactSequenceError):
                guarded.write(changed)
            self.assertEqual(fake.writes, [])

    def test_extra_report_is_rejected(self):
        guarded = pb.ExactSequenceTransport(FakeTransport([]))
        guarded.index = len(pb.SEQUENCE)
        with self.assertRaises(pb.ExactSequenceError):
            guarded.write(pb.SEQUENCE[-1][1])

    def test_nonzero_flags_abort(self):
        fake = FakeTransport([status(flags=2)])
        with self.assertRaises(bf.ProtocolError):
            pb.run_probe(pb.ExactSequenceTransport(fake))
        self.assertEqual(len(fake.writes), 1)

    def test_nonzero_error_abort(self):
        fake = FakeTransport([status(error=3)])
        with self.assertRaises(bf.ProtocolError):
            pb.run_probe(pb.ExactSequenceTransport(fake))
        self.assertEqual(len(fake.writes), 1)

    def test_nonzero_boot_buffer_abort_before_final_status(self):
        fake = FakeTransport([status(), buffer_reply(b"X" + bytes(47))])
        with self.assertRaises(bf.ProtocolError):
            pb.run_probe(pb.ExactSequenceTransport(fake))
        self.assertEqual(len(fake.writes), 3)


class TestSplitTransport(unittest.TestCase):
    def test_write_and_read_use_distinct_file_descriptors(self):
        command_read, command_write = __import__("os").pipe()
        response_read, response_write = __import__("os").pipe()
        self.addCleanup(__import__("os").close, command_read)
        self.addCleanup(__import__("os").close, response_write)
        transport = object.__new__(pb.SplitHidrawTransport)
        transport.write_fd = command_write
        transport.read_fd = response_read
        report = bf.build_report(bf.Q_STATUS)
        transport.write(report)
        self.assertEqual(__import__("os").read(command_read, 65), b"\x00" + report)
        reply = status()
        __import__("os").write(response_write, reply)
        self.assertEqual(transport.read(1.0), reply)
        transport.close()

    def test_same_node_is_refused_before_open(self):
        with self.assertRaises(bf.SelectionError):
            pb.SplitHidrawTransport("/dev/does-not-matter", "/dev/does-not-matter")


class TestChannelSelection(unittest.TestCase):
    def test_selects_ff01_for_commands_and_ff00_for_responses(self):
        calls = []

        def select_node(usage_page):
            calls.append(usage_page)
            if usage_page == bf.COMMAND_USAGE_PAGE:
                return "/dev/hidraw6", ["other"], []
            return "/dev/hidraw7", ["other"], []

        with mock.patch.object(bf, "select_bootloader_node", side_effect=select_node):
            selected = pb.select_bootloader_channels()
        self.assertEqual(calls, [bf.COMMAND_USAGE_PAGE, bf.RESPONSE_USAGE_PAGE])
        self.assertEqual(selected[:2], ("/dev/hidraw6", "/dev/hidraw7"))

    def test_live_probe_opens_both_nodes_before_sequence(self):
        fake = FakeTransport([status(), buffer_reply(), status()])
        opened = []

        def factory(command_node, response_node):
            opened.append((command_node, response_node))
            return fake

        select_channels = lambda: ("/dev/hidraw6", "/dev/hidraw7", [], [], [])
        self.assertEqual(pb.live_probe(open_transport=factory,
                                       select_channels=select_channels), 0)
        self.assertEqual(opened, [("/dev/hidraw6", "/dev/hidraw7")])
        self.assertEqual(fake.writes, [report for _label, report in pb.SEQUENCE])
        self.assertTrue(fake.closed)


class TestCli(unittest.TestCase):
    def test_dry_run_never_selects_or_opens(self):
        with mock.patch.object(pb, "live_probe",
                               side_effect=AssertionError("live path entered")):
            self.assertEqual(pb.main([]), 0)

    def test_run_without_ack_refuses_before_live_path(self):
        with mock.patch.object(pb, "live_probe",
                               side_effect=AssertionError("live path entered")):
            self.assertEqual(pb.main(["--run"]), 2)


if __name__ == "__main__":
    unittest.main()
