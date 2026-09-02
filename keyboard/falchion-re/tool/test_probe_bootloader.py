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
