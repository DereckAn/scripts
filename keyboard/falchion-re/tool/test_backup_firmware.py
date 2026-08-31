#!/usr/bin/env python3
"""Dependency-free mocked tests for backup_firmware.

Every test drives a `FakeBootloader` object or a temporary sysfs tree. Nothing
here opens /dev, and `HidrawTransport` is asserted never to be constructed.

Run: python3 tool/test_backup_firmware.py
"""
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backup_firmware as bf


# ---------------------------------------------------------------------------
# offline model of the 1b7f responder (logs 81-82)
# ---------------------------------------------------------------------------
class FakeBootloader:
    """Implements FUN_0000380c (OUT parser) and FUN_00003740 (IN responder).

    Fault-injection knobs mirror the failure modes the tool must abort on.
    """

    def __init__(self, flash, *, busy_polls=0, busy_forever=False, error=0,
                 code_override=None, resp_len=None, unlocked=False):
        self.flash = flash                  # bytes covering [REGION_LO, REGION_HI)
        self.busy_polls = busy_polls
        self.busy_forever = busy_forever
        self.error = error
        self.code_override = code_override
        self.resp_len = bf.REPORT_LEN if resp_len is None else resp_len
        self.flags = bf.UNLOCK_BIT if unlocked else 0
        self.addr = self.length = None
        self.pending = None
        self.log = []                       # (sub, payload) in send order
        self.reads = 0
        self.queued = None
        self.closed = False

    # -- transport surface ---------------------------------------------------
    def write(self, report):
        # The device sees the 64-byte report; the hidraw report-number byte is
        # added by HidrawTransport (see TestHidrawFraming).
        assert len(report) == bf.REPORT_LEN, "reports are exactly 64 bytes"
        sub, payload = report[0], report[1:]
        self.log.append((sub, payload))
        assert sub not in bf.FORBIDDEN, f"fake device saw forbidden 0x{sub:02x}"
        if sub == bf.SET_ADDR:
            self.addr = struct.unpack("<I", payload[:4])[0]
        elif sub == bf.SET_LEN:
            self.length = struct.unpack("<H", payload[:2])[0]
        elif sub == bf.EXEC:
            assert payload[0] == bf.OP_READ
            self.pending = bf.OP_READ
            self.flags |= bf.BUSY_READ          # log 81: bit 1 held across READ
            self._remaining_busy = -1 if self.busy_forever else self.busy_polls
        elif sub == bf.Q_STATUS:
            self.queued = self._status()
        elif sub == bf.Q_READDATA:
            self.queued = self._data()
        else:
            raise AssertionError(f"unexpected sub-command 0x{sub:02x}")

    def read(self, timeout):
        if self.queued is None:
            raise bf.ProtocolError("fake: read with no outstanding query")
        resp, self.queued = self.queued, None
        self.reads += 1
        return resp

    def close(self):
        self.closed = True

    # -- responses -----------------------------------------------------------
    def _frame(self, code, body=b""):
        if self.code_override is not None:
            code = self.code_override
        resp = bytes([code]) + bytes(body)
        resp += b"\x00" * (bf.REPORT_LEN - len(resp))
        return resp[:self.resp_len]

    def _status(self):
        if self.pending == bf.OP_READ:
            if self._remaining_busy > 0:
                self._remaining_busy -= 1
            elif self._remaining_busy == 0:
                self.flags &= ~bf.BUSY_READ     # READ finished; bit 1 cleared
                self.pending = None
        return self._frame(bf.R_STATUS, bytes([self.flags, self.error]))

    def _data(self):
        off = self.addr - bf.REGION_LO
        return self._frame(bf.R_READDATA, self.flash[off:off + self.length])


def flash_bytes(n=0x90):
    return bytes((i * 7 + 3) & 0xFF for i in range(n))


SHORT_PLAN = [(bf.REGION_LO, 0x30), (bf.REGION_LO + 0x30, 0x30), (bf.REGION_LO + 0x60, 0x30)]


class NoDeviceTransport:
    """Fails loudly if any test reaches for the real hidraw transport."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("a test tried to open a real device")


# ---------------------------------------------------------------------------
class TestGuard(unittest.TestCase):
    def test_forbidden_subcommands_cannot_be_built(self):
        for sub, payload in [(0x10, b"ASUSHIDFWU"), (0x22, b"\x04\x00\x00d"),
                             (0x11, b""), (0x01, b""), (0x51, b"")]:
            with self.assertRaises(bf.UnsafeReport):
                bf.build_report(sub, payload)

    def test_execute_is_locked_to_read(self):
        bf.build_report(bf.EXEC, bytes([bf.OP_READ]))
        for opcode in (0x01, 0x51, 0x00):
            with self.assertRaises(bf.UnsafeReport):
                bf.build_report(bf.EXEC, bytes([opcode]))

    def test_address_and_length_bounds(self):
        with self.assertRaises(bf.UnsafeReport):
            bf.build_report(bf.SET_ADDR, struct.pack("<I", 0))
        with self.assertRaises(bf.UnsafeReport):
            bf.build_report(bf.SET_ADDR, struct.pack("<I", bf.REGION_HI))
        with self.assertRaises(bf.UnsafeReport):
            bf.build_report(bf.SET_LEN, struct.pack("<H", bf.CHUNK_MAX + 1))
        with self.assertRaises(bf.UnsafeReport):
            bf.build_report(bf.SET_LEN, struct.pack("<H", 0))

    def test_plan_covers_exactly_the_app_region(self):
        plan = list(bf.dump_plan())
        self.assertEqual(sum(n for _a, n in plan), bf.REGION_SIZE)
        self.assertEqual(plan[0][0], 0x10000)
        self.assertEqual(plan[-1][0] + plan[-1][1], 0x7C000)


class TestChunkProtocol(unittest.TestCase):
    def test_success_and_exact_order(self):
        flash = flash_bytes()
        dev = FakeBootloader(flash)
        got = bf.read_chunk(dev, bf.REGION_LO, 0x30)
        self.assertEqual(got, flash[:0x30])
        self.assertEqual([sub for sub, _p in dev.log],
                         [bf.SET_ADDR, bf.SET_LEN, bf.EXEC, bf.Q_STATUS, bf.Q_READDATA])
        # one read per query, never a batched pair
        self.assertEqual(dev.reads, 2)

    def test_each_query_is_read_immediately(self):
        """Regression: the old code queued 0x8f and 0xaa then read once, so the
        status report was consumed as read data."""
        dev = FakeBootloader(flash_bytes())
        bf.read_chunk(dev, bf.REGION_LO, 0x30)
        queries = [i for i, (sub, _p) in enumerate(dev.log)
                   if sub in (bf.Q_STATUS, bf.Q_READDATA)]
        self.assertEqual(queries, [3, 4])          # adjacent, but each read between

    def test_busy_then_ready(self):
        flash = flash_bytes()
        dev = FakeBootloader(flash, busy_polls=3)
        self.assertEqual(bf.read_chunk(dev, bf.REGION_LO, 0x30), flash[:0x30])
        self.assertEqual(sum(1 for sub, _p in dev.log if sub == bf.Q_STATUS), 4)

    def test_permanent_busy_aborts_within_bounded_attempts(self):
        dev = FakeBootloader(flash_bytes(), busy_forever=True)
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.read_chunk(dev, bf.REGION_LO, 0x30)
        self.assertIn("stayed busy", str(ctx.exception))
        self.assertEqual(sum(1 for sub, _p in dev.log if sub == bf.Q_STATUS),
                         bf.BUSY_ATTEMPTS)

    def test_status_error_aborts(self):
        for code, text in bf.STATUS_ERRORS.items():
            dev = FakeBootloader(flash_bytes(), error=code)
            with self.assertRaises(bf.ProtocolError) as ctx:
                bf.read_chunk(dev, bf.REGION_LO, 0x30)
            self.assertIn(text, str(ctx.exception))

    def test_wrong_response_code_aborts(self):
        dev = FakeBootloader(flash_bytes(), code_override=0x7F)
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.read_chunk(dev, bf.REGION_LO, 0x30)
        self.assertIn("wrong response code 0x7f", str(ctx.exception))

    def test_data_response_code_must_be_0x2a(self):
        dev = FakeBootloader(flash_bytes())
        bf.send(dev, bf.SET_ADDR, struct.pack("<I", bf.REGION_LO))
        bf.send(dev, bf.SET_LEN, struct.pack("<H", 0x30))
        bf.send(dev, bf.EXEC, bytes([bf.OP_READ]))
        bf.wait_read_done(dev)
        dev.code_override = bf.R_STATUS            # answer data query as status
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.query(dev, bf.Q_READDATA, bf.R_READDATA)
        self.assertIn("expected 0x2a", str(ctx.exception))

    def test_short_report_aborts(self):
        dev = FakeBootloader(flash_bytes(), resp_len=32)
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.read_chunk(dev, bf.REGION_LO, 0x30)
        self.assertIn("short response: 32 of 64", str(ctx.exception))

    def test_payload_skips_only_the_response_code(self):
        flash = flash_bytes()
        dev = FakeBootloader(flash)
        got = bf.read_chunk(dev, bf.REGION_LO, 0x30)
        self.assertEqual(got[0], flash[0])          # no byte lost to a phantom prefix


class TestRunBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = os.path.join(self.tmp.name, "dump.bin")
        self.flash = flash_bytes()
        self.expected = self.flash[:0x90]

    def _select(self):
        return ("/dev/fake0", [], [])

    # The short mock plan cannot satisfy the real 0x6c000 validator, so these
    # cases inject a permissive one. Production validation is covered separately
    # by TestDumpValidation, which exercises the real default.
    @staticmethod
    def _skip_validation(_image):
        return []

    def test_three_identical_passes_write_output(self):
        made = []

        def factory(_node):
            dev = FakeBootloader(self.flash)
            made.append(dev)
            return dev

        rc = bf.run_backup(self.out, open_transport=factory,
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 0)
        self.assertEqual(Path(self.out).read_bytes(), self.expected)
        self.assertEqual(len(made), 3)
        self.assertTrue(all(d.closed for d in made))

    def test_mismatched_passes_refuse_to_write(self):
        variants = [self.flash, self.flash, bytes([self.flash[0] ^ 0xFF]) + self.flash[1:]]

        def factory(_node):
            return FakeBootloader(variants.pop(0))

        rc = bf.run_backup(self.out, open_transport=factory,
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))

    def test_failure_mid_dump_writes_nothing(self):
        def factory(_node):
            return FakeBootloader(self.flash, error=1)

        rc = bf.run_backup(self.out, open_transport=factory,
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))

    def test_existing_output_is_refused(self):
        Path(self.out).write_bytes(b"precious")
        rc = bf.run_backup(self.out, open_transport=NoDeviceTransport,
                           select_node=self._select, plan=SHORT_PLAN)
        self.assertEqual(rc, 2)
        self.assertEqual(Path(self.out).read_bytes(), b"precious")

    def test_fewer_than_three_passes_refused(self):
        rc = bf.run_backup(self.out, passes=2, open_transport=NoDeviceTransport,
                           select_node=self._select, plan=SHORT_PLAN)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(self.out))

    def test_selection_failure_never_opens_a_device(self):
        def refuse():
            raise bf.SelectionError("none found")

        rc = bf.run_backup(self.out, open_transport=NoDeviceTransport,
                           select_node=refuse, plan=SHORT_PLAN)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(self.out))

    def test_transport_open_failure_is_reported_without_traceback(self):
        def factory(_node):
            raise PermissionError(13, "Permission denied")

        rc = bf.run_backup(self.out, open_transport=factory,
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(self.out))

    def test_close_error_does_not_mask_the_protocol_error(self):
        class BadClose(FakeBootloader):
            def close(self):
                raise OSError(5, "Input/output error")

        def factory(_node):
            return BadClose(self.flash, error=3)      # bad length -> ProtocolError

        rc = bf.run_backup(self.out, open_transport=factory,
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 1)                        # protocol abort, not a crash
        self.assertFalse(os.path.exists(self.out))

    def test_close_error_alone_does_not_fail_a_good_dump(self):
        class BadClose(FakeBootloader):
            def close(self):
                raise OSError(5, "Input/output error")

        rc = bf.run_backup(self.out, open_transport=lambda _n: BadClose(self.flash),
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 0)
        self.assertEqual(Path(self.out).read_bytes(), self.expected)

    def test_validation_failure_rejects_all_passes(self):
        def failing(_image):
            raise bf.ValidationError("record[1] checksum mismatch")

        rc = bf.run_backup(self.out, open_transport=lambda _n: FakeBootloader(self.flash),
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=failing)
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(self.out))

    def test_write_failure_leaves_no_partial_output(self):
        readonly = Path(self.tmp.name, "ro")
        readonly.mkdir(mode=0o555)
        self.addCleanup(readonly.chmod, 0o755)
        target = str(readonly / "dump.bin")
        rc = bf.run_backup(target, open_transport=lambda _n: FakeBootloader(self.flash),
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(target))

    def test_output_race_is_refused_and_temp_cleaned(self):
        """Another writer creates the output after the pre-flight check."""
        def racing_validate(_image):
            Path(self.out).write_bytes(b"someone else got here")
            return []

        rc = bf.run_backup(self.out, open_transport=lambda _n: FakeBootloader(self.flash),
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=racing_validate)
        self.assertEqual(rc, 2)
        self.assertEqual(Path(self.out).read_bytes(), b"someone else got here")
        self.assertEqual(self._stray_temp_files(), [])

    def _stray_temp_files(self):
        return [n for n in os.listdir(self.tmp.name) if n.startswith(".backup_firmware-")]

    def test_successful_publish_leaves_no_temp_file(self):
        rc = bf.run_backup(self.out, open_transport=lambda _n: FakeBootloader(self.flash),
                           select_node=self._select, plan=SHORT_PLAN,
                           validate=self._skip_validation)
        self.assertEqual(rc, 0)
        self.assertEqual(self._stray_temp_files(), [])


# ---------------------------------------------------------------------------
# report-descriptor parsing and node selection
# ---------------------------------------------------------------------------
def descriptor(page=0xFF01, size=8, count=64, report_id=None):
    out = bytearray([0x06, page & 0xFF, page >> 8, 0x09, 0x01, 0xA1, 0x01])
    if report_id is not None:
        out += bytes([0x85, report_id])
    for usage, main in ((0x02, 0x81), (0x03, 0x91)):
        out += bytes([0x09, usage, 0x15, 0x00, 0x26, 0xFF, 0x00,
                      0x75, size, 0x95, count, main, 0x02])
    out += bytes([0xC0])
    return bytes(out)


class TestDescriptor(unittest.TestCase):
    def test_expected_descriptor_accepted(self):
        self.assertEqual(bf.descriptor_reasons(descriptor()), [])

    def test_wrong_usage_page_rejected(self):
        reasons = bf.descriptor_reasons(descriptor(page=0xFF00))
        self.assertTrue(any("usage page 0xff01 absent" in r for r in reasons))

    def test_wrong_report_size_rejected(self):
        reasons = bf.descriptor_reasons(descriptor(count=32))
        self.assertTrue(any("64-byte IN" in r for r in reasons))
        self.assertTrue(any("64-byte OUT" in r for r in reasons))

    def test_report_id_rejected(self):
        reasons = bf.descriptor_reasons(descriptor(report_id=1))
        self.assertTrue(any("report ID" in r for r in reasons))

    def test_truncated_descriptor_raises(self):
        with self.assertRaises(ValueError):
            bf.descriptor_facts(bytes([0x06, 0x01]))


class TestSelection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def add(self, name, pid, desc=None, vid=bf.VID):
        base = os.path.join(self.root, name, "device")
        os.makedirs(base)
        Path(base, "uevent").write_text(
            f"DRIVER=hid-generic\nHID_ID=0003:{vid:08X}:{pid:08X}\n")
        if desc is not None:
            Path(base, "report_descriptor").write_bytes(desc)

    def select(self):
        return bf.select_bootloader_node(sysfs_root=self.root, dev_root="/dev")

    def test_single_valid_node_selected(self):
        self.add("hidraw0", bf.PID_APP, descriptor(page=0xFF00))
        self.add("hidraw1", bf.PID_BOOT, descriptor())
        node, rejected, app_nodes = self.select()
        self.assertEqual(node, "/dev/hidraw1")
        self.assertEqual(rejected, [])
        self.assertEqual(app_nodes, ["hidraw0"])

    def test_zero_candidates_refused(self):
        self.add("hidraw0", bf.PID_APP, descriptor())
        with self.assertRaises(bf.SelectionError) as ctx:
            self.select()
        self.assertIn("no validated PID-1b7f", str(ctx.exception))

    def test_multiple_candidates_refused(self):
        self.add("hidraw1", bf.PID_BOOT, descriptor())
        self.add("hidraw2", bf.PID_BOOT, descriptor())
        with self.assertRaises(bf.SelectionError) as ctx:
            self.select()
        self.assertIn("refusing to guess", str(ctx.exception))

    def test_pid_match_with_wrong_descriptor_refused(self):
        """The first PID-only node must never be selected on PID alone."""
        self.add("hidraw1", bf.PID_BOOT, descriptor(page=0x0001, count=8))
        with self.assertRaises(bf.SelectionError) as ctx:
            self.select()
        self.assertIn("no validated PID-1b7f", str(ctx.exception))

    def test_correct_node_chosen_among_pid_siblings(self):
        self.add("hidraw1", bf.PID_BOOT, descriptor(page=0x0001, count=8))
        self.add("hidraw2", bf.PID_BOOT, descriptor())
        self.add("hidraw3", bf.PID_BOOT, descriptor(report_id=3))
        node, rejected, _app = self.select()
        self.assertEqual(node, "/dev/hidraw2")
        self.assertEqual(len(rejected), 2)

    def test_missing_descriptor_rejected(self):
        self.add("hidraw1", bf.PID_BOOT, None)
        with self.assertRaises(bf.SelectionError) as ctx:
            self.select()
        self.assertIn("unreadable", str(ctx.exception))

    def test_other_vendor_ignored(self):
        self.add("hidraw0", bf.PID_BOOT, descriptor(), vid=0x046D)
        with self.assertRaises(bf.SelectionError):
            self.select()


VENDOR_BIN = Path(__file__).resolve().parent.parent / "dumps/vendor/M605_V01_00_58.bin"


@unittest.skipUnless(VENDOR_BIN.exists(), "preserved vendor image is absent")
class TestDumpValidation(unittest.TestCase):
    """Exercises the real default validator, not a mock.

    The app region of the preserved 1.00.58 image is a structurally valid
    app-region dump, so it stands in for a good read-back.
    """

    @classmethod
    def setUpClass(cls):
        cls.good = VENDOR_BIN.read_bytes()[bf.REGION_LO:bf.REGION_HI]

    def test_good_dump_passes_and_states_skipped_checks(self):
        lines = bf.validate_dump(self.good)
        text = "\n".join(lines)
        self.assertIn("SKIP bootloader word-sum", text)
        self.assertIn("SKIP primary container", text)
        self.assertNotIn("FAIL", text)
        self.assertIn("PASS record[0] checksum", text)
        self.assertIn("PASS record[1] checksum", text)
        self.assertIn("PASS application word-sum", text)
        self.assertIn("PASS boot: SN_FWIN magic", text)

    def test_wrong_size_rejected(self):
        for bad in (self.good[:-1], self.good + b"\x00", b""):
            with self.assertRaises(bf.ValidationError) as ctx:
                bf.validate_dump(bad)
            self.assertIn("expected exactly 0x6c000", str(ctx.exception))

    def test_shifted_dump_rejected(self):
        """The exact corruption the post-EXEC race would produce."""
        shifted = self.good[1:] + b"\x00"
        with self.assertRaises(bf.ValidationError):
            bf.validate_dump(shifted)

    def test_stale_repeated_chunk_rejected(self):
        """A chunk that returned the previous chunk's buffer, inside record[0]."""
        stale = bytearray(self.good)
        stale[0x2000:0x2030] = stale[0x1FD0:0x2000]
        with self.assertRaises(bf.ValidationError) as ctx:
            bf.validate_dump(bytes(stale))
        self.assertIn("record[0] checksum", str(ctx.exception))

    def test_stale_chunk_over_the_record_table_rejected(self):
        stale = bytearray(self.good)
        stale[0x30:0x60] = stale[0x00:0x30]
        with self.assertRaises(bf.ValidationError):
            bf.validate_dump(bytes(stale))

    def test_single_bit_flip_rejected(self):
        flipped = bytearray(self.good)
        flipped[0x11000] ^= 0x01
        with self.assertRaises(bf.ValidationError) as ctx:
            bf.validate_dump(bytes(flipped))
        self.assertIn("checksum", str(ctx.exception))

    def test_destroyed_header_reports_parse_failure(self):
        broken = bytearray(self.good)
        broken[0:0x40] = b"\xff" * 0x40             # wreck the SN_FWIN header
        with self.assertRaises(bf.ValidationError):
            bf.validate_dump(bytes(broken))

    def test_validator_is_the_default_in_run_backup(self):
        import inspect
        default = inspect.signature(bf.run_backup).parameters["validate"].default
        self.assertIs(default, bf.validate_dump)


class TestHidrawFraming(unittest.TestCase):
    """Exercise the transport's framing over a pipe. No device is opened."""

    def test_write_prepends_report_number_zero(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, read_fd)
        transport = object.__new__(bf.HidrawTransport)
        transport.fd = write_fd
        report = bf.build_report(bf.Q_STATUS)
        transport.write(report)
        transport.close()
        framed = os.read(read_fd, bf.REPORT_LEN + 1)
        self.assertEqual(len(framed), bf.REPORT_LEN + 1)
        self.assertEqual(framed[0], 0)
        self.assertEqual(framed[1:], report)

    def test_read_returns_report_data_without_prefix(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        transport = object.__new__(bf.HidrawTransport)
        transport.fd = read_fd
        payload = bytes([bf.R_READDATA]) + b"\xab" * (bf.REPORT_LEN - 1)
        os.write(write_fd, payload)
        self.assertEqual(transport.read(1.0), payload)
        transport.close()

    def test_read_times_out(self):
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        self.addCleanup(os.close, read_fd)
        transport = object.__new__(bf.HidrawTransport)
        transport.fd = read_fd
        with self.assertRaises(bf.ProtocolError) as ctx:
            transport.read(0.01)
        self.assertIn("no response report", str(ctx.exception))


class TestCli(unittest.TestCase):
    def test_run_without_acknowledgement_is_refused(self):
        args = bf.parse_args(["--run", "/tmp/nope.bin"])
        self.assertFalse(args.force_unreviewed)
        self.assertEqual(bf.main(["--run", "/tmp/nope.bin"]), 2)
        self.assertFalse(os.path.exists("/tmp/nope.bin"))

    def test_default_is_dry_run(self):
        self.assertIsNone(bf.parse_args([]).run)


if __name__ == "__main__":
    unittest.main(verbosity=2)
