import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backup_firmware as bf
import probe_flash_read as pfr
from test_backup_firmware import FakeBootloader, flash_bytes


class TestOneBlockProbe(unittest.TestCase):
    def test_reads_exact_fresh_header_with_one_execute(self):
        flash = bytearray(flash_bytes())
        flash[:len(pfr.EXPECTED_MAGIC)] = pfr.EXPECTED_MAGIC
        fake = FakeBootloader(bytes(flash), dispatch_delay=2, write_step=8)
        guarded = pfr.ExactOneBlockTransport(fake)
        data = pfr.run_probe(guarded)
        self.assertEqual(data, bytes(flash[:pfr.LENGTH]))
        self.assertEqual(guarded.counts["exec_read"], 1)
        self.assertEqual(guarded.counts["set_addr"], 1)

    def test_changed_address_is_rejected(self):
        guarded = pfr.ExactOneBlockTransport(FakeBootloader(flash_bytes()))
        other = bf.build_report(bf.SET_ADDR,
                                (pfr.ADDRESS + pfr.LENGTH).to_bytes(4, "little"))
        with self.assertRaises(pfr.ExactOneBlockError):
            guarded.write(other)

    def test_second_execute_is_rejected(self):
        fake = FakeBootloader(flash_bytes())
        fake.addr = pfr.ADDRESS
        fake.length = pfr.LENGTH
        guarded = pfr.ExactOneBlockTransport(fake)
        guarded.write(pfr.REPORTS["exec_read"])
        with self.assertRaises(pfr.ExactOneBlockError):
            guarded.write(pfr.REPORTS["exec_read"])

    def test_missing_magic_aborts(self):
        fake = FakeBootloader(flash_bytes(), dispatch_delay=1)
        with self.assertRaises(bf.ProtocolError):
            pfr.run_probe(pfr.ExactOneBlockTransport(fake))

    def test_live_probe_uses_both_nodes(self):
        flash = bytearray(flash_bytes())
        flash[:len(pfr.EXPECTED_MAGIC)] = pfr.EXPECTED_MAGIC
        fake = FakeBootloader(bytes(flash))
        opened = []

        def factory(command_node, response_node):
            opened.append((command_node, response_node))
            return fake

        selector = lambda: ("/dev/ff01", "/dev/ff00", [], [], [])
        self.assertEqual(pfr.live_probe(factory, selector), 0)
        self.assertEqual(opened, [("/dev/ff01", "/dev/ff00")])
        self.assertTrue(fake.closed)

    def test_cli_refuses_without_ack_before_live(self):
        with mock.patch.object(pfr, "live_probe",
                               side_effect=AssertionError("live path entered")):
            self.assertEqual(pfr.main(["--run"]), 2)


if __name__ == "__main__":
    unittest.main()
