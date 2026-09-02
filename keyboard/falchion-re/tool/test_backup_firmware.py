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
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backup_firmware as bf


# ---------------------------------------------------------------------------
# offline model of the 1b7f responder (logs 81-82)
# ---------------------------------------------------------------------------
class FakeBootloader:
    """Offline model of the 1b7f responder, faithful to logs 81/82/85/86.

    The point of this model is that it reproduces the scheduling and the
    *non-atomicity* the firmware actually has, not an idealised version:

      * `write()` runs in USB-interrupt context. The 0x1f EXEC parser only sets
        the pending byte state+0x34, and drops the report entirely if that byte
        is already non-zero (the `bne` at 0x000038de). It performs no flash
        access.
      * `_tick()` models FUN_00003a7c -> FUN_00002db8, which the main loop only
        reaches on a SysTick tick. It samples the address and length *current at
        dispatch time* and starts a transfer.
      * A transfer is NOT atomic. FUN_00003b64 does not mask interrupts, so the
        USB responder can run while state+4 is only partly written. The transfer
        advances `write_step` bytes per query opportunity, and `_data()` serves
        `target[:written] + previous[written:]` -- a genuine half-old/half-new
        buffer. state+0x38 bit 1 is set for exactly the duration of the transfer,
        matching the stores at 0x00002e0a and 0x00002e1e.
      * `dispatch_delay` sets how many query opportunities pass before the tick
        fires; `None` means the service loop never runs.
      * The buffer starts as 0x30 zero bytes, matching the Region$$Table
        zero-init at 0x0000ccc0 (log 86). `residue=` overrides it to model a
        bootloader that has already served a READ.

    Fault-injection knobs mirror the failure modes the tool must abort on.
    """

    def __init__(self, flash, *, dispatch_delay=0, write_step=None, error=0,
                 code_override=None, resp_len=None, unlocked=False,
                 residue=None, foreign_pending=None, foreign_delay=0):
        self.flash = flash                  # bytes covering [REGION_LO, REGION_HI)
        self.dispatch_delay = dispatch_delay
        self.countdown = 0 if dispatch_delay is None else dispatch_delay
        self.write_step = write_step        # None = whole transfer in one step
        self.error = error
        self.code_override = code_override
        self.resp_len = bf.REPORT_LEN if resp_len is None else resp_len
        self.flags = bf.UNLOCK_BIT if unlocked else 0
        self.addr = self.length = None
        self.pending = 0                    # state+0x34
        self.buffer = bytes(bf.REPORT_LEN) if residue is None else residue
        self.transfer = None                # (target_bytes, written) while busy
        # a READ queued by some other host before this tool attached: state+0x34
        # is already non-zero and its address is not one we chose
        self.foreign_pending = foreign_pending
        self.foreign_delay = foreign_delay
        if foreign_pending is not None:
            self.pending = bf.OP_READ
            self.addr = foreign_pending
            self.length = 0x30
        self.log = []                       # (sub, payload) in send order
        self.reads = 0
        self.dispatches = 0
        self.dropped_execs = 0
        self.served_partial = 0
        self.queued = None
        self.closed = False

    # -- transport surface: this is the USB interrupt (FUN_0000bd40) -----------
    def write(self, report):
        # The device sees the 64-byte report; the hidraw report-number byte is
        # added by HidrawTransport (see TestHidrawFraming).
        assert len(report) == bf.REPORT_LEN, "reports are exactly 64 bytes"
        sub, payload = report[0], report[1:]
        self.log.append((sub, payload))
        assert sub not in bf.FORBIDDEN, f"fake device saw forbidden 0x{sub:02x}"
        # The main loop runs independently of USB traffic, so every report is an
        # opportunity for a dispatch -- including a set-address report, which is
        # where the foreign-pending hole lives.
        self._advance()
        if sub == bf.SET_ADDR:
            self.addr = struct.unpack("<I", payload[:4])[0]
        elif sub == bf.SET_LEN:
            self.length = struct.unpack("<H", payload[:2])[0]
        elif sub == bf.EXEC:
            assert payload[0] == bf.OP_READ
            if self.pending:                    # 0x000038de: bne, nothing stored
                self.dropped_execs += 1
                return
            self.pending = bf.OP_READ
            self.error = self.error or self._exec_verdict()
        elif sub == bf.Q_STATUS:
            self.queued = self._status()
        elif sub == bf.Q_READDATA:
            self.queued = self._data()
        else:
            raise AssertionError(f"unexpected sub-command 0x{sub:02x}")

    def _exec_verdict(self):
        """The 0x1f parser's own synchronous verdict for a READ (log 85 sec. H)."""
        if not bf.REGION_LO <= self.addr < bf.REGION_HI:
            return 1                            # 0x00003984
        if not 0 < self.length <= bf.CHUNK_MAX:
            return 3                            # 0x00003964
        return 0

    # -- the main loop: FUN_00003a7c -> FUN_00002db8 -> FUN_00003b64 -----------
    def _advance(self):
        """One opportunity for the main loop to make progress."""
        if self.transfer is not None:           # a transfer is already running
            target, written = self.transfer
            step = len(target) if self.write_step is None else self.write_step
            written = min(written + step, len(target))
            if written >= len(target):
                self.buffer = target + self.buffer[len(target):]
                self.transfer = None
                self.pending = 0                # state+0x34 cleared last
                self.dispatches += 1
                self.countdown = 0 if self.dispatch_delay is None else self.dispatch_delay
            else:
                self.transfer = (target, written)
            return
        if not self.pending or self.dispatch_delay is None:
            return
        if self.foreign_pending is not None:
            if self.foreign_delay > 0:
                self.foreign_delay -= 1
                return
        elif self.countdown > 0:
            self.countdown -= 1
            return
        off = self.addr - bf.REGION_LO
        target = self.flash[off:off + self.length]
        self.foreign_pending = None
        if self.write_step is None or self.write_step >= len(target):
            self.buffer = target + self.buffer[len(target):]
            self.pending = 0
            self.dispatches += 1
            self.countdown = 0 if self.dispatch_delay is None else self.dispatch_delay
        else:
            self.transfer = (target, self.write_step)

    def read(self, timeout):
        if self.queued is None:
            raise bf.ProtocolError("fake: read with no outstanding query")
        resp, self.queued = self.queued, None
        self.reads += 1
        return resp

    def close(self):
        self.closed = True

    # -- responses (FUN_00003740) --------------------------------------------
    def _frame(self, code, body=b""):
        if self.code_override is not None:
            code = self.code_override
        resp = bytes([code]) + bytes(body)
        resp += b"\x00" * (bf.REPORT_LEN - len(resp))
        return resp[:self.resp_len]

    def _status(self):
        flags = self.flags
        if self.transfer is not None:           # bit 1 held across FUN_00003b64
            flags |= bf.BUSY_READ
        return self._frame(bf.R_STATUS, bytes([flags, self.error]))

    def _visible(self):
        """state+4 as the responder would copy it right now."""
        if self.transfer is None:
            return self.buffer
        target, written = self.transfer
        return target[:written] + self.buffer[written:]

    def _data(self):
        view = self._visible()
        if self.transfer is not None:
            self.served_partial += 1
        return self._frame(bf.R_READDATA, view[:self.length])


def read_one(dev, addr, length=0x30):
    """Bootstrap a baseline the way dump_once does, then read one chunk."""
    baseline = bf.bootstrap_baseline(dev, length)
    return bf.read_chunk(dev, addr, length, baseline)


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
        self.assertEqual(read_one(dev, bf.REGION_LO), flash[:0x30])
        self.assertEqual([sub for sub, _p in dev.log],
                         [bf.SET_LEN, bf.Q_STATUS, bf.Q_READDATA,     # bootstrap
                          bf.SET_LEN, bf.SET_ADDR, bf.EXEC,           # queue
                          bf.Q_READDATA, bf.Q_STATUS,                 # sample, then status
                          bf.Q_READDATA])                             # confirming fetch
        self.assertEqual(dev.reads, 5)          # one read per query, never batched

    def test_data_query_precedes_its_status(self):
        """The ordering is the whole proof: the status that qualifies a sample
        must be read AFTER that sample, never before."""
        dev = FakeBootloader(flash_bytes())
        read_one(dev, bf.REGION_LO)
        subs = [sub for sub, _p in dev.log]
        first_exec = subs.index(bf.EXEC)
        after = subs[first_exec + 1:]
        self.assertEqual(after[0], bf.Q_READDATA)
        self.assertEqual(after[1], bf.Q_STATUS)

    def test_each_query_is_read_immediately(self):
        """Regression: the old code queued 0x8f and 0xaa then read once, so the
        status report was consumed as read data."""
        dev = FakeBootloader(flash_bytes())
        read_one(dev, bf.REGION_LO)
        queries = sum(1 for sub, _p in dev.log
                      if sub in (bf.Q_STATUS, bf.Q_READDATA))
        self.assertEqual(dev.reads, queries)    # exactly one read per query

    # -- log 86: the partial-buffer counterexample ---------------------------
    def test_fake_really_serves_a_half_old_half_new_buffer(self):
        """Guards the model itself. If _tick() ever goes back to replacing the
        buffer atomically, every partial-write test below becomes vacuous."""
        flash = flash_bytes()
        dev = FakeBootloader(flash, write_step=8, dispatch_delay=0)
        bf.send(dev, bf.SET_LEN, struct.pack("<H", 0x30))
        bf.send(dev, bf.SET_ADDR, struct.pack("<I", bf.REGION_LO))
        bf.send(dev, bf.EXEC, bytes([bf.OP_READ]))
        mixed = bf.fetch(dev, 0x30)             # transfer starts, 8 bytes in
        self.assertEqual(mixed, flash[:8] + bytes(0x28))
        self.assertNotEqual(mixed, flash[:0x30])
        self.assertNotEqual(mixed, bytes(0x30))
        # bit 1 is held for exactly the duration of the transfer (0x2e0a/0x2e1e)
        self.assertEqual(bf.check_status(dev) & bf.BUSY_READ, bf.BUSY_READ)
        self.assertEqual(dev.served_partial, 1)

    def test_log86_counterexample_step_by_step(self):
        """The exact interleaving the review found, made explicit and permanent:

          1. the status query is answered before the pending READ starts, so
             state+0x38 bit 1 reads CLEAR;
          2. the SysTick tick then lets the main loop begin FUN_00003b64;
          3. the USB responder runs while state+4 is only partly updated;
          4. the 0xaa reply is a mixture of new and baseline bytes;
          5. the old rule -- status first, accept any sample that differs from
             the baseline -- accepts that mixture.

        Every assertion below is on raw protocol primitives, so this test pins
        the counterexample independently of how read_fresh is written."""
        flash = flash_bytes()
        dev = FakeBootloader(flash, write_step=8, dispatch_delay=1)
        baseline = bf.bootstrap_baseline(dev, 0x30)
        bf.exec_read(dev, bf.REGION_LO, 0x30)

        # (1) status answered before the READ starts
        self.assertEqual(bf.check_status(dev) & bf.BUSY_READ, 0)
        self.assertIsNone(dev.transfer)

        # (2)(3)(4) the transfer starts and the fetch lands inside it
        mixture = bf.fetch(dev, 0x30)
        self.assertEqual(mixture, flash[:8] + bytes(0x28))
        self.assertIsNotNone(dev.transfer)

        # (5) the old accept condition is satisfied by a WRONG value
        self.assertNotEqual(mixture, baseline)          # old rule would accept
        self.assertNotEqual(mixture, flash[:0x30])      # and it is not the chunk

        # the corrected rule reads the qualifying status AFTER the sample, and
        # that status still reports the transfer in flight
        self.assertEqual(bf.check_status(dev) & bf.BUSY_READ, bf.BUSY_READ)

    def test_partial_buffer_is_never_returned(self):
        """The log-86 counterexample. Status taken before the fetch reads busy
        clear, then the transfer starts and the fetch lands inside it. Every
        value read_fresh returns must be a whole chunk, never a mixture."""
        flash = flash_bytes()
        for step in (1, 4, 8, 16, 24, 40, 47):
            for delay in (0, 1, 2, 5):
                dev = FakeBootloader(flash, write_step=step, dispatch_delay=delay)
                got = read_one(dev, bf.REGION_LO)
                self.assertEqual(got, flash[:0x30],
                                 f"step={step} delay={delay} returned a partial buffer")

    def test_partial_buffers_were_actually_served_during_those_reads(self):
        """Non-vacuity: the run above must really have handed out mixtures."""
        dev = FakeBootloader(flash_bytes(), write_step=8, dispatch_delay=1)
        read_one(dev, bf.REGION_LO)
        self.assertGreater(dev.served_partial, 0)

    def test_whole_dump_survives_partial_writes(self):
        flash = flash_bytes(0x120)
        plan = [(bf.REGION_LO + i * 0x30, 0x30) for i in range(6)]
        for step in (4, 16, 31, 47):
            dev = FakeBootloader(flash, write_step=step, dispatch_delay=2)
            image, baseline = bf.dump_once(dev, plan)
            self.assertEqual(image, flash[:0x120], f"step={step}")
            self.assertEqual(baseline, flash[0xf0:0x120])

    # -- the post-EXEC scheduling race (log 85) ------------------------------
    def test_stale_buffer_is_never_accepted_before_dispatch(self):
        flash = flash_bytes()
        dev = FakeBootloader(flash, dispatch_delay=6)
        got = read_one(dev, bf.REGION_LO)
        self.assertEqual(got, flash[:0x30])
        self.assertGreaterEqual(dev.dispatches, 1)

    def test_first_status_reply_shows_busy_clear_while_stale(self):
        """Pins the mechanism: with dispatch pending, status says 'not busy' and
        the data query returns the previous buffer."""
        dev = FakeBootloader(flash_bytes(), dispatch_delay=None)   # never runs
        bf.send(dev, bf.SET_LEN, struct.pack("<H", 0x30))
        bf.send(dev, bf.SET_ADDR, struct.pack("<I", bf.REGION_LO))
        bf.send(dev, bf.EXEC, bytes([bf.OP_READ]))
        self.assertEqual(bf.check_status(dev) & bf.BUSY_READ, 0)   # clear!
        self.assertEqual(bf.fetch(dev, 0x30), bytes(0x30))

    def test_never_dispatching_device_aborts(self):
        dev = FakeBootloader(flash_bytes(), dispatch_delay=None)
        with self.assertRaises(bf.ProtocolError) as ctx:
            read_one(dev, bf.REGION_LO)
        self.assertIn("never changed", str(ctx.exception))
        self.assertEqual(dev.dispatches, 0)

    def test_polling_is_bounded_by_attempts(self):
        dev = FakeBootloader(flash_bytes(), dispatch_delay=None)
        with self.assertRaises(bf.ProtocolError):
            read_one(dev, bf.REGION_LO)
        self.assertEqual(sum(1 for sub, _p in dev.log if sub == bf.Q_STATUS),
                         1 + bf.FRESH_ATTEMPTS)      # bootstrap + handshake rounds

    def test_exec_is_re_armed_because_the_parser_drops_it_while_pending(self):
        flash = flash_bytes()
        dev = FakeBootloader(flash, dispatch_delay=5)
        self.assertEqual(read_one(dev, bf.REGION_LO), flash[:0x30])
        self.assertGreater(dev.dropped_execs, 0)

    def test_re_armed_exec_left_pending_does_not_corrupt_the_next_chunk(self):
        """A re-armed EXEC can still be pending when read_fresh returns. It reads
        whatever address is current when it finally dispatches, so it either
        re-reads this chunk (no change) or performs the next one. Neither breaks
        the next chunk's baseline/address association."""
        flash = flash_bytes(0xc0)
        plan = [(bf.REGION_LO + i * 0x30, 0x30) for i in range(4)]
        for delay in (1, 2, 3, 7):
            dev = FakeBootloader(flash, dispatch_delay=delay, write_step=13)
            image, _b = bf.dump_once(dev, plan)
            self.assertEqual(image, flash[:0xc0], f"delay={delay}")
            self.assertGreater(dev.dropped_execs, 0, f"delay={delay}")

    # -- bootstrap (log 86 Region$$Table zero-init) --------------------------
    def test_bootstrap_accepts_the_zero_initialised_buffer(self):
        dev = FakeBootloader(flash_bytes())
        self.assertEqual(bf.bootstrap_baseline(dev, 0x30), bytes(0x30))

    def test_bootstrap_refuses_a_bootloader_that_already_served_a_read(self):
        dev = FakeBootloader(flash_bytes(), residue=b"\xa5" * bf.REPORT_LEN)
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.bootstrap_baseline(dev, 0x30)
        self.assertIn("zero bytes", str(ctx.exception))

    def test_foreign_read_that_completed_before_the_bootstrap_is_refused(self):
        """A previously queued foreign READ that has already published its bytes
        leaves state+4 non-zero, which the bootstrap rejects."""
        flash = flash_bytes(0x120)
        dev = FakeBootloader(flash, foreign_pending=bf.REGION_LO + 0x60)
        dev._advance()                          # the foreign READ dispatches
        self.assertEqual(dev.dispatches, 1)
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.bootstrap_baseline(dev, 0x30)
        self.assertIn("already driven a READ", str(ctx.exception))

    def test_foreign_pending_read_completing_after_the_bootstrap_is_the_known_hole(self):
        """DOCUMENTED RESIDUAL, log 86. A foreign READ that is queued but has not
        dispatched is invisible: state+0x34 is exposed by no query. If it lands
        between the bootstrap fetch and this tool's first set-address it publishes
        an unrelated address's bytes, and the handshake accepts them, because from
        the host's side that is indistinguishable from its own read completing.

        This test asserts the hole rather than hiding it. It is closed only by the
        operational precondition that nothing else talks to the node, and it will
        fail loudly if anyone later believes they have fixed it."""
        flash = flash_bytes(0x120)
        # bootstrap spends 3 report opportunities (set-len, status, data); the
        # foreign READ dispatches on the 5th, which is this tool's set-address
        # report, i.e. after the baseline was taken but before our address is in.
        dev = FakeBootloader(flash, foreign_pending=bf.REGION_LO + 0x60,
                             foreign_delay=4, dispatch_delay=20)
        baseline = bf.bootstrap_baseline(dev, 0x30)     # foreign not yet dispatched
        self.assertEqual(baseline, bytes(0x30))
        got = bf.read_chunk(dev, bf.REGION_LO, 0x30, baseline)
        self.assertEqual(got, flash[0x60:0x90])         # the FOREIGN address's bytes
        self.assertNotEqual(got, flash[0x00:0x30])      # not the one we asked for

    def test_later_passes_carry_the_baseline_instead_of_re_bootstrapping(self):
        """The all-zero bootstrap is only true before any READ has run, so pass 2
        must be handed pass 1's proven final value."""
        flash = flash_bytes(0x90)
        plan = [(bf.REGION_LO + i * 0x30, 0x30) for i in range(3)]
        dev = FakeBootloader(flash)
        first, baseline = bf.dump_once(dev, plan)
        second, _b = bf.dump_once(dev, plan, baseline)
        self.assertEqual(first, second)
        self.assertEqual(first, flash[:0x90])
        with self.assertRaises(bf.ProtocolError):       # re-bootstrapping must fail
            bf.dump_once(dev, plan)

    def test_carried_baseline_length_must_match(self):
        dev = FakeBootloader(flash_bytes())
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.dump_once(dev, SHORT_PLAN, bytes(0x10))
        self.assertIn("carried baseline", str(ctx.exception))

    # -- undecidable cases ---------------------------------------------------
    def test_identical_neighbour_chunks_are_rebased_through_an_anchor(self):
        head = bytes(range(0x30))
        pad = b"\xff" * 0x30
        flash = head + pad + pad                 # chunks 1 and 2 are identical
        dev = FakeBootloader(flash)
        plan = [(bf.REGION_LO + i * 0x30, 0x30) for i in range(3)]
        image, _b = bf.dump_once(dev, plan)
        self.assertEqual(image, flash)
        self.assertGreater(sum(1 for sub, payload in dev.log
                               if sub == bf.SET_ADDR
                               and struct.unpack("<I", payload[:4])[0] == bf.REGION_LO),
                           1)

    def test_identical_chunks_with_no_anchor_abort(self):
        pad = b"\x11" * 0x30
        dev = FakeBootloader(pad + pad)
        plan = [(bf.REGION_LO, 0x30), (bf.REGION_LO + 0x30, 0x30)]
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.dump_once(dev, plan)
        self.assertIn("no anchor chunk", str(ctx.exception))

    def test_all_zero_first_chunk_is_undecidable_against_the_zero_baseline(self):
        """The bootstrap baseline is 0x30 zero bytes, so a first chunk that is
        itself all zeros cannot be told apart from 'not dispatched'. The real
        region starts with the SN_FWIN container magic, but the tool must abort
        rather than assume."""
        dev = FakeBootloader(bytes(0x30))
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.dump_once(dev, [(bf.REGION_LO, 0x30)])
        self.assertIn("never changed", str(ctx.exception))

    def test_mixed_length_plan_is_refused(self):
        dev = FakeBootloader(flash_bytes())
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.dump_once(dev, [(bf.REGION_LO, 0x30), (bf.REGION_LO + 0x30, 0x20)])
        self.assertIn("mixed chunk lengths", str(ctx.exception))

    def test_baseline_length_mismatch_is_refused(self):
        dev = FakeBootloader(flash_bytes())
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.read_fresh(dev, bf.REGION_LO, 0x30, b"\x00" * 0x10)
        self.assertIn("same-length baseline", str(ctx.exception))

    # -- status semantics ----------------------------------------------------
    def test_status_error_aborts(self):
        for code, text in bf.STATUS_ERRORS.items():
            dev = FakeBootloader(flash_bytes(), error=code)
            with self.assertRaises(bf.ProtocolError) as ctx:
                read_one(dev, bf.REGION_LO)
            self.assertIn(text, str(ctx.exception))

    def test_unlocked_device_is_refused(self):
        dev = FakeBootloader(flash_bytes(), unlocked=True)
        with self.assertRaises(bf.ProtocolError) as ctx:
            read_one(dev, bf.REGION_LO)
        self.assertIn("bit 7", str(ctx.exception))

    def test_erase_or_program_in_progress_is_refused(self):
        dev = FakeBootloader(flash_bytes())
        dev.flags |= bf.BUSY_WRITE
        with self.assertRaises(bf.ProtocolError) as ctx:
            read_one(dev, bf.REGION_LO)
        self.assertIn("bit 0", str(ctx.exception))

    def test_wrong_response_code_aborts(self):
        dev = FakeBootloader(flash_bytes(), code_override=0x7F)
        with self.assertRaises(bf.ProtocolError) as ctx:
            read_one(dev, bf.REGION_LO)
        self.assertIn("wrong response code 0x7f", str(ctx.exception))

    def test_data_response_code_must_be_0x2a(self):
        dev = FakeBootloader(flash_bytes())
        bf.send(dev, bf.SET_LEN, struct.pack("<H", 0x30))
        dev.code_override = bf.R_STATUS            # answer data query as status
        with self.assertRaises(bf.ProtocolError) as ctx:
            bf.query(dev, bf.Q_READDATA, bf.R_READDATA)
        self.assertIn("expected 0x2a", str(ctx.exception))

    def test_short_report_aborts(self):
        dev = FakeBootloader(flash_bytes(), resp_len=32)
        with self.assertRaises(bf.ProtocolError) as ctx:
            read_one(dev, bf.REGION_LO)
        self.assertIn("short response: 32 of 64", str(ctx.exception))

    def test_payload_skips_only_the_response_code(self):
        flash = flash_bytes()
        dev = FakeBootloader(flash)
        got = read_one(dev, bf.REGION_LO)
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
        """All passes share one handle: the bootstrap all-zero check is only true
        before any READ has run, so later passes carry the proven baseline."""
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
        self.assertEqual(len(made), 1)          # one open, three passes
        self.assertTrue(all(d.closed for d in made))
        self.assertGreaterEqual(made[0].dispatches, 3 * len(SHORT_PLAN))

    def test_production_defaults_open_distinct_command_and_response_nodes(self):
        opened = []

        def factory(command_node, response_node):
            opened.append((command_node, response_node))
            return FakeBootloader(self.flash)

        selected = ("/dev/ff01", "/dev/ff00", [], [], [])
        with mock.patch.object(bf, "select_bootloader_channels",
                               return_value=selected):
            rc = bf.run_backup(self.out, open_transport=factory,
                               plan=SHORT_PLAN,
                               validate=self._skip_validation)
        self.assertEqual(rc, 0)
        self.assertEqual(opened, [("/dev/ff01", "/dev/ff00")])

    def test_mismatched_passes_refuse_to_write(self):
        """The flash changes under the tool between passes 2 and 3."""
        flipped = bytes([self.flash[0] ^ 0xFF]) + self.flash[1:]
        dev = FakeBootloader(self.flash)
        passes_seen = []
        original_dump = bf.dump_once

        def counting_dump(transport, plan=None, baseline=None):
            passes_seen.append(len(passes_seen))
            if len(passes_seen) == 3:
                transport.flash = flipped
            return original_dump(transport, plan, baseline)

        bf.dump_once = counting_dump
        self.addCleanup(setattr, bf, "dump_once", original_dump)
        rc = bf.run_backup(self.out, open_transport=lambda _n: dev,
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

    def test_ff00_response_descriptor_accepted_when_explicit(self):
        self.assertEqual(
            bf.descriptor_reasons(descriptor(page=0xFF00),
                                  usage_page=bf.RESPONSE_USAGE_PAGE), [])

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

    def test_explicit_ff00_response_node_selected(self):
        self.add("hidraw1", bf.PID_BOOT, descriptor(page=0xFF01))
        self.add("hidraw2", bf.PID_BOOT, descriptor(page=0xFF00))
        node, rejected, _app_nodes = bf.select_bootloader_node(
            sysfs_root=self.root, dev_root="/dev", usage_page=bf.RESPONSE_USAGE_PAGE)
        self.assertEqual(node, "/dev/hidraw2")
        self.assertEqual(len(rejected), 1)

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
