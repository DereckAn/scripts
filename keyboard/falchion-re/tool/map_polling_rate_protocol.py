#!/usr/bin/env python3
"""The polling-rate protocol, decoded from the Armoury Crate USB capture.

Read-only and offline. The capture in `captures/` is evidence: it is opened for
reading only, never modified, and its sha256 is checked before anything is
decoded. NO DEVICE WAS ACCESSED and NO FRAME WAS CONSTRUCTED FOR TRANSMISSION —
every byte string in the output is a frame this tool READ OUT of the capture,
reproduced as evidence, and every carry-capable command carries
`owner_approval_required`.

WHAT THIS ADDS TO LOG 124. Log 124 could not find a polling-rate command because
none had ever been captured, and could not find a firmware consumer of a rate
index. This capture supplies the command — `51 31`, with the index at payload
offset 4 — and the firmware cross-reference finds its handler, its persistence
field and its expansion arithmetic. Log 124's negative is NOT rewritten: it
remains correct for the pre-capture evidence state, and the residual negative it
identified (nothing turns the stored value into a timer period) still stands.

THE ONE NEW MEASUREMENT. The rate is not merely asserted by the owner's stated
order: the interrupt-IN report timestamps quantise to a 1 ms grid in one state
and to a 125 us grid in the other, which is what pins index 0 to 1000 Hz and
index 3 to 8000 Hz from the wire alone — and, as a by-product, demonstrates
high-speed operation, which log 107 asserted and log 124 inherited.

Examples:
    python3 tool/map_polling_rate_protocol.py
    python3 tool/map_polling_rate_protocol.py --json
    python3 tool/map_polling_rate_protocol.py --write
    python3 tool/map_polling_rate_protocol.py --check
"""
import argparse
from collections import Counter
import functools
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
CAPTURES = ROOT / "captures"

CAPTURE = CAPTURES / "02-polling-rate.pcap"
CAPTURE_SHA256 = "a6e860be5192ce942b95441ed2e75bef1ff41c5e87c98ba56747a0148ac45d54"
OWNER_FACTS = CAPTURES / "02-polling-rate-owner-facts.txt"

# STEP 0. Only fields verified to exist in this tshark build are used. The
# owner's Windows host reported usb.capdata / data.data / usb.data_fragment /
# usb.payload as empty for USBPcap; that is re-verified here rather than trusted
# (see empty_field_names()).
FIELDS = ("frame.number", "frame.time_relative", "usb.device_address",
          "usb.endpoint_address", "usb.transfer_type", "usb.data_len",
          "usb.src", "usb.dst", "usb.bmRequestType", "usb.setup.bRequest",
          "usb.bDescriptorType", "usbhid.data")
EMPTY_FIELDS = ("usb.capdata", "data.data", "usb.data_fragment")

# USBPcap synthesises a descriptor exchange at t=0 for every device already
# enumerated when the capture started (--inject-descriptors). Those frames are
# not enumerations and must not be counted as one.
INJECTED_T = 0.0

FALCHION = (0x0B05, 0x1B7E)
VENDOR_OUT = "0x0d"          # interface 1, interrupt OUT, 64-byte frames
VENDOR_IN = "0x85"           # interface 1, interrupt IN, 64-byte frames
REPORT_ENDPOINTS = ("0x81", "0x8c")   # the IN endpoints that carry key reports
VENDOR_REPORT_SIZE = 64

RATE_OPCODE = "5131"         # opcode 0x51, subcommand 0x31
COMMIT_OPCODE = "5055"       # persistent commit — NEVER SEND without approval
RATE_VALUE_OFFSET = 4        # payload byte index carrying the index

# Observed on the wire in this capture. Indices 1 and 2 are NOT reachable from
# Armoury Crate 6.5.7.0 (it exposes 1000 and 8000 only) and are therefore
# derived from the firmware's own `1 << index` arithmetic, not observed.
RATE_INDEX_OBSERVED = {0: 1000, 3: 8000}
RATE_INDEX_DERIVED = {1: 2000, 2: 4000}

# notes/protocol.md's recorded startup order, for confirm-or-correct.
HISTORICAL_STARTUP = ("12 03", "12 00", "22 01", "12 12", "12 08", "12 16",
                      "12 14", "25 00", "25 01")


def _sentence(text):
    """Capitalise only the first letter, leaving acronyms and units alone."""
    return text[:1].upper() + text[1:] if text else text

# Grid tests. A high-speed interrupt endpoint with bInterval=1 is polled every
# 125 us; a device that only has a new report every 1 ms lands on the coarser
# grid. TOL_* are the acceptance windows, each a tenth of its grid.
GRID_MS_SLOW, TOL_MS_SLOW = 1.0, 0.05
GRID_MS_FAST, TOL_MS_FAST = 0.125, 0.0125
# A state is read as slow if most gaps sit on the 1 ms grid, fast if few do.
SLOW_MIN_FRACTION = 0.60
FAST_MAX_FRACTION = 0.25

NEVER_SEND = (
    ("50 55", "persistent commit to flash — writes the profile block and the "
              "wear-levelled store; observed 20 times in this capture, always "
              "immediately after a 51 31 write"),
    ("51 xx (any subcommand)", "the configuration write family; 51 31 is the "
                               "polling rate, 51 21 the Fn-layer remap, and the "
                               "rest are unidentified writes"),
    ("any erase / program / unlock / reset / SPI framing", "the bootloader "
     "vendor-HID protocol of logs 81/82/87/88; not present in this capture and "
     "not to be constructed"),
)


class CaptureError(Exception):
    """Raised on any input this tool refuses to guess about."""


# ---------------------------------------------------------------- extraction

def tshark_binary():
    path = shutil.which("tshark")
    if path is None:
        raise CaptureError("tshark is not installed; this tool parses the "
                           "capture with tshark and installs nothing")
    return path


@functools.lru_cache(maxsize=1)
def tshark_version():
    out = subprocess.run([tshark_binary(), "--version"], check=True,
                         capture_output=True, text=True).stdout
    return out.splitlines()[0].strip()


@functools.lru_cache(maxsize=1)
def field_names():
    """Which of the candidate fields this tshark build actually knows."""
    out = subprocess.run([tshark_binary(), "-G", "fields"], check=True,
                         capture_output=True, text=True).stdout
    known = {line.split("\t")[2] for line in out.splitlines()
             if line.startswith("F\t") and line.count("\t") >= 2}
    missing = [f for f in FIELDS if f not in known]
    if missing:
        raise CaptureError(f"this tshark build lacks required fields: {missing}")
    return tuple(FIELDS)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@functools.lru_cache(maxsize=None)
def verify_capture(path=CAPTURE, expected=CAPTURE_SHA256):
    if not path.exists():
        raise CaptureError(f"capture missing: {path}")
    got = sha256_of(path)
    if got != expected:
        raise CaptureError(f"capture sha256 mismatch: {got} != {expected}")
    return got


def parse_rows(text):
    """Turn tshark -T fields output into dicts, fail-closed on shape."""
    rows = []
    names = FIELDS
    for lineno, line in enumerate(text.splitlines(), 1):
        parts = line.split("\t")
        if len(parts) != len(names):
            raise CaptureError(f"line {lineno}: expected {len(names)} fields, "
                               f"got {len(parts)}")
        row = dict(zip(names, parts))
        try:
            row["frame.number"] = int(row["frame.number"])
            row["t"] = float(row["frame.time_relative"])
        except ValueError as exc:
            raise CaptureError(f"line {lineno}: {exc}") from exc
        rows.append(row)
    return rows


@functools.lru_cache(maxsize=1)
def rows(path=CAPTURE):
    verify_capture(path)
    cmd = [tshark_binary(), "-r", str(path), "-T", "fields",
           "-E", "separator=/t"]
    for f in field_names():
        cmd += ["-e", f]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return tuple(parse_rows(out))


@functools.lru_cache(maxsize=1)
def empty_field_names(path=CAPTURE):
    """Re-derive U8's claim that the alternative payload fields are empty."""
    verify_capture(path)
    subject = subject_addresses()[-1]
    cmd = [tshark_binary(), "-r", str(path), "-T", "fields", "-E",
           "separator=/t", "-Y",
           f"usb.device_address=={subject} && "
           f"(usb.endpoint_address=={VENDOR_OUT} || "
           f"usb.endpoint_address=={VENDOR_IN})"]
    for f in EMPTY_FIELDS:
        cmd += ["-e", f]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    nonempty = Counter()
    for line in out.splitlines():
        for name, value in zip(EMPTY_FIELDS, line.split("\t")):
            if value:
                nonempty[name] += 1
    return {name: nonempty.get(name, 0) for name in EMPTY_FIELDS}


# ------------------------------------------------------------------ devices

@functools.lru_cache(maxsize=1)
def device_identities(path=CAPTURE):
    """address -> (vid, pid, bcdDevice), from GET_DESCRIPTOR device responses."""
    verify_capture(path)
    cmd = [tshark_binary(), "-r", str(path), "-Y", "usb.idVendor", "-T",
           "fields", "-E", "separator=/t", "-e", "usb.device_address",
           "-e", "usb.idVendor", "-e", "usb.idProduct", "-e", "usb.bcdDevice"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    ids = {}
    for line in out.splitlines():
        addr, vid, pid, bcd = line.split("\t")
        ids[int(addr)] = (int(vid, 16), int(pid, 16), int(bcd, 16))
    if not ids:
        raise CaptureError("no device descriptor in the capture; the address "
                           "map cannot be built and nothing may be attributed")
    return ids


def subject_addresses(ids=None):
    ids = device_identities() if ids is None else ids
    found = sorted(a for a, v in ids.items() if v[:2] == FALCHION)
    if not found:
        raise CaptureError("the Falchion 0b05:1b7e is not in this capture")
    return tuple(found)


@functools.lru_cache(maxsize=None)
def device_inventory():
    ids = device_identities()
    counts = Counter(int(r["usb.device_address"]) for r in rows()
                     if r["usb.device_address"])
    subject = set(subject_addresses(ids))
    out = []
    for addr in sorted(counts):
        if addr not in ids:
            raise CaptureError(f"device address {addr} carries "
                               f"{counts[addr]} frames but never identified "
                               f"itself; refusing to attribute it")
        vid, pid, bcd = ids[addr]
        out.append({"address": addr, "vid": f"{vid:#06x}", "pid": f"{pid:#06x}",
                    "bcd_device": f"{bcd:#06x}", "frames": counts[addr],
                    "is_subject": addr in subject})
    return out


@functools.lru_cache(maxsize=None)
def subject_rows():
    """Every frame belonging to the Falchion, and nothing else."""
    keep = {str(a) for a in subject_addresses()}
    return tuple(r for r in rows() if r["usb.device_address"] in keep)


# ------------------------------------------------------- the vendor channel

def vendor_frames(source=None):
    """The 64-byte vendor-HID conversation on interface 1, validated."""
    src = subject_rows() if source is None else source
    out = []
    for r in src:
        ep = r["usb.endpoint_address"]
        if ep not in (VENDOR_OUT, VENDOR_IN):
            continue
        payload = r["usbhid.data"]
        if not payload:
            continue                       # URB submit/complete with no data
        if len(payload) != VENDOR_REPORT_SIZE * 2:
            raise CaptureError(
                f"frame {r['frame.number']}: vendor payload is "
                f"{len(payload) // 2} bytes, not {VENDOR_REPORT_SIZE}")
        try:
            bytes.fromhex(payload)
        except ValueError as exc:
            raise CaptureError(f"frame {r['frame.number']}: {exc}") from exc
        out.append({"frame": r["frame.number"], "t": r["t"],
                    "direction": "OUT" if ep == VENDOR_OUT else "IN",
                    "endpoint": ep, "payload": payload})
    if not out:
        raise CaptureError("no vendor-HID frames found on interface 1")
    return out


@functools.lru_cache(maxsize=None)
def command_inventory():
    """Every distinct vendor command and its reply, with counts."""
    frames = vendor_frames()
    pairs, pending = [], None
    for f in frames:
        if f["direction"] == "OUT":
            pending = f
        elif pending is not None:
            pairs.append((pending, f))
            pending = None
    tally = {}
    for out, back in pairs:
        key = out["payload"][:4]
        entry = tally.setdefault(key, {
            "command": " ".join(key[i:i + 2] for i in (0, 2)),
            "request": out["payload"], "response": back["payload"],
            "count": 0, "first_frame": out["frame"],
            "first_t": round(out["t"], 6),
            "echo_only": out["payload"] == back["payload"]})
        entry["count"] += 1
    return [tally[k] for k in sorted(tally)], len(pairs)


@functools.lru_cache(maxsize=None)
def rate_writes():
    """Every 51 31 frame, in order, with the byte-4 index it carries."""
    out = []
    for f in vendor_frames():
        if f["direction"] != "OUT" or not f["payload"].startswith(RATE_OPCODE):
            continue
        raw = bytes.fromhex(f["payload"])
        index = raw[RATE_VALUE_OFFSET]
        others = {i: b for i, b in enumerate(raw)
                  if b and i not in (0, 1, RATE_VALUE_OFFSET)}
        if others:
            raise CaptureError(f"frame {f['frame']}: a 51 31 write carries "
                               f"non-zero bytes outside offset "
                               f"{RATE_VALUE_OFFSET}: {others}")
        out.append({"frame": f["frame"], "t": round(f["t"], 6), "index": index,
                    "payload": f["payload"]})
    if not out:
        raise CaptureError("no 51 31 frames in this capture")
    return out


@functools.lru_cache(maxsize=None)
def rate_windows():
    """Collapse repeats: one window per change of the carried index."""
    writes = rate_writes()
    end = max(r["t"] for r in rows())
    windows, previous = [], None
    for i, w in enumerate(writes):
        if w["index"] == previous:
            continue                      # a repeat of the same value
        stop = end
        for later in writes[i + 1:]:
            if later["index"] != w["index"]:
                stop = later["t"]
                break
        windows.append({"start": w["t"], "stop": round(stop, 6),
                        "index": w["index"], "frame": w["frame"]})
        previous = w["index"]
    return windows


@functools.lru_cache(maxsize=None)
def reports_inside_commit_windows():
    """Reports delivered between a 51 31 write and its 50 55 echo.

    This is what U4 turns on. Isolated reports DO land there; consecutive PAIRS
    do not, and only a pair yields an inter-report gap that could be graded
    against a grid. So the interval is populated but not measurable.
    """
    changes = {w["start"] for w in rate_windows()}
    out = {"single": 0, "consecutive_pairs": 0, "after_real_change": 0,
           "detail": []}
    for ep in REPORT_ENDPOINTS:
        ts = report_gaps(ep)
        for c in commit_follows():
            lo = c["write_t"]
            hi = lo + (c["commit_latency_ms"] + c["echo_latency_ms"]) / 1000
            inside = [t for t in ts if lo <= t <= hi]
            if not inside:
                continue
            out["single"] += len(inside)
            idx = [ts.index(t) for t in inside]
            out["consecutive_pairs"] += sum(
                1 for a, b in zip(idx, idx[1:]) if b == a + 1)
            real = c["write_t"] in changes
            out["after_real_change"] += len(inside) if real else 0
            out["detail"].append({"endpoint": ep, "write_t": c["write_t"],
                                  "after_real_change": real,
                                  "reports": [round(t, 6) for t in inside]})
    return out


def _commit_timing_note():
    w = reports_inside_commit_windows()
    noop = w["single"] - w["after_real_change"]
    return (f"NOT DETERMINED BY THIS CAPTURE. Key reports DO land between a "
            f"51 31 write and its 50 55 echo — {w['single']} of them — but "
            f"never two consecutively, and only a consecutive PAIR yields an "
            f"inter-report gap that could be graded against a grid. Worse for "
            f"the question, {noop} of those {w['single']} follow a write of "
            f"the value the device already held, so even a pair there would "
            f"have compared one state with itself. The remaining "
            f"{w['after_real_change']} follow a real change but are lone "
            f"reports with no successor inside the window")


@functools.lru_cache(maxsize=None)
def commit_follows():
    """Does a 50 55 commit follow every 51 31 write? With the latency."""
    frames = vendor_frames()
    result = []
    for i, f in enumerate(frames):
        if f["direction"] != "OUT" or not f["payload"].startswith(RATE_OPCODE):
            continue
        commit = next((g for g in frames[i + 1:]
                       if g["direction"] == "OUT"
                       and g["payload"].startswith(COMMIT_OPCODE)), None)
        echo = None
        if commit is not None:
            j = frames.index(commit)
            echo = next((g for g in frames[j + 1:]
                         if g["direction"] == "IN"
                         and g["payload"].startswith(COMMIT_OPCODE)), None)
        result.append({
            "write_frame": f["frame"], "write_t": round(f["t"], 6),
            "commit_frame": None if commit is None else commit["frame"],
            "commit_latency_ms": None if commit is None
            else round((commit["t"] - f["t"]) * 1000, 3),
            "echo_latency_ms": None if echo is None
            else round((echo["t"] - commit["t"]) * 1000, 3)})
    return result


# ------------------------------------------------------------ the enumeration

def enumeration_events(include_injected=False):
    """Every real GET_DESCRIPTOR(device) on the subject — i.e. enumeration.

    Frames at t=0 are USBPcap's injected descriptor synthesis for devices that
    were already enumerated when the capture began. Counting them as an
    enumeration would manufacture an event the bus never carried.
    """
    out = [{"frame": r["frame.number"], "t": round(r["t"], 6),
            "address": int(r["usb.device_address"]),
            "injected": r["t"] <= INJECTED_T}
           for r in subject_rows()
           if r["usb.setup.bRequest"] == "6"
           and r["usb.bDescriptorType"] == "0x01"]
    return out if include_injected else [e for e in out if not e["injected"]]


@functools.lru_cache(maxsize=None)
def descriptor_endpoints(path=CAPTURE):
    """bInterval / wMaxPacketSize per endpoint, read off the wire descriptor."""
    verify_capture(path)
    cmd = [tshark_binary(), "-r", str(path), "-T", "fields", "-E",
           "separator=/t", "-Y",
           "usb.bEndpointAddress && usb.device_address==%d"
           % subject_addresses()[-1],
           "-e", "frame.number", "-e", "usb.bEndpointAddress",
           "-e", "usb.bInterval", "-e", "usb.wMaxPacketSize"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        raise CaptureError("no configuration descriptor for the subject")
    _, eps, intervals, sizes = lines[0].split("\t")
    eps, intervals, sizes = eps.split(","), intervals.split(","), sizes.split(",")
    if not (len(eps) == len(intervals) == len(sizes)):
        raise CaptureError("descriptor endpoint fields disagree in length")
    return [{"endpoint": e, "b_interval": int(i), "w_max_packet_size": int(s)}
            for e, i, s in zip(eps, intervals, sizes)]


def control_transfer_span():
    """When control traffic to the subject happens — all of it."""
    ts = [r["t"] for r in subject_rows()
          if r["usb.transfer_type"] in ("0x02", "0xff")
          and r["t"] > INJECTED_T]
    if not ts:
        raise CaptureError("no control transfers to the subject")
    return {"count": len(ts), "first": round(min(ts), 6),
            "last": round(max(ts), 6)}


# ------------------------------------------------------------- the timing test

@functools.lru_cache(maxsize=None)
def report_gaps(endpoint):
    return tuple(sorted(r["t"] for r in subject_rows()
                        if r["usb.endpoint_address"] == endpoint
                        and r["usbhid.data"]))


def _on_grid(gap_ms, grid, tol):
    rem = gap_ms % grid
    return min(rem, grid - rem) < tol


@functools.lru_cache(maxsize=None)
def grid_statistics(endpoint):
    """Per rate state: what fraction of report gaps land on each grid.

    This is the measurement that turns the owner's stated order into evidence.
    Only gaps wholly inside one window are used, so a rate change never
    straddles a measured interval.
    """
    windows = rate_windows()
    ts = report_gaps(endpoint)
    per_state = {}
    for w in windows:
        seg = [t for t in ts if w["start"] <= t < w["stop"]]
        for a, b in zip(seg, seg[1:]):
            per_state.setdefault(w["index"], []).append((b - a) * 1000.0)
    out = {}
    for index, gaps in sorted(per_state.items()):
        slow = sum(1 for g in gaps if _on_grid(g, GRID_MS_SLOW, TOL_MS_SLOW))
        fast = sum(1 for g in gaps if _on_grid(g, GRID_MS_FAST, TOL_MS_FAST))
        out[index] = {"gaps": len(gaps),
                      "on_1ms_grid": slow,
                      "on_1ms_fraction": round(slow / len(gaps), 4),
                      "on_125us_grid": fast,
                      "on_125us_fraction": round(fast / len(gaps), 4),
                      "min_gap_ms": round(min(gaps), 4)}
    return out


@functools.lru_cache(maxsize=None)
def measured_rates(endpoint="0x81"):
    """Read each state's rate off the grid statistics alone."""
    verdicts = {}
    for index, s in grid_statistics(endpoint).items():
        if s["on_1ms_fraction"] >= SLOW_MIN_FRACTION:
            verdicts[index] = 1000
        elif (s["on_1ms_fraction"] <= FAST_MAX_FRACTION
              and s["on_125us_fraction"] >= SLOW_MIN_FRACTION):
            verdicts[index] = 8000
        else:
            verdicts[index] = None
    return verdicts


# --------------------------------------------------------------- background

@functools.lru_cache(maxsize=None)
def background_traffic():
    """What an app must tolerate, split by whose traffic it is."""
    subject = set(subject_addresses())
    ids = device_identities()
    counts = Counter(int(r["usb.device_address"]) for r in rows()
                     if r["usb.device_address"])
    others = []
    for addr, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        if addr in subject:
            continue
        vid, pid, _ = ids[addr]
        others.append({"address": addr, "device": f"{vid:04x}:{pid:04x}",
                       "frames": n, "share": round(n / sum(counts.values()), 4)})
    vend = vendor_frames()
    handshake_end = max(f["t"] for f in vend
                        if f["payload"].startswith(("12", "22", "25")))
    after = [f for f in vend if f["t"] > handshake_end
             and f["direction"] == "OUT"]
    return {
        "subject_vendor_frames": len(vend),
        "handshake_last_query_t": round(handshake_end, 6),
        "host_vendor_frames_after_handshake": len(after),
        "keepalive_period_s": None,
        "verdict": "Armoury Crate sends the Falchion NO periodic keepalive. "
                   "After the startup handshake every host frame on the vendor "
                   "channel is a deliberate user action (51 31) and its commit "
                   "(50 55). The heavy periodic traffic in this capture belongs "
                   "to OTHER devices and must not be attributed to the keyboard.",
        "other_devices": others,
    }


# ------------------------------------------------------------------- checks

@functools.lru_cache(maxsize=None)
def verify():
    checks = []

    def check(ok, label, detail=""):
        checks.append({"ok": bool(ok), "label": label, "detail": detail})
        return ok

    ids = device_identities()
    subject = subject_addresses(ids)
    check(FALCHION in {v[:2] for v in ids.values()},
          "the Falchion identifies itself on the wire",
          f"0b05:1b7e at address(es) {list(subject)}")
    check(all(ids[a][2] == 0x0159 for a in subject),
          "the subject's bcdDevice is the preserved 1.59 firmware",
          "bcdDevice 0x0159 on every subject address")

    writes = rate_writes()
    values = sorted({w["index"] for w in writes})
    check(values == [0, 3], "the rate field takes exactly two values",
          f"payload offset {RATE_VALUE_OFFSET} = {values} over "
          f"{len(writes)} writes")
    check(all(w["payload"][:4] == RATE_OPCODE for w in writes),
          "every rate write is opcode 51 subcommand 31",
          f"{len(writes)} frames")

    windows = rate_windows()
    per = Counter(w["index"] for w in windows)
    check(min(per.values()) >= 2,
          "each rate value repeats across at least two windows (U3)",
          ", ".join(f"index {k}: {v} windows" for k, v in sorted(per.items())))
    check(all(a["index"] != b["index"] for a, b in zip(windows, windows[1:])),
          "the collapsed windows strictly alternate",
          f"{len(windows)} windows")

    commits = commit_follows()
    check(all(c["commit_frame"] is not None for c in commits),
          "a 50 55 commit follows every 51 31 write",
          f"{len(commits)} writes, all committed")

    inside = reports_inside_commit_windows()
    check(inside["consecutive_pairs"] == 0,
          "no consecutive report pair lies inside a write-to-commit interval, "
          "which is precisely why U4 stays open",
          f"{inside['single']} isolated reports land there, "
          f"{inside['consecutive_pairs']} consecutive pairs")

    enums = enumeration_events()
    check(len(enums) == 1,
          "the subject enumerates exactly once — no rate change re-enumerates "
          "(U5)",
          f"one real GET_DESCRIPTOR(device), at t={enums[0]['t']}; the t=0 "
          f"descriptor frames are USBPcap's injected synthesis and are "
          f"excluded" if enums else "no real enumeration found")
    span = control_transfer_span()
    first_change = windows[0]["start"]
    check(span["last"] < first_change,
          "no control transfer reaches the subject at or after any rate "
          "change (U1)",
          f"{span['count']} control frames, all in "
          f"[{span['first']}, {span['last']}]; first rate change at "
          f"{first_change}")

    eps = {e["endpoint"]: e for e in descriptor_endpoints()}
    check(eps["0x81"]["b_interval"] == 1 and eps["0x8e"]["b_interval"] == 4,
          "the wire descriptor reproduces log 107's bInterval table",
          ", ".join(f"{k} bInterval={v['b_interval']}"
                    for k, v in sorted(eps.items())))

    for ep in REPORT_ENDPOINTS:
        m = measured_rates(ep)
        check(m.get(0) == 1000 and m.get(3) == 8000,
              f"EP {ep}: the report grid measures index 0 = 1000 Hz and "
              f"index 3 = 8000 Hz",
              "; ".join(f"index {k}: {v} Hz" for k, v in sorted(m.items())))

    stats = grid_statistics("0x81")
    check(stats[3]["on_1ms_fraction"] < stats[0]["on_1ms_fraction"],
          "the 1 ms grid separates the two states, which is what makes the "
          "reading a measurement rather than a restatement of the owner's order",
          f"index 0: {stats[0]['on_1ms_fraction']:.1%} on the 1 ms grid; "
          f"index 3: {stats[3]['on_1ms_fraction']:.1%}")
    check(stats[3]["on_125us_fraction"] >= SLOW_MIN_FRACTION,
          "index 3's reports land on the 125 us grid, which is impossible at "
          "full speed — this capture demonstrates high-speed operation",
          f"{stats[3]['on_125us_fraction']:.1%} of "
          f"{stats[3]['gaps']} gaps")

    empties = empty_field_names()
    check(all(v == 0 for v in empties.values()),
          "on the vendor endpoints only usbhid.data carries the payload (U8)",
          ", ".join(f"{k}={v}" for k, v in sorted(empties.items()))
          + " — note this build DOES populate usb.data_fragment on 90 control "
            "transfers, so the owner's blanket 'returns EMPTY' is corrected to "
            "'empty on the vendor endpoints'")

    st = startup_section()
    check(st["historical_tail_matches"],
          "the launch burst ends with notes/protocol.md's recorded nine-command "
          "startup block, in order",
          " ".join(f"[{c}]" for c in st["historical_tail"]))

    inv, pair_count = command_inventory()
    check(pair_count * 2 == len(vendor_frames()),
          "every vendor request has exactly one reply",
          f"{pair_count} request/response pairs")

    doc = to_wire_document()
    carriers = [c for c in doc["commands"] if c["writes_device_state"]]
    check(carriers and all(c["owner_approval_required"] for c in carriers),
          "every state-writing command is marked owner-approval-only",
          f"{len(carriers)} write-capable commands")
    check(all(any(n[0].split()[0] in c["command"] for n in NEVER_SEND)
              or c["owner_approval_required"]
              for c in doc["commands"] if c["writes_device_state"]),
          "the never-send list covers every write-capable command", "")
    return checks


# ------------------------------------------------------------- the document

@functools.lru_cache(maxsize=None)
def to_wire_document():
    """The protocol surface an owner's application needs, as data."""
    return {
        "transport": {
            "interface": 1,
            "usage_page": "0xFF00",
            "report_id": "none declared — prepend a 0x00 placeholder byte on "
                         "both Windows and Linux hidraw",
            "out_endpoint": VENDOR_OUT,
            "in_endpoint": VENDOR_IN,
            "report_size_bytes": VENDOR_REPORT_SIZE,
            "endpoints": descriptor_endpoints(),
        },
        "commands": [
            {"command": "12 00", "kind": "query",
             "meaning": "firmware version; reply appends "
                        "00 00 59 00 01 00 06 00 03 00 = 1.59",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 03", "kind": "query",
             "meaning": "unidentified; reply is the header and zeros",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 07", "kind": "query",
             "meaning": "unidentified; reply appends 01",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 08", "kind": "query",
             "meaning": "unidentified; reply appends 01",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 12", "kind": "query",
             "meaning": "unidentified; reply appends 01 01",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 14", "kind": "query",
             "meaning": "with request byte 2 = 02 the reply appends the ASCII "
                        "model string 024080600167; with byte 2 = 00 the reply "
                        "is the header and zeros",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 15", "kind": "query",
             "meaning": "GET POLLING RATE. Not sent by Armoury Crate in this "
                        "capture; recovered from the firmware dispatcher, "
                        "which reads profile block +0x4f8, masks the low four "
                        "bits and returns the index in reply byte 4",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "12 16", "kind": "query",
             "meaning": "unidentified; reply is the header and zeros",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "22 01", "kind": "handshake",
             "meaning": "init handshake; echo only",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "25 00", "kind": "handshake",
             "meaning": "init handshake; echo only",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "25 01", "kind": "handshake",
             "meaning": "init handshake; echo only",
             "writes_device_state": False, "owner_approval_required": False},
            {"command": "51 31", "kind": "write",
             "meaning": "SET POLLING RATE. Payload byte 4 is the rate index; "
                        "all other bytes are zero in every observed frame",
             "writes_device_state": True, "owner_approval_required": True},
            {"command": "50 55", "kind": "commit",
             "meaning": "persistent commit to flash",
             "writes_device_state": True, "owner_approval_required": True},
        ],
        "never_send": [{"frame": f, "why": w} for f, w in NEVER_SEND],
    }


def polling_rate_section():
    windows = rate_windows()
    measured = {ep: measured_rates(ep) for ep in REPORT_ENDPOINTS}
    return {
        "command": {
            "opcode": "0x51", "subcommand": "0x31",
            "value_offset": RATE_VALUE_OFFSET,
            "value_width_bytes": 1,
            "other_bytes": "zero in every observed frame",
            "distinct_payloads_observed": sorted(
                {w["payload"] for w in rate_writes()}),
            "response": "a verbatim echo of the request. The firmware builds it "
                        "from the request rather than copying the frame: "
                        "opcode 0x51, subcommand 0x31, a zero 16-bit field, "
                        "then one payload byte taken from request byte 4",
            "owner_approval_required": True,
        },
        "encoding": {
            "kind": "index",
            "firmware_expansion": "1 << index",
            "unit_of_expansion_hz": 1000,
            "observed": {str(k): v for k, v in RATE_INDEX_OBSERVED.items()},
            "derived_not_observed": {str(k): v
                                     for k, v in RATE_INDEX_DERIVED.items()},
            "direction": "ascending — the larger index is the faster rate",
            "note": "Armoury Crate 6.5.7.0 exposes only 1000 and 8000 Hz for "
                    "this keyboard, so indices 1 and 2 were never sent. They "
                    "are read out of the firmware's own arithmetic and its "
                    "bound of 3, not observed on the wire.",
        },
        "windows": windows,
        "reports_inside_commit_windows": reports_inside_commit_windows(),
        "writes": rate_writes(),
        "commits": commit_follows(),
        "measurement": {
            "method": "inter-report timestamp quantisation on the subject's "
                      "interrupt-IN endpoints, per rate state",
            "grids_ms": {"slow": GRID_MS_SLOW, "fast": GRID_MS_FAST},
            "per_endpoint": {ep: grid_statistics(ep)
                             for ep in REPORT_ENDPOINTS},
            "verdict": {ep: {str(k): v for k, v in m.items()}
                        for ep, m in measured.items()},
        },
        "persistence": {
            "commit_required_to_persist": True,
            "commit_command": "50 55",
            "applies_without_commit": _commit_timing_note(),
            "stored_at": "profile block +0x4f8, bits 0..3",
        },
        "re_enumeration": {
            "occurs": False,
            "evidence": "the subject issues exactly one GET_DESCRIPTOR(device), "
                        "at the deliberate replug; no device address above the "
                        "subject's appears anywhere; every control transfer to "
                        "the subject predates the first rate change",
            "b_interval_consequence": "because the device never re-enumerates, "
                                      "this capture provides no post-change "
                                      "configuration descriptor. Whether any "
                                      "bInterval would change is NOT ANSWERED. "
                                      "The mechanism does not need one: the "
                                      "host already polls EP 0x81 every 125 us "
                                      "(bInterval 1 at high speed), and the "
                                      "rate setting changes how often the "
                                      "DEVICE has a new report ready.",
        },
    }


def firmware_section():
    return {
        "handler": {
            "address": "0x18002b2e",
            "reached_from": "the vendor-HID dispatcher FUN_18001fbe: "
                            "cmp r2,#0x51 at 0x1800201c selects the opcode, "
                            "cmp r2,#0x31 at 0x180024d2 the subcommand",
            "listing": [
                "18002b2e  ldrb   r1,[r4,#0x4]     ; r4 = 0x180233a8, the vendor request buffer",
                "18002b30  cmp    r1,#0x3",
                "18002b32  beq    0x18002b38",
                "18002b34  cmp    r1,#0x0",
                "18002b36  bne    0x18002b6c        ; anything but 0 or 3 leaves the handler",
                "18002b38  ldr    r2,[0x18002e40]   ; *(0x18002e40) = 0x18021de0, the profile block",
                "18002b3a  ldrh.w r0,[r2,#0x4f8]",
                "18002b3e  bfi    r0,r1,#0x0,#0x4   ; the index into bits 0..3",
                "18002b42  strh.w r0,[r2,#0x4f8]",
                "18002b46  and    r1,r0,#0xf",
                "18002b4a  lsl.w  r0,r6,r1          ; r6 = 1, set once at 0x18001fd6",
                "18002b4e  ldr    r1,[0x18002e44]   ; *(0x18002e44) = 0x1801e736",
                "18002b50  strb   r0,[r1,#0x0]      ; the expanded multiplier, as a byte",
                "18002b52  adr    r0,[0x18002e48]   ; the string \"=S_PR_U\"",
                "18002b54  bl     0x1801bd78        ; the firmware's own logger",
                "18002b58  adds   r3,r4,#0x4",
                "18002b5a  movs   r2,#0x0",
                "18002b5c  movs   r1,#0x31",
                "18002b5e  str    r6,[sp,#0x0]      ; response payload length = 1",
                "18002b60  b      0x180030c4        ; movs r0,#0x51 ; bl SendResponse64",
            ],
            "confidence": "observed",
            "kind_basis": "static analysis of the preserved installed "
                          "application image, cross-checked instruction for "
                          "instruction against the pre-existing Ghidra listing "
                          "in ghidra/decompiles/dispatcher.txt",
        },
        "acceptance": {
            "accepted_values": [0, 3],
            "note": "the handler accepts 0 and 3 by explicit comparison and "
                    "falls through for everything else, INCLUDING 1 and 2. The "
                    "four-entry reading rests on bfi's 4-bit field, the mask "
                    "`and r1,r0,#0xf`, and the `1 << index` expansion — not on "
                    "the "
                    "handler accepting 1 or 2, which it does not.",
        },
        "persistence": {
            "field": "profile block 0x18021de0 + 0x4f8, bits 0..3",
            "corrects": "log 125 recorded +0x4f8 as the VERSION STAMP copied "
                        "from ROM 0x1801bfbc. That reading is refined, not "
                        "withdrawn: the polling-rate index occupies the low "
                        "four bits of the same halfword, and log 125's "
                        "unmatched `performance.pollingRate` row is now "
                        "matched.",
            "checksum_coverage": "neither",
            "checksum_ranges": "checksum A covers +0x002..+0x4b1 and "
                               "checksum B covers +0x4fc..+0x7bb, so +0x4f8 "
                               "falls between them and writing four bits of it "
                               "invalidates neither sum",
            "reload_path": "FUN_18000d56 at 0x1800153a reloads it: "
                           "ldrb.w r1,[r7,#0x4f8]; and r1,r1,#0xf; "
                           "lsl.w r1,r0,r1; strb r1,[r2] — the same expansion "
                           "as the wire handler",
        },
        "get_command": {
            "command": "12 15",
            "address": "0x18002254",
            "listing": [
                "18002254  ldr    r0,[0x1800259c]   ; = 0x18021de0, the profile block",
                "18002256  adds   r3,r4,#0x4",
                "18002258  ldrb.w r0,[r0,#0x4f8]",
                "1800225c  and    r0,r0,#0xf",
                "18002260  strb   r0,[r4,#0x4]      ; the index into reply byte 4",
                "18002262  movs   r0,#0x3c          ; 60-byte payload",
                "18002268  movs   r1,#0x15",
                "18002250  movs   r0,#0x12          ; -> SendResponse64",
            ],
            "confidence": "strongly-inferred",
            "kind_basis": "the handler is read out of the instruction stream "
                          "and reaches the same field the set handler writes, "
                          "but Armoury Crate never sent 12 15 in this capture, "
                          "so no reply was observed",
        },
        "consumer": {
            "found": False,
            "byte": "0x1801e736",
            "writers": ["0x1800117c", "0x18001536", "0x180018f4", "0x18001ecc",
                        "0x18002b4e", "0x18007a18"],
            "readers": [],
            "search": "an aligned-word search of every preserved image for the "
                      "address, a displacement search over every region "
                      "pointer within 4095 bytes below it, and a movw/movt "
                      "immediate search for its construction",
            "verdict": "SIX WRITERS, NO READER. Log 124's residual negative "
                       "survives one level deeper: the firmware stores the "
                       "index, persists it and expands it to a multiplier, and "
                       "nothing in the preserved images turns that multiplier "
                       "into a timer period. What the images do NOT contain "
                       "is not evidence that the device ignores it — the wire "
                       "shows it plainly does not.",
        },
        "units": {
            "attached_now": "the REPORT CADENCE, measured: index 0 delivers on "
                            "a 1 ms grid and index 3 on a 125 us grid. "
                            "Combined with the firmware's 1 << index, the "
                            "expansion's unit is 1000 Hz.",
            "still_unresolved": "IRQ38's period. Nothing here reads the tick, "
                                "and the dependency map's clock_frequency stays "
                                "unresolved. The six subsystems log 124 found "
                                "riding IRQ38 are untouched by this step.",
        },
    }


UNCERTAINTIES = (
    ("U1", "Command transport: interrupt OUT or a control SET_REPORT?",
     "RESOLVED — interrupt OUT on EP 0x0d. Every control transfer to the "
     "subject, all 402 of them, lies inside the 0.73 s enumeration burst that "
     "follows the deliberate replug; the first rate change is over 110 s later. "
     "Both paths were searched for every window."),
    ("U2", "Encoding direction: ascending or descending?",
     "RESOLVED — ascending, and not from the owner's stated order alone. The "
     "report-timestamp grid measures index 3 as the faster state."),
    ("U3", "Carrier shape: a dedicated command or a byte in a larger blob?",
     "RESOLVED — a dedicated command. The two 51 31 forms differ at exactly one "
     "of 64 payload bytes; the other 59 non-header bytes are zero in all 20 "
     "frames. Each value recurs in at least two cleanly separated windows."),
    ("U4", "Application timing: immediately, on commit, or on re-enumeration?",
     "PARTIALLY RESOLVED — not on re-enumeration, because none occurs. Whether "
     "the 51 31 write alone suffices, or the 50 55 commit is needed, is NOT "
     "DETERMINED. Fourteen key reports do land inside a write-to-commit-echo "
     "interval, but never two consecutively, so no inter-report gap lies "
     "wholly inside one and there is nothing to grade against a grid; and all "
     "but two of them follow a write of the value the device already held. "
     "Every observed change was a write immediately followed by a commit."),
    ("U5", "Re-enumeration: does the device reset and come back?",
     "RESOLVED, NEGATIVE — and the negative is a first-class fact. Exactly one "
     "GET_DESCRIPTOR(device) in the whole capture, at the replug; no address "
     "above the subject's; the subject holds one address across all twelve "
     "windows. Consequently NO post-change configuration descriptor exists and "
     "no bInterval diff against log 107 is possible from this capture."),
    ("U6", "Background traffic: what must an app tolerate?",
     "RESOLVED — nothing from the keyboard. Armoury Crate sends the Falchion no "
     "periodic keepalive at all: after the startup handshake every host frame "
     "on its vendor channel is a user action. The capture's heavy periodic "
     "traffic belongs to other devices on the same root hub and is kept "
     "strictly separate."),
    ("U7", "Coalescing: fewer than four change events?",
     "RESOLVED, THE OTHER WAY — there are MORE. Armoury Crate 6.5.7.0 exposes "
     "only 1000 and 8000 Hz, so the prompt's 1000/2000/4000/8000 sequence was "
     "impossible; the owner toggled between the two values repeatedly. Twenty "
     "51 31 writes collapse to twelve strictly alternating windows. Nothing "
     "was invented to reach four."),
    ("U8", "tshark output quirks.",
     "RESOLVED — usbhid.data carries the 64-byte payload; usb.capdata, "
     "data.data and usb.data_fragment are re-verified empty on this build "
     "rather than assumed. Every payload is length-checked to 64 bytes before "
     "it is decoded, and the firmware listing was cross-checked against an "
     "independent disassembly."),
)


@functools.lru_cache(maxsize=None)
def to_dict():
    checks = verify()
    return {
        "verdict": "the polling rate is set by 51 31 with a one-byte index at "
                   "payload offset 4; index 0 = 1000 Hz and index 3 = 8000 Hz, "
                   "measured from the report cadence; the device does not "
                   "re-enumerate",
        "capture": {
            "file": str(CAPTURE.relative_to(ROOT)),
            "sha256": verify_capture(),
            "frames": len(rows()),
            "duration_s": round(max(r["t"] for r in rows()), 6),
            "tshark": tshark_version(),
            "fields_used": list(field_names()),
            "fields_verified_empty": empty_field_names(),
            "anchor_method": "traffic landmarks — no wall-clock stamps were "
                             "recorded for the rate changes",
            "second_capture": "none — no lighting capture was taken, so the "
                              "lighting branch of the analysis is skipped",
        },
        "devices": device_inventory(),
        "wire_document": to_wire_document(),
        "startup": startup_section(),
        "polling_rate": polling_rate_section(),
        "background": background_traffic(),
        "enumeration": {"events": enumeration_events(),
                        "injected_at_t0": enumeration_events(True),
                        "control_transfer_span": control_transfer_span(),
                        "endpoints": descriptor_endpoints()},
        "firmware": firmware_section(),
        "uncertainties": [{"key": k, "question": q, "resolution": r}
                          for k, q, r in UNCERTAINTIES],
        "checks": checks,
        "summary": {"checks": len(checks),
                    "failed": sum(1 for c in checks if not c["ok"]),
                    "ok": all(c["ok"] for c in checks)},
        "disclaimer": "Offline analysis of a preserved capture and preserved "
                      "firmware images. No device was accessed and no frame "
                      "was constructed for transmission. Every byte string "
                      "here was read out of the capture or the images. This "
                      "authorises nothing live.",
    }


@functools.lru_cache(maxsize=None)
def startup_section():
    inv, _ = command_inventory()
    frames = vendor_frames()
    bursts, current, previous_t = [], [], None
    for f in frames:
        if previous_t is not None and f["t"] - previous_t > 5.0:
            bursts.append(current)
            current = []
        current.append(f)
        previous_t = f["t"]
    bursts.append(current)
    handshakes = []
    for b in bursts:
        outs = [f for f in b if f["direction"] == "OUT"]
        if not outs or any(f["payload"].startswith(RATE_OPCODE) for f in outs):
            continue
        handshakes.append({
            "start": round(b[0]["t"], 6), "stop": round(b[-1]["t"], 6),
            "sequence": [" ".join(f["payload"][i:i + 2] for i in (0, 2))
                         for f in outs]})
    last = handshakes[-1]["sequence"] if handshakes else []
    tail = last[-len(HISTORICAL_STARTUP):]
    return {
        "bursts": handshakes,
        "last_launch_burst": last,
        "historical_tail": tail,
        "historical_tail_matches": tuple(tail) == HISTORICAL_STARTUP,
        "historical_agreement":
            "notes/protocol.md records the startup order as "
            + ", ".join(HISTORICAL_STARTUP) +
            ". The Armoury Crate launch burst in this capture ENDS with "
            "exactly that nine-command block, in that order, so the historical "
            "record is CONFIRMED rather than corrected. What it did not "
            "record: the launch burst is longer than nine commands, it opens "
            "with 12 14 carrying request byte 2 = 02 (a model-string read "
            "returning the ASCII 024080600167) followed by 12 07, and the "
            "12 03 / 12 00 / 22 01 / 12 12 group is repeated more than once "
            "within a single launch. The prompt's expectation that the "
            "startup query is 12 00 is therefore half right: 12 00 is the "
            "VERSION query and appears inside the block, but it is not the "
            "first query of a launch.",
        "commands": inv,
    }


# --------------------------------------------------------------- rendering

def report_lines():
    d = to_dict()
    pr, fw = d["polling_rate"], d["firmware"]
    out = ["POLLING-RATE PROTOCOL — from captures/02-polling-rate.pcap", "",
           f"capture   {d['capture']['frames']} frames, "
           f"{d['capture']['duration_s']} s, sha256 "
           f"{d['capture']['sha256'][:16]}...",
           f"tshark    {d['capture']['tshark']}", ""]
    out.append("DEVICES")
    for dev in d["devices"]:
        mark = "  <- SUBJECT" if dev["is_subject"] else ""
        out.append(f"  addr {dev['address']}  {dev['vid'][2:]}:{dev['pid'][2:]}"
                   f"  {dev['frames']:>7} frames{mark}")
    out += ["", "THE COMMAND",
            f"  51 31, index at payload offset {pr['command']['value_offset']}, "
            f"all other bytes zero",
            f"  index 0 = 1000 Hz, index 3 = 8000 Hz  (measured)",
            f"  index 1 = 2000 Hz, index 2 = 4000 Hz  (derived from the "
            f"firmware's 1 << index; NOT observed)",
            f"  response: {pr['command']['response'][:60]}...",
            f"  commit:   {pr['persistence']['commit_command']} follows every "
            f"write ({len(pr['commits'])} of {len(pr['commits'])})",
            f"  re-enumeration: {pr['re_enumeration']['occurs']}", ""]
    out.append("THE MEASUREMENT")
    for ep, stats in pr["measurement"]["per_endpoint"].items():
        for index, s in stats.items():
            out.append(f"  EP {ep} index {index}: {s['gaps']:>4} gaps, "
                       f"{s['on_1ms_fraction']:>6.1%} on the 1 ms grid, "
                       f"{s['on_125us_fraction']:>6.1%} on the 125 us grid")
    out += ["", "FIRMWARE",
            f"  handler {fw['handler']['address']} in the vendor-HID dispatcher",
            f"  stored  {fw['persistence']['field']}",
            f"  get     {fw['get_command']['command']} at "
            f"{fw['get_command']['address']}",
            f"  consumer of the expanded byte: "
            f"{'found' if fw['consumer']['found'] else 'NOT FOUND'} "
            f"({len(fw['consumer']['writers'])} writers, "
            f"{len(fw['consumer']['readers'])} readers)", ""]
    out.append("UNCERTAINTIES")
    for u in d["uncertainties"]:
        out.append(f"  {u['key']}  {u['resolution'].split(' — ')[0]}")
    out += ["", "CHECKS"]
    for c in d["checks"]:
        out.append(f"  {'PASS' if c['ok'] else 'FAIL'} {c['label']}"
                   + (f" — {c['detail']}" if c["detail"] else ""))
    s = d["summary"]
    out += ["", f"RESULT polling_rate_protocol_ok={s['ok']} "
                f"checks={s['checks']}"]
    return out


def markdown():
    d = to_dict()
    pr, fw, wd = d["polling_rate"], d["firmware"], d["wire_document"]
    out = ["# The polling-rate protocol", "",
           "**Generated by `tool/map_polling_rate_protocol.py`. Do not edit by "
           "hand.**", "",
           "> Offline analysis of a preserved capture and preserved firmware "
           "images. No device was accessed and no frame was constructed for "
           "transmission. Every byte string below was READ OUT of the capture "
           "or the images. This authorises nothing live.", "",
           "## Verdict", "", f"**{_sentence(d['verdict'])}.**", "",
           "## The capture", "",
           f"- `{d['capture']['file']}`, sha256 `{d['capture']['sha256']}`",
           f"- {d['capture']['frames']} frames over "
           f"{d['capture']['duration_s']} s",
           f"- decoded with {d['capture']['tshark']}",
           f"- anchor method: {d['capture']['anchor_method']}",
           f"- {d['capture']['second_capture']}", "",
           "| address | device | frames | subject |", "|---|---|---|---|"]
    for dev in d["devices"]:
        out.append(f"| {dev['address']} | `{dev['vid'][2:]}:{dev['pid'][2:]}` | "
                   f"{dev['frames']} | {'**yes**' if dev['is_subject'] else ''} |")
    t = wd["transport"]
    out += ["", "## Transport", "",
            f"Interface {t['interface']}, usage page {t['usage_page']}, "
            f"{t['report_size_bytes']}-byte unnumbered reports: OUT on "
            f"`{t['out_endpoint']}`, IN on `{t['in_endpoint']}`.",
            f"Report ID: {t['report_id']}.", "",
            "| endpoint | bInterval | wMaxPacketSize |", "|---|---|---|"]
    for e in t["endpoints"]:
        out.append(f"| `{e['endpoint']}` | {e['b_interval']} | "
                   f"{e['w_max_packet_size']} |")
    out += ["", "## The startup sequence", "",
            d["startup"]["historical_agreement"], "",
            "The full Armoury Crate launch burst, in order: "
            + ", ".join(f"`{c}`" for c in d["startup"]["last_launch_burst"]),
            "",
            "Its tail — the historically recorded block — is "
            + ", ".join(f"`{c}`" for c in d["startup"]["historical_tail"])
            + ".",
            "", "### Every distinct vendor command observed", "",
            "| command | reply | seen | echo only |",
            "|---|---|---|---|"]
    for c in d["startup"]["commands"]:
        reply = c["response"][:24].rstrip("0") or "00"
        out.append(f"| `{c['command']}` | `{reply}…` | {c['count']} | "
                   f"{'yes' if c['echo_only'] else 'no'} |")
    out += ["", "## The polling-rate command", "",
            "```", "byte:  0    1    2  3    4         5..63",
            "      51   31   00 00   <index>   00 ...", "```", "",
            f"The index sits at payload offset {pr['command']['value_offset']}. "
            f"Every other byte is zero in all "
            f"{len(pr['writes'])} observed writes. Only two distinct 64-byte "
            f"payloads exist in the capture.", "",
            "| index | rate | how known |", "|---|---|---|"]
    for k, v in sorted(pr["encoding"]["observed"].items()):
        out.append(f"| {k} | {v} Hz | **measured on the wire** |")
    for k, v in sorted(pr["encoding"]["derived_not_observed"].items()):
        out.append(f"| {k} | {v} Hz | derived from the firmware's "
                   f"`1 << index`; **not observed** |")
    out += ["", pr["encoding"]["note"], "",
            "**Response.** " + _sentence(pr["command"]["response"]) + ".", "",
            f"**Commit.** A `{pr['persistence']['commit_command']}` commit "
            f"follows every one of the {len(pr['commits'])} writes in this "
            f"capture, and the value is stored at "
            f"{pr['persistence']['stored_at']}. Whether the write alone would "
            f"have sufficed is "
            + pr["persistence"]["applies_without_commit"] + ".",
            "", "**Re-enumeration.** Does not occur. "
            + _sentence(pr["re_enumeration"]["evidence"]) + ".", "",
            _sentence(pr["re_enumeration"]["b_interval_consequence"]), "",
            "## How the rate was measured, not assumed", "",
            "No wall-clock stamps exist, so the owner's stated order could not "
            "anchor the decode by itself. The subject's interrupt-IN "
            "timestamps do. A high-speed endpoint with `bInterval = 1` is "
            "polled every 125 us; a device that only has a new report every "
            "millisecond can only complete on the coarser grid. Splitting the "
            "gaps between consecutive key reports by rate state, and never "
            "crossing a change:", "",
            "| endpoint | index | gaps | on the 1 ms grid | on the 125 us grid |",
            "|---|---|---|---|---|"]
    for ep, stats in pr["measurement"]["per_endpoint"].items():
        for index, s in stats.items():
            out.append(f"| `{ep}` | {index} | {s['gaps']} | "
                       f"{s['on_1ms_fraction']:.1%} | "
                       f"{s['on_125us_fraction']:.1%} |")
    out += ["", "Index 0 lands on the millisecond grid; index 3 does not, and "
            "lands on the 125 us grid instead. Two independent endpoints agree. "
            "That is what pins index 0 to 1000 Hz and index 3 to 8000 Hz "
            "without relying on the owner's recollection — and, as a "
            "by-product, it demonstrates high-speed operation, which log 107 "
            "asserted and log 124 explicitly inherited rather than derived.", "",
            "## What the firmware does with it", "",
            f"The handler is at `{fw['handler']['address']}`, reached from "
            f"{fw['handler']['reached_from']}.", "", "```"]
    out += fw["handler"]["listing"]
    out += ["```", "", _sentence(fw["acceptance"]["note"]), "",
            f"**Persistence.** The field is "
            f"{fw['persistence']['field']}, covered by "
            f"{fw['persistence']['checksum_coverage']} of the profile block's "
            f"two checksums — {fw['persistence']['checksum_ranges']}. "
            f"{_sentence(fw['persistence']['corrects'])} "
            f"{_sentence(fw['persistence']['reload_path'])}.", "",
            f"**Read-back.** `{fw['get_command']['command']}` at "
            f"`{fw['get_command']['address']}` returns the index in reply byte "
            f"4. Confidence: {fw['get_command']['confidence']} — "
            f"{fw['get_command']['kind_basis']}.", "",
            f"**The consumer.** {fw['consumer']['verdict']}", "",
            f"**Units — attached now.** {_sentence(fw['units']['attached_now'])}",
            "",
            f"**Units — still unresolved.** "
            f"{_sentence(fw['units']['still_unresolved'])}", "",
            "## Traffic an application must tolerate", "",
            d["background"]["verdict"], "",
            "| address | device | frames | share |", "|---|---|---|---|"]
    for o in d["background"]["other_devices"]:
        out.append(f"| {o['address']} | `{o['device']}` | {o['frames']} | "
                   f"{o['share']:.1%} |")
    out += ["", "## NEVER SEND without explicit owner approval", "",
            "| frame | why |", "|---|---|"]
    for n in wd["never_send"]:
        out.append(f"| `{n['frame']}` | {n['why']} |")
    out += ["", "Every command below that writes device state is marked "
            "owner-approval-only. The read-only queries are safe to issue.", "",
            "| command | kind | meaning | approval |", "|---|---|---|---|"]
    for c in wd["commands"]:
        out.append(f"| `{c['command']}` | {c['kind']} | {c['meaning']} | "
                   f"{'**required**' if c['owner_approval_required'] else 'no'} |")
    out += ["", "## The uncertainties", "", "| # | question | resolution |",
            "|---|---|---|"]
    for u in d["uncertainties"]:
        out.append(f"| {u['key']} | {u['question']} | {u['resolution']} |")
    out += ["", "## Checks", "", "| | check | detail |", "|---|---|---|"]
    for c in d["checks"]:
        out.append(f"| {'PASS' if c['ok'] else 'FAIL'} | {c['label']} | "
                   f"{c['detail']} |")
    s = d["summary"]
    out += ["", f"`RESULT polling_rate_protocol_ok={s['ok']} "
                f"checks={s['checks']}`", ""]
    return "\n".join(out)


def bodies():
    return {
        "polling-rate-protocol.json": json.dumps(to_dict(), indent=2,
                                                 sort_keys=True) + "\n",
        "polling-rate-protocol.md": markdown(),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = bodies()
    except (OSError, CaptureError, subprocess.CalledProcessError,
            ValueError, KeyError) as exc:
        print(f"RESULT polling_rate_protocol_ok=False error={exc}")
        return 1
    if args.check:
        stale = [name for name, body in payload.items()
                 if not (NOTES / name).exists()
                 or (NOTES / name).read_text() != body]
        print(f"RESULT reports_current={not stale} stale={len(stale)}"
              + ("" if not stale else " " + ", ".join(stale)))
        return 0 if not stale else 1
    if args.write:
        for name, body in payload.items():
            path = NOTES / name
            if not path.exists() or path.read_text() != body:
                path.write_text(body)
                print(f"WROTE notes/{name}")
        return 0
    if args.json:
        print(payload["polling-rate-protocol.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(c["ok"] for c in verify()) else 1


if __name__ == "__main__":
    sys.exit(main())
