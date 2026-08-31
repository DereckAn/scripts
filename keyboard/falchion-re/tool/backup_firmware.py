#!/usr/bin/env python3
"""Read-only firmware backup tool for the ROG Falchion Ace HFX bootloader.

Reads the *application* flash region only: base 0x10000, size 0x6c000
(0x10000..0x7c000), while the device is in bootloader mode (PID 1b7f), over the
vendor-HID framing recovered statically in logs 81-82. The bootloader region
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

PROTOCOL EVIDENCE (all static; nothing here has been exercised on hardware)
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

UNRESOLVED (why --run stays gated)
  * **Post-EXEC scheduling race.** The OUT parser only records the pending
    command in state+0x34; the service loop (`FUN_00003a7c` -> `FUN_00002db8`)
    is what later sets state+0x38 bit 1 and performs the READ. Nothing recovered
    so far proves the service loop has run by the time the host's first 0x8f
    arrives. If the host queries status in that window, bit 1 reads clear, the
    poll exits immediately, and the subsequent 0xaa can return the *previous*
    chunk's buffer. Status does not expose state+0x34, so this tool cannot
    distinguish "READ finished" from "READ not started yet". No timing guarantee
    is claimed or assumed here.
    Mitigation, not a fix: every completed dump is re-parsed in memory by
    `validate_dump()` before anything is written, which rejects the shifted or
    stale images this race would produce. A race that happened to yield a
    self-consistent image would not be caught.
  * Linux hidraw write() takes a leading report-number byte (0 for unnumbered
    reports); read() returns report data with no such prefix. Both conventions
    are applied here but have never been exercised against this device.
  * No live validation of any kind has been performed and no installed-firmware
    backup exists.

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
USAGE_PAGE = 0xFF01

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
BUSY_ATTEMPTS = 64         # bounded status polls per chunk
POLL_INTERVAL = 0.002

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
    """Could not identify exactly one validated bootloader hidraw node."""


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
    return [
        ("set_addr", SET_ADDR, struct.pack("<I", addr)),
        ("set_len", SET_LEN, struct.pack("<H", length)),
        ("exec_read", EXEC, bytes([OP_READ])),
        ("query_status", Q_STATUS, b""),
        ("query_data", Q_READDATA, b""),
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


def descriptor_reasons(desc):
    """Return [] if this is the expected FF01 64-byte unnumbered vendor
    collection, else the list of mismatch reasons."""
    pages, ins, outs, has_report_id = descriptor_facts(desc)
    reasons = []
    if USAGE_PAGE not in pages:
        found = ", ".join(f"0x{p:04x}" for p in sorted(pages)) or "none"
        reasons.append(f"usage page 0x{USAGE_PAGE:04x} absent (found {found})")
    if not any(p == USAGE_PAGE and n == REPORT_LEN for p, n in ins):
        reasons.append(f"no {REPORT_LEN}-byte IN report on page 0x{USAGE_PAGE:04x}")
    if not any(p == USAGE_PAGE and n == REPORT_LEN for p, n in outs):
        reasons.append(f"no {REPORT_LEN}-byte OUT report on page 0x{USAGE_PAGE:04x}")
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


def select_bootloader_node(sysfs_root=SYSFS_HIDRAW, dev_root="/dev"):
    """Return (node, rejected, app_nodes) for the single hidraw whose PID is
    1b7f AND whose report descriptor matches. Raises SelectionError on none,
    several, or descriptor mismatch.

    A PID match alone is never sufficient: the device exposes several HID
    interfaces and only the FF01 64-byte unnumbered one speaks this protocol.
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
            reasons = descriptor_reasons(desc)
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
             f"0x{USAGE_PAGE:04x}, {REPORT_LEN}-byte IN+OUT, no report ID)"] + detail))
    raise SelectionError("\n".join(
        [f"{len(matched)} validated PID-{PID_BOOT:04x} nodes ({', '.join(matched)}); "
         "refusing to guess which one to read"] + detail))


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


def wait_read_done(transport, attempts=BUSY_ATTEMPTS):
    """Poll 0x8f until the READ-busy bit clears, within bounded attempts.

    Validates resp[0] == 0x0f and resp[2] (state+0x35 error) == 0 on every poll.

    Caveat: a clear bit 1 means "not currently reading", which is not the same as
    "the READ we just requested has finished". See the post-EXEC scheduling race
    in the module docstring — this loop cannot close that window, and the
    end-of-dump `validate_dump()` is what guards against its consequences.
    """
    for _ in range(attempts):
        resp = query(transport, Q_STATUS, R_STATUS)
        error = resp[STATUS_ERROR]
        if error:
            raise ProtocolError(f"bootloader status error 0x{error:02x} "
                                f"({STATUS_ERRORS.get(error, 'unknown')})")
        if not resp[STATUS_FLAGS] & BUSY_READ:
            return resp
        time.sleep(POLL_INTERVAL)
    raise ProtocolError(
        f"READ stayed busy (state+0x38 bit 1) after {attempts} status polls")


def read_chunk(transport, addr, length):
    """set-address -> set-length -> execute READ -> status poll -> data."""
    send(transport, SET_ADDR, struct.pack("<I", addr))
    send(transport, SET_LEN, struct.pack("<H", length))
    send(transport, EXEC, bytes([OP_READ]))
    wait_read_done(transport)
    resp = query(transport, Q_READDATA, R_READDATA)
    payload = resp[1:1 + length]            # skip the 0x2a response code
    if len(payload) != length:
        raise ProtocolError(f"data response carried {len(payload)} of {length} bytes")
    return payload


def dump_once(transport, plan=None):
    """One full pass. Any failure raises; a partial dump is never returned."""
    image = bytearray()
    for addr, length in (dump_plan() if plan is None else plan):
        image += read_chunk(transport, addr, length)
    return bytes(image)


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


def run_backup(out_path, passes=3, open_transport=HidrawTransport,
               select_node=select_bootloader_node, plan=None,
               validate=validate_dump):
    """Dump `passes` times, require byte- and SHA-256-identical results, re-parse
    the result, and publish only if every stage succeeded."""
    if passes < 3:
        print(f"REFUSING: at least 3 passes are required, got {passes}.")
        return 2
    if os.path.exists(out_path):
        print(f"REFUSING: {out_path} already exists; refusing to overwrite a backup.")
        return 2
    try:
        node, rejected, app_nodes = select_node()
    except SelectionError as exc:
        print(f"REFUSING: {exc}")
        return 2
    print(f"Bootloader HID device: {node}")
    for note in rejected:
        print(f"  note: skipped {note}")
    for name in app_nodes:
        print(f"  note: application-mode node {name} ignored")
    print(f"REGION app-only base=0x{REGION_LO:x} size=0x{REGION_SIZE:x} "
          f"(bootloader [0x0,0x{REGION_LO:x}) is not readable and is not included)")

    images, digests = [], []
    for index in range(passes):
        try:
            transport = open_transport(node)
        except OSError as exc:
            print(f"REFUSING: cannot open {node}: {exc}")
            print("Nothing was written.")
            return 2
        try:
            image = dump_once(transport, plan)
        except (ProtocolError, UnsafeReport, OSError) as exc:
            print(f"ABORT on pass {index + 1}/{passes}: {exc}")
            print("No dump was accepted and nothing was written.")
            return 1
        finally:
            _close_quietly(transport)
        digest = hashlib.sha256(image).hexdigest()
        images.append(image)
        digests.append(digest)
        print(f"pass {index + 1}/{passes}: 0x{len(image):x} bytes sha256={digest}")

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
          f"(resp[1]=state+0x38 flags, READ-busy bit 0x{BUSY_READ:02x}; "
          f"resp[2]=state+0x35 error), data resp[0]=0x{R_READDATA:02x}")
    _safety_selfcheck()
    print("RESULT dry_run_ok=True guard_rejected_forbidden=True")
    print("LIMITATION No device was opened. A post-EXEC scheduling race, the "
          "hidraw transfer convention, and the absence of any live validation "
          "all remain unresolved, so --run stays gated behind --force-unreviewed.")
    return 0


LIVE_REFUSAL = """REFUSING to run live.

The read-back protocol is recovered from static analysis only and has never been
exercised against hardware. The READ-busy bit is identified (log 81 FUN_00002db8
holds state+0x38 bit 1 across the synchronous READ; log 82 returns that byte as
status resp[1]), but three things remain unvalidated:

  1. A post-EXEC scheduling race: nothing proves the service loop has set bit 1
     before the host's first status query, so an early poll could exit at once
     and return a stale buffer. Status does not expose the pending byte
     state+0x34, so the race cannot be closed from the host side. The end-of-dump
     self-validation rejects the shifted/stale images this would produce, but it
     is a mitigation, not a proof of correctness.
  2. The Linux hidraw write() report-number prefix and read() framing for this
     device are assumed, not observed.
  3. No live validation of any kind has been performed and no installed-firmware
     backup exists, so there is nothing to restore from if a read path misbehaves.

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
