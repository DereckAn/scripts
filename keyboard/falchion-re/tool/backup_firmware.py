#!/usr/bin/env python3
"""Read-only firmware backup tool for the ROG Falchion Ace HFX bootloader.

Reads the *application* flash region only: base 0x10000, size 0x6c000
(0x10000..0x7c000), while the device is in bootloader mode (PID 1b7f), over the
vendor-HID framing recovered statically in logs 81-82 and 89. The bootloader region
[0x0, 0x10000) is not readable over USB and is not part of the output.

SAFETY
  * Only set-address (0x20), set-length (0x21), execute-READ (0x1f/0x05) and the
    queries 0x8f/0xaa can pass `guard()`. Unlock (0x10), load-data (0x22),
    reset (0x11), erase (0x01) and program (0x51) have no construction path, and
    `guard()` re-runs on the exact bytes immediately before every write.
  * Default action is --dry-run: it builds and validates the whole dump plan
    without opening any device.
  * --run additionally requires --force-unreviewed. Live use is unauthorised
    pending independent review; see UNRESOLVED below.

PROTOCOL EVIDENCE (the READ behavior below is static; no READ has run on hardware)
  * log 81 `FUN_00002db8`: on command byte 0x05 it sets state+0x38 bit 1
    (`(+0x38 & 0xfd) + 2`), calls the synchronous READ `FUN_00003b64`, then
    clears bit 1 (`+0x38 & 0xfd`) and clears the pending byte +0x34. Erase (0x01)
    and program (0x51) use bit 0 the same way, so bit 1 is specifically the
    READ-busy indicator.
  * log 82 `FUN_00003740`: the IN responder writes resp[0] = query & 0x7f, so
    0x8f -> 0x0f and 0xaa -> 0x2a. For the 0x0f status it returns
    resp[1] = state+0x38 (bit 1 READ busy, bit 0 erase/program busy,
    bit 7 unlocked) and resp[2] = state+0x35 (error: 1 address out of range,
    2 not unlocked, 3 bad length).
  * log 82 `FUN_00003740` param 0x2a: the payload is memcpy'd starting at
    resp[1] for the previously set length, so response[1:1+length] skips the
    0x2a response code. This is a protocol field, not a hidraw report-ID prefix.
  * log 89: commands are written on FF01/OUT channel 0/EP6 while responses are
    read on the distinct FF00/IN channel 1/EP5. The first live 0x8f query timed
    out because the earlier probe incorrectly waited for its reply on FF01.

  * log 85 `FUN_00003a7c` / `FUN_00002db8` / SysTick handler 0x000048d0: the
    post-EXEC scheduling race is **proven possible**. The 0x1f parser (USB
    interrupt) only sets the pending byte state+0x34 and the request flag at
    0x18010bd8. The READ itself runs from FUN_00002db8, reached only through
    FUN_00003a7c, whose loop body is gated on the *SysTick* flag at 0x18010bd4
    (`b 0x00003aa8` at 0x00003a7e jumps straight to `ldr r0,[r0,#0x0]; cmp
    r0,#0x0; bne`). The only writer of that word is the SysTick handler at
    0x000048d0. So an accepted EXEC waits for the next SysTick tick before the
    READ starts. Neither the tick period nor the flash-transfer duration is
    recoverable statically (FUN_00004910 selects the core clock at runtime), so
    no claim is made about how often the race is hit -- only that it is possible.
    Consequences:
      - polling state+0x38 bit 1 cannot sequence a READ: bit 1 clear is also what
        "not started yet" looks like, so the poll can exit immediately;
      - state+0x34 is not exposed by any query, and reading it via a 0xaa
        over-read needs a set-length above 0x30, which either misaligns the flash
        engine or corrupts state+0x36 into the responder's unclamped memcpy
        length -- both rejected (log 85 section 5).
  * log 86: FUN_00003b64 does **not** mask interrupts, so the 0xaa responder can
    observe state+4 while the flash transfer is only partly done. A status query
    taken *before* the fetch does not exclude that: an entire READ can start and
    finish between two status queries with the fetch landing inside it. The fix
    is an ordering one -- fetch, THEN status, then one confirming fetch. See
    read_fresh() for the interleaving proof.
  * log 86: the bootloader's ARM Region$$Table entry at 0x0000ccc0 zero-initialises
    0x18011168..0x1802b230 with __scatterload_zeroinit (fn 0x000001fc, reached from
    the reset vector via __scatterload at 0x00000148). That range covers the whole
    state block, so immediately after startup state+0x34 == 0 (no pending
    operation), state+4 == 48 zero bytes (a *known* baseline), state+0x36 == 0 and
    state+0x38 == 0 (locked, not busy). This is what makes the first baseline
    trustworthy instead of merely observed.

UNRESOLVED (why --run stays gated)
  * Log 90 validates Linux report framing, FF01 command routing, FF00 response
    routing, status, volatile length, and the zero-buffer bootstrap. It did not
    set an address or execute a flash READ.
  * No execute-READ has been sent and no installed-firmware backup exists.
  * OPERATIONAL PRECONDITION, not provable from the protocol: no other process
    may send reports to either hidraw node during the dump. A foreign pending
    READ is invisible (state+0x34 is not exposed), and one that completes between
    this tool's bootstrap fetch and its first set-address would publish an
    unrelated address's bytes. The bootstrap refuses unless state+4 reads as the
    48 zero bytes the startup left, which catches a foreign READ that has already
    *completed*, but not one still pending.
  * The freshness handshake is inconclusive when a chunk's content equals the
    previously proven buffer; it then re-bases through an anchor chunk of proven,
    different content, and aborts if no such anchor exists yet.

Usage:
    python3 tool/backup_firmware.py                    # dry-run, no device
    python3 tool/backup_firmware.py --run OUT --force-unreviewed
"""
import argparse
import hashlib
import os
import select
import struct
import sys
import tempfile
import time

VID = 0x0B05
PID_BOOT = 0x1B7F          # bootloader mode
PID_APP = 0x1B7E           # application mode (never addressed by this tool)
REPORT_LEN = 64
COMMAND_USAGE_PAGE = 0xFF01
RESPONSE_USAGE_PAGE = 0xFF00
# Compatibility/default: callers selecting the command/OUT channel continue to
# get FF01 unless they explicitly request the response/IN channel.
USAGE_PAGE = COMMAND_USAGE_PAGE

REGION_LO = 0x10000                       # app region base
REGION_SIZE = 0x6C000                     # app region size
REGION_HI = REGION_LO + REGION_SIZE       # 0x7c000
CHUNK_MAX = 0x30                          # bootloader read-length cap

# OUT sub-commands (report[0]); log 82 FUN_0000380c.
SET_ADDR, SET_LEN, EXEC = 0x20, 0x21, 0x1F
# IN queries; the responder echoes the low 7 bits as resp[0] (log 82).
Q_STATUS, Q_READDATA = 0x8F, 0xAA
R_STATUS, R_READDATA = Q_STATUS & 0x7F, Q_READDATA & 0x7F     # 0x0f, 0x2a
OP_READ = 0x05

# Status report layout: resp[1] = state+0x38, resp[2] = state+0x35 (log 82).
STATUS_FLAGS, STATUS_ERROR = 1, 2
BUSY_READ = 0x02           # log 81: bit 1 is held across the synchronous READ
BUSY_WRITE = 0x01          # bit 0 is erase/program; this tool never sets it
UNLOCK_BIT = 0x80
STATUS_ERRORS = {1: "address out of range", 2: "not unlocked", 3: "bad length"}

RESP_TIMEOUT = 2.0         # seconds to wait for one response report
FRESH_ATTEMPTS = 64        # bounded buffer-change polls per read
POLL_INTERVAL = 0.002
ANCHOR_KEEP = 2            # distinct proven chunks kept for re-basing

ALLOWED_OUT = {SET_ADDR, SET_LEN, EXEC}
ALLOWED_QUERY = {Q_STATUS, Q_READDATA}
# Never emittable. Listed so the intent is explicit and testable.
FORBIDDEN = {0x10, 0x22, 0x11, 0x01, 0x51}

SYSFS_HIDRAW = "/sys/class/hidraw"


class UnsafeReport(Exception):
    """An outgoing report failed the read-only allowlist."""


class ProtocolError(Exception):
    """The device response was absent, short, mis-coded, errored, or stayed busy."""


class SelectionError(Exception):
    """Could not identify the required validated bootloader hidraw node(s)."""


class ValidationError(Exception):
    """A completed dump failed to re-parse as a correct app-region image."""


# ---------------------------------------------------------------------------
# outgoing allowlist
# ---------------------------------------------------------------------------
def guard(sub, payload=b""):
    """Raise unless (sub, payload) is a pure read/query. Every outgoing report
    passes through here at build time and again just before write()."""
    if sub in FORBIDDEN:
        raise UnsafeReport(f"sub-command 0x{sub:02x} is a write/unlock/reset command")
    if sub not in ALLOWED_OUT and sub not in ALLOWED_QUERY:
        raise UnsafeReport(f"sub-command 0x{sub:02x} is not on the read-only allowlist")
    payload = bytes(payload)
    if sub == EXEC:
        if payload != bytes([OP_READ]):
            raise UnsafeReport("execute payload must be exactly READ(0x05), got "
                               f"{payload.hex() or '<empty>'}")
    elif sub == SET_ADDR:
        if len(payload) != 4:
            raise UnsafeReport("set-address payload must be 4 bytes")
        addr = struct.unpack("<I", payload)[0]
        if not REGION_LO <= addr < REGION_HI:
            raise UnsafeReport(f"address 0x{addr:x} outside the readable app region")
    elif sub == SET_LEN:
        if len(payload) != 2:
            raise UnsafeReport("set-length payload must be 2 bytes")
        length = struct.unpack("<H", payload)[0]
        if not 0 < length <= CHUNK_MAX:
            raise UnsafeReport(f"length 0x{length:x} outside 1..0x{CHUNK_MAX:x}")
    elif payload:
        raise UnsafeReport(f"query 0x{sub:02x} takes no payload")


def build_report(sub, payload=b""):
    guard(sub, payload)
    body = bytes([sub]) + bytes(payload)
    if len(body) > REPORT_LEN:
        raise UnsafeReport("report too long")
    return body + b"\x00" * (REPORT_LEN - len(body))


def chunk_exchange(addr, length):
    """The exact (label, sub, payload) sequence for one chunk, in order."""
    if not (REGION_LO <= addr and addr + length <= REGION_HI):
        raise UnsafeReport(f"address 0x{addr:x}+0x{length:x} outside readable region")
    if not (0 < length <= CHUNK_MAX):
        raise UnsafeReport(f"length 0x{length:x} out of range")
    # Length before address: after the set-address report, both fields hold the
    # values this chunk intends, so every later dispatch reads exactly (addr,
    # length). Data query before status query: see read_fresh().
    return [
        ("set_len", SET_LEN, struct.pack("<H", length)),
        ("set_addr", SET_ADDR, struct.pack("<I", addr)),
        ("exec_read", EXEC, bytes([OP_READ])),
        ("query_data", Q_READDATA, b""),
        ("query_status", Q_STATUS, b""),
    ]


def read_chunk_reports(addr, length):
    """The same sequence rendered as finished 64-byte reports (display/tests)."""
    return [(label, build_report(sub, payload))
            for label, sub, payload in chunk_exchange(addr, length)]


def dump_plan(lo=REGION_LO, hi=REGION_HI, chunk=CHUNK_MAX):
    for addr in range(lo, hi, chunk):
        yield addr, min(chunk, hi - addr)


# ---------------------------------------------------------------------------
# HID report-descriptor validation and node selection
# ---------------------------------------------------------------------------
def descriptor_facts(desc):
    """Parse a HID report descriptor into (usage_pages, ins, outs, has_report_id).

    `ins`/`outs` hold (usage_page, size_in_bytes) per Input/Output main item.
    """
    pos, page, size, count = 0, None, 0, 0
    pages, ins, outs, has_report_id = set(), [], [], False
    while pos < len(desc):
        prefix = desc[pos]
        pos += 1
        if prefix == 0xFE:                                   # long item
            if pos >= len(desc):
                raise ValueError("truncated long item")
            pos += 2 + desc[pos]
            if pos > len(desc):
                raise ValueError("truncated long item body")
            continue
        n = prefix & 0x03
        if n == 3:
            n = 4
        if pos + n > len(desc):
            raise ValueError("truncated short item")
        value = int.from_bytes(desc[pos:pos + n], "little") if n else 0
        pos += n
        tag = prefix & 0xFC
        if tag == 0x04:                                      # Usage Page
            page = value
            pages.add(value)
        elif tag == 0x74:                                    # Report Size
            size = value
        elif tag == 0x94:                                    # Report Count
            count = value
        elif tag == 0x84:                                    # Report ID
            has_report_id = True
        elif tag == 0x80:                                    # Input
            ins.append((page, size * count // 8))
        elif tag == 0x90:                                    # Output
            outs.append((page, size * count // 8))
    return pages, ins, outs, has_report_id


def descriptor_reasons(desc, usage_page=USAGE_PAGE):
    """Return [] if this is the requested 64-byte unnumbered vendor
    collection, else the list of mismatch reasons."""
    pages, ins, outs, has_report_id = descriptor_facts(desc)
    reasons = []
    if usage_page not in pages:
        found = ", ".join(f"0x{p:04x}" for p in sorted(pages)) or "none"
        reasons.append(f"usage page 0x{usage_page:04x} absent (found {found})")
    if not any(p == usage_page and n == REPORT_LEN for p, n in ins):
        reasons.append(f"no {REPORT_LEN}-byte IN report on page 0x{usage_page:04x}")
    if not any(p == usage_page and n == REPORT_LEN for p, n in outs):
        reasons.append(f"no {REPORT_LEN}-byte OUT report on page 0x{usage_page:04x}")
    if has_report_id:
        reasons.append("descriptor declares a report ID (expected unnumbered reports)")
    return reasons


def _hid_id(uevent):
    """Extract (vid, pid) from a hidraw uevent HID_ID=0003:0000XXXX:0000YYYY."""
    for line in uevent.splitlines():
        if line.startswith("HID_ID="):
            parts = line.split(":")
            if len(parts) != 3:
                return None
            try:
                return int(parts[1], 16) & 0xFFFF, int(parts[2], 16) & 0xFFFF
            except ValueError:
                return None
    return None


def select_bootloader_node(sysfs_root=SYSFS_HIDRAW, dev_root="/dev",
                           usage_page=USAGE_PAGE):
    """Return (node, rejected, app_nodes) for the single hidraw whose PID is
    1b7f AND whose report descriptor matches. Raises SelectionError on none,
    several, or descriptor mismatch.

    A PID match alone is never sufficient: the device exposes several HID
    interfaces. The protocol command and response paths use distinct pages, so
    callers must explicitly select the page required for their direction.
    """
    matched, rejected, app_nodes = [], [], []
    try:
        names = sorted(os.listdir(sysfs_root))
    except OSError as exc:
        raise SelectionError(f"cannot enumerate {sysfs_root}: {exc}") from exc
    for name in names:
        base = os.path.join(sysfs_root, name, "device")
        try:
            with open(os.path.join(base, "uevent")) as fh:
                ids = _hid_id(fh.read())
        except OSError:
            continue
        if ids is None or ids[0] != VID:
            continue
        if ids[1] == PID_APP:
            app_nodes.append(name)
            continue
        if ids[1] != PID_BOOT:
            continue
        try:
            with open(os.path.join(base, "report_descriptor"), "rb") as fh:
                desc = fh.read()
        except OSError as exc:
            rejected.append(f"{name}: report descriptor unreadable ({exc})")
            continue
        try:
            reasons = descriptor_reasons(desc, usage_page=usage_page)
        except ValueError as exc:
            rejected.append(f"{name}: malformed report descriptor ({exc})")
            continue
        if reasons:
            rejected.append(f"{name}: " + "; ".join(reasons))
        else:
            matched.append(os.path.join(dev_root, name))

    if len(matched) == 1:
        return matched[0], rejected, app_nodes
    detail = [f"  rejected {r}" for r in rejected]
    if app_nodes:
        detail.append("  application-mode (1b7e) nodes present: " + ", ".join(app_nodes)
                      + " — this tool never sends bootloader commands to the application")
    if not matched:
        raise SelectionError("\n".join(
            [f"no validated PID-{PID_BOOT:04x} vendor node (usage page "
             f"0x{usage_page:04x}, {REPORT_LEN}-byte IN+OUT, no report ID)"] + detail))
    raise SelectionError("\n".join(
        [f"{len(matched)} validated PID-{PID_BOOT:04x} nodes ({', '.join(matched)}); "
         "refusing to guess which one to read"] + detail))


def select_bootloader_channels():
    """Select the distinct FF01 command and FF00 response hidraw nodes."""
    command_node, command_rejected, command_apps = select_bootloader_node(
        usage_page=COMMAND_USAGE_PAGE)
    response_node, response_rejected, response_apps = select_bootloader_node(
        usage_page=RESPONSE_USAGE_PAGE)
    if command_node == response_node:
        raise SelectionError(
            "FF01 command and FF00 response selectors returned one node")
    app_nodes = sorted(set(command_apps + response_apps))
    return (command_node, response_node, command_rejected,
            response_rejected, app_nodes)


# ---------------------------------------------------------------------------
# transport (only reached via --run)
# ---------------------------------------------------------------------------
class HidrawTransport:
    """Raw hidraw, no external dependencies.

    write(): Linux hidraw takes a leading report-number byte, 0 for devices with
    unnumbered reports (which the descriptor check enforced).
    read(): returns report data with no report-number prefix, so resp[0] is the
    bootloader's own response code. Neither convention has been exercised
    against this device.
    """

    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)

    def write(self, report):
        written = os.write(self.fd, b"\x00" + report)
        if written != len(report) + 1:
            raise ProtocolError(f"short write: {written} of {len(report) + 1} bytes")

    def read(self, timeout):
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            raise ProtocolError(f"no response report within {timeout:g}s")
        return os.read(self.fd, REPORT_LEN)

    def close(self):
        os.close(self.fd)


class SplitHidrawTransport:
    """Write only to FF01 and read only from FF00.

    Open the response side first so its input queue exists before a command can
    be sent. The access modes prevent writes to FF00 and reads from FF01.
    """

    def __init__(self, command_path, response_path):
        if command_path == response_path:
            raise SelectionError("command and response hidraw nodes must differ")
        self.command_path = command_path
        self.response_path = response_path
        self.read_fd = os.open(response_path, os.O_RDONLY)
        try:
            self.write_fd = os.open(command_path, os.O_WRONLY)
        except BaseException:
            os.close(self.read_fd)
            raise

    def write(self, report):
        written = os.write(self.write_fd, b"\x00" + report)
        if written != len(report) + 1:
            raise ProtocolError(
                f"short write: {written} of {len(report) + 1} bytes")

    def read(self, timeout):
        ready, _, _ = select.select([self.read_fd], [], [], timeout)
        if not ready:
            raise ProtocolError(f"no response report within {timeout:g}s")
        return os.read(self.read_fd, REPORT_LEN)

    def close(self):
        errors = []
        for name in ("write_fd", "read_fd"):
            fd = getattr(self, name, None)
            if fd is None:
                continue
            try:
                os.close(fd)
            except OSError as exc:
                errors.append(exc)
            setattr(self, name, None)
        if errors:
            raise errors[0]


def send(transport, sub, payload=b""):
    """Build, re-guard, and write exactly one report."""
    report = build_report(sub, payload)
    guard(sub, payload)                     # re-guard the exact bytes being sent
    transport.write(report)


def read_response(transport, expect_code, timeout=RESP_TIMEOUT):
    """Read exactly one full-length report and validate its response code."""
    resp = bytes(transport.read(timeout))
    if len(resp) != REPORT_LEN:
        raise ProtocolError(f"short response: {len(resp)} of {REPORT_LEN} bytes")
    if resp[0] != expect_code:
        raise ProtocolError(
            f"wrong response code 0x{resp[0]:02x}, expected 0x{expect_code:02x}")
    return resp


def query(transport, sub, expect_code, timeout=RESP_TIMEOUT):
    """One immediate request-response exchange: send, then read its reply.

    Queries are never batched. Sending 0x8f and 0xaa back to back and then
    reading once would consume the status report as if it were read data.
    """
    send(transport, sub)
    return read_response(transport, expect_code, timeout)


def check_status(transport):
    """One 0x8f exchange, validated. Returns resp[1] = state+0x38.

    Verified use (log 85 section H): resp[2] = state+0x35 is written by the same
    OUT parser, in the same interrupt, that consumed the EXEC report -- at
    0x00003984 (address out of range) and 0x00003964 (bad length) for a READ, and
    0x00003938/0x000039ea (not unlocked) for erase/program. A rejected EXEC is
    therefore reported reliably here.

    Verified NON-use: resp[1] bit 1 is *not* a completion signal. The READ runs
    on a SysTick tick, so a clear bit 1 is also exactly what "not started yet"
    looks like -- no timing claim is needed or made. Its only role is to place a
    sample outside the interval in which FUN_00003b64 can be writing, and it does
    that only when read AFTER the sample; see read_fresh().
    """
    resp = query(transport, Q_STATUS, R_STATUS)
    error = resp[STATUS_ERROR]
    if error:
        raise ProtocolError(f"bootloader status error 0x{error:02x} "
                            f"({STATUS_ERRORS.get(error, 'unknown')})")
    flags = resp[STATUS_FLAGS]
    if flags & UNLOCK_BIT:
        raise ProtocolError(
            "state+0x38 bit 7 is set: erase/program is unlocked on this device. "
            "Refusing to continue a read-only dump against an unlocked bootloader")
    if flags & BUSY_WRITE:
        raise ProtocolError("state+0x38 bit 0 is set: an erase or program is in "
                            "progress. Refusing to continue")
    return flags


def fetch(transport, length):
    """One 0xaa exchange. Returns the responder's `length` payload bytes.

    The bytes are the current contents of the response buffer at state+4
    (log 85: FUN_00003740 sub-command 0x2a copies state+4 for state+0x36 bytes,
    and FUN_00003b64 writes its READ result to that same address). They are NOT
    known to belong to the last address requested; `read_fresh()` is what
    establishes that.
    """
    resp = query(transport, Q_READDATA, R_READDATA)
    payload = resp[1:1 + length]              # skip the 0x2a response code
    if len(payload) != length:
        raise ProtocolError(f"data response carried {len(payload)} of {length} bytes")
    return payload


def exec_read(transport, addr, length):
    """Queue one READ. Says nothing about the buffer (log 85).

    Length first, then address: after the set-address report both fields hold
    this chunk's values, so every dispatch from that point on reads exactly
    (addr, length). FUN_00003b64 samples both at dispatch time, not at EXEC time.
    """
    send(transport, SET_LEN, struct.pack("<H", length))
    send(transport, SET_ADDR, struct.pack("<I", addr))
    send(transport, EXEC, bytes([OP_READ]))


def read_fresh(transport, addr, length, baseline, attempts=FRESH_ATTEMPTS):
    """Return content(addr), proven complete and fresh, or None if undecidable.

    `baseline` is the value state+4 is *known* to hold before this call: the 48
    zero bytes the startup zero-init left (log 86) for the first chunk, and the
    previous chunk's proven bytes afterwards.

    THE RULE: fetch, then status, then -- only if the status says not-busy and
    the fetched sample differs from the baseline -- one more fetch, and return
    that second fetch. The order matters and the earlier implementation had it
    backwards; see the counterexample in log 86.

    INTERLEAVING PROOF.
      Facts (log 85 sections 2-3, log 86):
        F1 state+4 is written only by FUN_00003b64; the host has no write path
           into it (OUT 0x22's last reachable byte is state+3).
        F2 FUN_00003b64 is called only from FUN_00002db8, strictly between the
           store that sets state+0x38 bit 1 (0x00002e0a) and the store that
           clears it (0x00002e1e). So every write to state+4 happens at a time
           when bit 1 reads set.
        F3 FUN_00003b64 takes its address from *(u32 *)(state-0x1000) and its
           length from *(u16 *)(state+0x36) when it runs, not when the EXEC was
           parsed.
        F4 FUN_00002db8 runs only from the single-threaded main loop
           FUN_00003a7c, so READ episodes are serialised and non-overlapping.
        F5 FUN_00003740, which answers 0x8f and 0xaa, writes neither state+4,
           state+0x34, nor the service-loop flags.
      Call an *episode* one execution of FUN_00003b64 from the cmd-5 branch, and
      let E_i = [s_i, e_i] be the interval over which it holds bit 1 set. By F4
      the E_i are disjoint and ordered; by F1/F2 state+4 is constant outside
      their union.
      Let t2 be the time of this call's set-address report. Every episode that
      dispatches at or after t2 writes content(addr) (F3, and the host changes
      neither field again until the next chunk's set-address). Every episode that
      dispatches before t2 writes the *previous* chunk's address, whose content
      is exactly `baseline` -- writing bytes that are already there cannot change
      the value. So, with E* the first episode dispatching at or after t2:
          state+4 == baseline            for t < s*
          state+4 == content(addr)       for t > e*
          state+4 == content(addr)       throughout every later episode, because
                                         they store the same bytes again.
      Now suppose the host samples X at t_f and then reads a status with bit 1
      clear at t_s > t_f. Bit 1 clear means t_s lies in no E_i (F2).
        - If t_s < s*, then t_f < s* too, so X == baseline.
        - Otherwise t_s > e*, so state+4 == content(addr) at t_s and at every
          later instant.
      Therefore X != baseline forces t_s > e*, and any fetch issued after t_s
      returns the complete content(addr). That is the second fetch. No timing
      assumption and no unexposed state is used. QED
      Corollary: if content(addr) == baseline then every state during E* equals
      baseline, so X == baseline; hence X != baseline also implies the confirmed
      value differs from the baseline. The check below is therefore a free
      consistency test on the whole model, and firing it means the model is wrong.

    Returns None if the sample never differs within `attempts`: either the READ
    has not dispatched, or content(addr) == baseline. The caller re-bases and
    retries rather than guess.

    Re-arming: the EXEC is re-sent while the sample still equals the baseline,
    because the 0x1f parser drops an EXEC while state+0x34 is non-zero (`bne` at
    0x000038de before any store), so the first one may have been swallowed by an
    older pending operation. A re-arm that is accepted only re-reads the same
    address with the same length, so by the argument above it cannot change
    state+4's value, and a re-arm still pending when this returns is covered by
    the next chunk's E* definition.

    Re-arming STOPS as soon as a sample differs from the baseline. At that point
    an episode with this address has provably already begun writing, so no
    further EXEC is needed for progress; continuing to re-arm would keep starting
    fresh episodes and could starve the busy-clear observation the rule needs
    (a lock-step between the host's round and the dispatch cadence). Stopping
    bounds the number of episodes, so bit 1 is eventually clear for good.
    """
    if len(baseline) != length:
        raise ProtocolError(f"baseline is {len(baseline)} bytes, need {length}; "
                            "the freshness handshake needs a same-length baseline")
    exec_read(transport, addr, length)
    for _ in range(attempts):
        sample = fetch(transport, length)          # X -- may be a partial buffer
        flags = check_status(transport)            # t_s -- strictly after X
        moved = sample != baseline
        if moved and not flags & BUSY_READ:
            confirmed = fetch(transport, length)   # provably complete
            if confirmed == baseline:
                raise ProtocolError(
                    f"chunk 0x{addr:x}: the confirming fetch returned the baseline "
                    "after a differing sample. The recovered model of the response "
                    "buffer is wrong; refusing to guess")
            return confirmed
        time.sleep(POLL_INTERVAL)
        if not moved:
            send(transport, EXEC, bytes([OP_READ]))  # re-arm, same addr and length
    return None


def read_chunk(transport, addr, length, baseline, anchors=()):
    """Return bytes proven to be the flash contents at `addr`.

    On an undecidable handshake the buffer is driven to an anchor chunk of
    already-proven, different content, and the target is retried. One usable
    anchor is enough: content(addr) cannot equal both the baseline and the
    anchor, because those two differ.
    """
    current = baseline                        # what state+4 is known to hold
    value = read_fresh(transport, addr, length, current)
    if value is not None:
        return value
    for anchor_addr, anchor_data in anchors:
        if anchor_data == current or len(anchor_data) != length:
            continue                          # cannot re-base onto the baseline
        moved = read_fresh(transport, anchor_addr, length, current)
        if moved != anchor_data:
            raise ProtocolError(
                f"re-base read of 0x{anchor_addr:x} returned "
                f"{'nothing new' if moved is None else 'different bytes'} than "
                "the value already proven for that address")
        current = anchor_data
        value = read_fresh(transport, addr, length, current)
        if value is not None:
            return value
    raise ProtocolError(
        f"chunk 0x{addr:x}: the response buffer never changed, so a fresh read "
        "cannot be told apart from a stale one, and no anchor chunk of different "
        "proven content was available to re-base through (log 85 post-EXEC "
        "scheduling race)")


def bootstrap_baseline(transport, length):
    """Establish the first known value of state+4, or refuse.

    log 86: the reset path's Region$$Table entry at 0x0000ccc0 zero-initialises
    0x18011168..0x1802b230 through __scatterload_zeroinit, and that range covers
    state+4, state+0x34, state+0x36 and state+0x38. So a bootloader that has just
    started, and to which nothing has yet been said, has an all-zero response
    buffer and no pending operation.

    Requiring the all-zero read is therefore a real check, not a formality: it
    fails if a READ has already completed in this bootloader session, which is
    exactly the situation in which the first baseline could not be trusted. It
    does NOT detect a foreign READ that is queued but has not dispatched --
    state+0x34 is exposed by no query. That residue is covered only by the
    operational precondition in the module docstring.
    """
    send(transport, SET_LEN, struct.pack("<H", length))
    check_status(transport)
    residue = fetch(transport, length)
    if residue != bytes(length):
        raise ProtocolError(
            f"bootstrap: state+4 read {residue.hex()} but a freshly started "
            f"bootloader must read {length} zero bytes (log 86 Region$$Table "
            "zero-init). Something has already driven a READ in this bootloader "
            "session, so the first baseline cannot be trusted. Power-cycle the "
            "keyboard, re-enter bootloader mode, and make sure nothing else is "
            "talking to either bootloader hidraw node")
    return residue


def dump_once(transport, plan=None, baseline=None):
    """One full pass. Returns (image, final_baseline).

    `baseline` is the value state+4 is known to hold on entry. Pass None for the
    first pass on a freshly started bootloader; pass the previous pass's returned
    baseline for later passes, because the bootstrap's all-zero check can only be
    true before any READ has run.
    """
    plan = list(dump_plan() if plan is None else plan)
    if not plan:
        raise ProtocolError("empty dump plan")
    lengths = {length for _addr, length in plan}
    if len(lengths) != 1:
        raise ProtocolError(f"plan has mixed chunk lengths {sorted(lengths)}; the "
                            "freshness handshake compares same-length buffers")
    length = lengths.pop()
    if baseline is None:
        baseline = bootstrap_baseline(transport, length)
    elif len(baseline) != length:
        raise ProtocolError(f"carried baseline is {len(baseline)} bytes, need {length}")

    image, anchors = bytearray(), []
    for addr, chunk_len in plan:
        data = read_chunk(transport, addr, chunk_len, baseline, anchors)
        image += data
        baseline = data
        if len(anchors) < ANCHOR_KEEP and all(d != data for _a, d in anchors):
            anchors.append((addr, data))
    return bytes(image), baseline


def _close_quietly(transport):
    """Close without letting a close error mask the original protocol failure."""
    try:
        transport.close()
    except OSError as exc:                    # pragma: no cover - device-specific
        print(f"  note: closing the transport failed ({exc}); "
              "the result above is unaffected")


def validate_dump(image):
    """Re-parse a completed dump in memory and return its check report.

    Raises ValidationError unless the image is exactly the app region and every
    check that region can support passes. This is what catches a deterministic
    stale or shifted read that was nonetheless identical across all passes.
    """
    if len(image) != REGION_SIZE:
        raise ValidationError(
            f"dump is 0x{len(image):x} bytes, expected exactly 0x{REGION_SIZE:x}")
    try:
        import analyze_boot_structures as boot
        import analyze_candidate_integrity as integrity
    except ImportError as exc:
        raise ValidationError(f"cannot import the offline analyzers: {exc}") from exc

    lines, failures = [], []
    try:
        _records, word_sums, checks = integrity.analyze(image, REGION_LO)
        present, skipped, _recs, boot_checks = boot.known_boot_checks(image, REGION_LO)
    except (ValueError, struct.error, IndexError) as exc:
        raise ValidationError(f"dump does not parse as the app region: {exc}") from exc

    for name, result in word_sums.items():
        if result is None:
            lines.append(f"  SKIP {name} word-sum (below 0x{REGION_LO:x}, "
                         "not readable over USB)")
    for name in skipped:
        lines.append(f"  SKIP {name} container (below 0x{REGION_LO:x}, "
                     "not readable over USB)")
    for name, ok in list(checks.items()) + [(f"boot: {k}", v)
                                            for k, v in boot_checks.items()]:
        lines.append(f"  {'PASS' if ok else 'FAIL'} {name}")
        if not ok:
            failures.append(name)
    if not present:
        failures.append("no boot container present in the dump")
    if failures:
        raise ValidationError("failed checks: " + ", ".join(failures) + "\n"
                              + "\n".join(lines))
    return lines


def _publish(image, out_path):
    """Write via an exclusive temp file in the destination directory, fsync, and
    publish with os.link so an existing output is never overwritten and no
    partial file is ever left behind under our own name."""
    directory = os.path.dirname(os.path.abspath(out_path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".backup_firmware-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(image)
            fh.flush()
            os.fsync(fh.fileno())
        os.link(tmp, out_path)                # atomic, fails if out_path exists
    finally:
        try:
            os.unlink(tmp)                    # only ever our own temp
        except OSError:                       # pragma: no cover
            pass


def run_backup(out_path, passes=3, open_transport=None,
               select_node=None, plan=None,
               validate=validate_dump):
    """Dump `passes` times, require byte- and SHA-256-identical results, re-parse
    the result, and publish only if every stage succeeded."""
    if passes < 3:
        print(f"REFUSING: at least 3 passes are required, got {passes}.")
        return 2
    if os.path.exists(out_path):
        print(f"REFUSING: {out_path} already exists; refusing to overwrite a backup.")
        return 2
    # Production always selects and opens distinct command/response nodes.
    # The three-item form remains only as a dependency-injection seam for the
    # offline fake-device tests; it cannot be reached from the CLI defaults.
    injected_single_node = select_node is not None
    selector = select_node if injected_single_node else select_bootloader_channels
    transport_factory = open_transport
    if transport_factory is None:
        transport_factory = SplitHidrawTransport
    try:
        selected = tuple(selector())
    except SelectionError as exc:
        print(f"REFUSING: {exc}")
        return 2
    if len(selected) == 5:
        command_node, response_node, command_rejected, response_rejected, app_nodes = selected
        print(f"Bootloader command HID device (FF01): {command_node}")
        print(f"Bootloader response HID device (FF00): {response_node}")
        for note in command_rejected:
            print(f"  note: command selector skipped {note}")
        for note in response_rejected:
            print(f"  note: response selector skipped {note}")
    elif len(selected) == 3 and injected_single_node:
        # Offline tests use an in-memory full-duplex transport with no hidraw.
        command_node, rejected, app_nodes = selected
        response_node = None
        for note in rejected:
            print(f"  note: skipped {note}")
    else:
        print("REFUSING: selector returned an unsupported channel layout")
        return 2
    for name in app_nodes:
        print(f"  note: application-mode node {name} ignored")
    print(f"REGION app-only base=0x{REGION_LO:x} size=0x{REGION_SIZE:x} "
          f"(bootloader [0x0,0x{REGION_LO:x}) is not readable and is not included)")

    # All passes share one handle. The freshness proof is stateful: the bootstrap
    # all-zero check is only true before any READ has run in this bootloader
    # session, so later passes must carry the previous pass's proven baseline
    # rather than re-bootstrap.
    try:
        if response_node is None:
            transport = transport_factory(command_node)
        else:
            transport = transport_factory(command_node, response_node)
    except OSError as exc:
        target = (command_node if response_node is None else
                  f"{command_node} and {response_node}")
        print(f"REFUSING: cannot open {target}: {exc}")
        print("Nothing was written.")
        return 2
    images, digests, baseline = [], [], None
    try:
        for index in range(passes):
            try:
                image, baseline = dump_once(transport, plan, baseline)
            except (ProtocolError, UnsafeReport, OSError) as exc:
                print(f"ABORT on pass {index + 1}/{passes}: {exc}")
                print("No dump was accepted and nothing was written.")
                return 1
            digest = hashlib.sha256(image).hexdigest()
            images.append(image)
            digests.append(digest)
            print(f"pass {index + 1}/{passes}: 0x{len(image):x} bytes sha256={digest}")
    finally:
        _close_quietly(transport)

    if any(img != images[0] for img in images[1:]) or len(set(digests)) != 1:
        print("MISMATCH between passes (bytes and/or SHA-256) — do NOT trust this dump.")
        print("Nothing was written.")
        return 1

    if validate is not None:
        try:
            for line in validate(images[0]):
                print(line)
        except ValidationError as exc:
            print(f"REJECTED: the dump did not self-validate.\n{exc}")
            print("All passes are rejected and nothing was written. Identical "
                  "passes only prove the reads were repeatable, not correct.")
            return 1
        print("self-validation: PASS (dump re-parses as the app region)")

    try:
        _publish(images[0], out_path)
    except FileExistsError:
        print(f"REFUSING: {out_path} appeared during the dump; nothing was written.")
        return 2
    except OSError as exc:
        print(f"REFUSING: cannot write {out_path}: {exc}")
        print("No partial output was left behind.")
        return 2
    print(f"OK: {passes} identical passes; wrote {out_path}")
    print("Validate next (the dump starts at flash 0x10000, so --base is required):")
    print(f"  python3 tool/analyze_candidate_integrity.py {out_path} --base 0x{REGION_LO:x}")
    print(f"  python3 tool/analyze_boot_structures.py {out_path} --base 0x{REGION_LO:x}")
    return 0


# ---------------------------------------------------------------------------
# dry run
# ---------------------------------------------------------------------------
def _safety_selfcheck():
    """The guard must reject every write/unlock/reset construction."""
    must_fail = [
        (EXEC, bytes([0x01])),          # erase
        (EXEC, bytes([0x51])),          # program
        (EXEC, b""),                    # unspecified opcode
        (0x10, b"ASUSHIDFWU"),          # unlock
        (0x22, b"\x04\x00\x00data"),    # load data
        (0x11, b""),                    # reset
        (SET_ADDR, struct.pack("<I", 0x0)),        # bootloader region
        (SET_ADDR, struct.pack("<I", REGION_HI)),  # past the app region
        (SET_LEN, struct.pack("<H", CHUNK_MAX + 1)),
        (SET_LEN, struct.pack("<H", 0)),
    ]
    for sub, payload in must_fail:
        try:
            build_report(sub, payload)
        except UnsafeReport:
            continue
        raise AssertionError(f"SAFETY FAILURE: built forbidden report 0x{sub:02x}")
    for sub, payload in [(SET_ADDR, struct.pack("<I", REGION_LO)),
                         (SET_LEN, struct.pack("<H", CHUNK_MAX)),
                         (EXEC, bytes([OP_READ])), (Q_STATUS, b""), (Q_READDATA, b"")]:
        build_report(sub, payload)
    print("safety self-check: PASS "
          "(guard rejected every write/unlock/reset form; read reports built)")


def dry_run():
    print("PROGRAM backup_firmware  (DRY-RUN — no device opened)")
    plan = list(dump_plan())
    total = sum(n for _addr, n in plan)
    print(f"REGION app-only base=0x{REGION_LO:x} size=0x{REGION_SIZE:x} "
          f"range 0x{REGION_LO:x}..0x{REGION_HI:x}")
    print(f"chunks={len(plan)} chunk_max=0x{CHUNK_MAX:x} bytes=0x{total:x}")
    assert total == REGION_SIZE, "plan does not cover the declared app region"
    count = 0
    for addr, length in plan:
        for _label, sub, payload in chunk_exchange(addr, length):
            guard(sub, payload)              # exactly what would be sent
            assert sub in ALLOWED_OUT | ALLOWED_QUERY
            count += 1
    print(f"validated {count} reports; all pass the read-only guard")
    print(f"sample chunk @0x{REGION_LO:x} len 0x{CHUNK_MAX:x}:")
    for label, report in read_chunk_reports(REGION_LO, CHUNK_MAX):
        print(f"  {label:12s} {report[:8].hex(' ')} ...")
    print(f"expected replies: status resp[0]=0x{R_STATUS:02x} "
          f"(resp[1]=state+0x38 flags, resp[2]=state+0x35 error), "
          f"data resp[0]=0x{R_READDATA:02x}")
    print(f"per-chunk freshness handshake: up to {FRESH_ATTEMPTS} rounds of "
          f"data-then-status; a round is accepted only when the status that "
          f"FOLLOWS the sample reports bit 0x{BUSY_READ:02x} clear and the sample "
          f"differs from the known baseline, and the value returned is then a "
          f"second, confirming data query; re-bases through up to {ANCHOR_KEEP} "
          "anchor chunks (proof in read_fresh, log 86)")
    print(f"state+0x38 bit 0x{BUSY_READ:02x} (READ busy) is never a completion "
          "signal; it is only read AFTER a sample, to place that sample outside "
          "the interval in which FUN_00003b64 can be writing (log 86)")
    print("bootstrap: state+4 must read 0x30 zero bytes before the first EXEC "
          "(log 86 Region$$Table zero-init at 0x0000ccc0); otherwise refuse")
    _safety_selfcheck()
    print("RESULT dry_run_ok=True guard_rejected_forbidden=True")
    print("LIMITATION No device was opened. The post-EXEC scheduling race is "
          "proven possible (log 85) and the corrected handshake (log 86) is "
          "proven to return only complete buffers. Log 90 live-validates the "
          "non-flash framing/bootstrap, but execute-READ and the sole-host "
          "operational precondition all remain unresolved, so --run stays gated "
          "behind --force-unreviewed. Live use is still unauthorised.")
    return 0


LIVE_REFUSAL = """REFUSING to run live.

Bootloader entry and the exact split-channel status/zero-buffer probe are
live-validated (log 90). No address or execute-READ has been sent.

Two protocol questions are now settled. The post-EXEC scheduling race is real
(log 85): the 0x1f parser only sets the pending byte state+0x34 and the request
flag at 0x18010bd8, while the READ runs from FUN_00002db8, reached only through
FUN_00003a7c, whose loop body is gated on the SysTick flag that only the handler
at 0x000048d0 writes. And the first version of the fix was wrong (log 86): it
read status *before* the data query, which does not exclude a READ that starts
and finishes between two status queries with the fetch landing inside it, so it
could accept a half-old/half-new buffer. The handshake now fetches, then reads
status, then re-fetches, which is proven to return only complete buffers; and the
first baseline is the all-zero state+4 the Region$$Table zero-init leaves, not a
guess.

What is still unresolved:

  1. Linux report framing, FF01 command routing, FF00 response routing, status,
     volatile length, and the zero-buffer bootstrap are validated. Flash READ
     behavior and the freshness handshake have not been exercised on hardware.
  2. No execute-READ has been sent and no installed-firmware backup exists, so
     there is nothing to restore from if a read path misbehaves.
  3. An operational precondition that the protocol cannot enforce: no other
     process may send reports to either hidraw node during the dump. A foreign READ
     that is queued but has not dispatched is invisible -- state+0x34 is exposed
     by no query -- and if it completes between the bootstrap fetch and the first
     set-address it would publish an unrelated address's bytes. The bootstrap
     catches a foreign READ that has already completed; it cannot catch a pending
     one.
  4. The handshake is undecidable when a chunk's content equals the previously
     proven buffer; it re-bases through an anchor chunk of proven, different
     content and aborts if none is available yet.

Live use is unauthorised pending independent review. If that review has happened
and you accept the risk, re-run with --force-unreviewed."""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Read-only app-region backup over the 1b7f bootloader.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", metavar="OUT",
                        help="perform the read-back into OUT (needs --force-unreviewed)")
    parser.add_argument("--force-unreviewed", action="store_true",
                        help="acknowledge the unvalidated hidraw transfer convention")
    parser.add_argument("--passes", type=int, default=3,
                        help="identical passes required before writing (minimum 3)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.run is None:
        return dry_run()
    if not args.force_unreviewed:
        print(LIVE_REFUSAL)
        return 2
    return run_backup(args.run, passes=args.passes)


if __name__ == "__main__":
    sys.exit(main())
