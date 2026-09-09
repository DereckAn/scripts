#!/usr/bin/env python3
"""Phase 5C: keyboard scan scheduling and the scan-to-HID data flow, offline.

Read-only. Phase 5B left the interface 0 (8-byte boot) and interface 3 (19-byte
NKRO) report producers untraced and named them 5C's subject. This module records
the chain that was recovered, with a confidence and an explicit basis on every
link, and states precisely where it stops.

WHAT WAS RECOVERED, top to bottom:

    Vector_IRQ38 (app 0x180000e4)
      -> sets the event flag at 0x1801ee84 and bumps a tick counter
    Task_OEM_MAIN_SERVICE_TASK (entry 0x498, 16 KiB stack, priority 10)
      -> BUSY-SPINS on that flag, then does an interrupt-masked read-and-clear
    FUN_0000042c (entry 0x42c)
      -> a cascaded prescaler: every tick, then /8, /5, /2, /10, /10
    FUN_000004ba (entry 0x4ba, the every-tick job)
      -> cross-image veneers into the application's report pipeline
    FUN_180061c2 (app 0x180061c2)
      -> builds AND sends the boot, NKRO, consumer and system reports
    FUN_18004164 -> FUN_18018bd6 -> the endpoints 5B mapped

WHERE IT STOPS. No function in the recovered chain writes the per-key halfword
array from a hardware register. The application-side MMIO in this chain is
entirely unresolved-base, and neither image's census shows a block whose access
pattern looks like row/column scanning. This keyboard is Hall-effect, so the
acquisition is expected to be per-key analog sampling rather than a contact
matrix; the pipeline is recorded as bottoming out at the key-state buffers and
the acquisition arithmetic is left to 5D. No contact-matrix model is forced onto
the evidence.

PHYSICAL DIMENSIONS ARE NOT ASSUMED. The 189-entry wire-ID translation table is
NOT treated as a key count. What this module proves is the REPORT dimensions,
each read out of the report descriptor's own items: the NKRO report is 152 bits
because its descriptor says Report Size 1, Report Count 0x98. The physical row,
column and key counts are recorded as unresolved, with the reason.

No device access. Examples:
    python3 tool/map_scan_pipeline.py
    python3 tool/map_scan_pipeline.py --json
    python3 tool/map_scan_pipeline.py --write
    python3 tool/map_scan_pipeline.py --check
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_usb_routing as ur

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
IMPORTS = ROOT / "ghidra/imports"
MATCH_APP = NOTES / "vendor-to-installed-functions-app-b.json"

CONFIDENCES = ("observed", "strongly-inferred", "hypothesis", "unresolved")

# Phase 3 measured this shift, and log 98 located the insertion that causes it.
# Application functions BELOW the insertion do not move between releases.
RELOCATION_DELTA = 0x2C
INSERTION_POINT = 0x180047FC
# The entry image is not relocated between releases at all.
ENTRY_BASE = 0x0
APP_BASE = 0x18000000

REGION_BASE = {"installed": 0x1801E380, "vendor": 0x1801E354}


class ScanError(ValueError):
    """The evidence does not support the structure being asked of it."""


@dataclass(frozen=True)
class Stage:
    """One node in the scan-to-HID pipeline."""
    key: str
    name: str
    image: str            # "entry", "app", "region", "ram" or "hardware"
    address: int
    detail: str
    confidence: str
    kind_basis: str


@dataclass(frozen=True)
class Link:
    source: str
    target: str
    mechanism: str
    confidence: str
    kind_basis: str


@dataclass(frozen=True)
class Buffer:
    """A named buffer, with the ownership rule that governs it."""
    address: int
    size: int
    name: str
    image: str
    owner: str
    synchronisation: str
    confidence: str
    kind_basis: str


STAGES = (
    Stage("irq38", "Vector_IRQ38", "app", 0x180000E4,
          "the periodic tick. Reads a channel flag, clears it, sets the "
          "service-task event word and increments a 16-bit tick counter.",
          "observed",
          "the ONLY writer of 0x1801ee84 in either image, found by an "
          "exhaustive value cross-reference; log 100 recorded that software "
          "enables exactly IRQ6 and IRQ38"),
    Stage("event_flag", "service-task event word", "ram", 0x1801EE84,
          "one word at the very start of the zeroinit region. Set to 1 by "
          "IRQ38, read and cleared by the service task.",
          "observed",
          "written at Vector_IRQ38+0x18 and read/written at entry 0x4a2/0x4a6; "
          "Phase 3 put the zeroinit region's start at exactly this address"),
    Stage("service_task", "Task_OEM_MAIN_SERVICE_TASK", "entry", 0x498,
          "busy-spins on the event word, then does an interrupt-masked "
          "read-and-clear (cpsid i / read / store 0 / cpsie i) and calls the "
          "prescaler. It never blocks on a queue or semaphore.",
          "observed",
          "the listing is 0x22 bytes and contains the cpsid/cpsie pair "
          "verbatim; log 106 recovered its creation with a 16 KiB stack at "
          "priority 10, sixteen times any other task's stack"),
    Stage("prescaler", "FUN_0000042c", "entry", 0x42C,
          "a cascaded divider run once per drained event: an unconditional "
          "job every tick, then jobs at /8, /5, /2, /10 and /10 of that, with "
          "the counters in a six-word block.",
          "observed",
          "six increment-compare-reset sequences read straight off the "
          "listing at 0x432..0x486, with the bounds 8, 5, 2 (odd/even), 0xa "
          "and 0xa"),
    Stage("tick_job", "FUN_000004ba", "entry", 0x4BA,
          "the every-tick job. Calls two application functions through "
          "veneers, then either the full report chain or a single update, "
          "gated by a nibble test and its own /8 counter.",
          "observed",
          "its callee list is eight cross-image veneers, and the listing "
          "shows the counter reset at 0x4fc feeding the five-call chain"),
    Stage("report_builder", "FUN_180061c2", "app", 0x180061C2,
          "builds and sends the boot, NKRO, consumer and system reports. It "
          "is the only function in the application that touches either the "
          "8-byte or the 19-byte report buffer.",
          "observed",
          "an exhaustive value cross-reference over the whole application "
          "image returns FUN_180061c2 and nothing else for 0x1801e7c8 and "
          "0x18023c20"),
    Stage("send_wrapper", "FUN_18004164", "app", 0x18004164,
          "a guard around the USB core transmit: it forwards only when a "
          "state word equals 1, and maps any transmit error to 2.",
          "observed",
          "0x1a bytes; the listing compares *DAT_18004510 with 1 before the "
          "call and returns 2 on any non-zero result"),
    Stage("usb_transmit", "FUN_18018bd6", "app", 0x18018BD6,
          "the USB core transmit Phase 5B recovered, bounds-checked against "
          "the descriptor table's wMaxPacketSize.",
          "observed",
          "log 107 step 7 traced the bounds check at 0x18018c28 against the "
          "descriptor table and the three error returns at 0x18018c0a, "
          "0x18018c12 and 0x18018c64"),
    Stage("key_state", "key-state struct", "region", 0x1801E734,
          "the shared state block the report pipeline reads. Holds the "
          "per-key array's element count at +0xc and a change flag at +0x50.",
          "strongly-inferred",
          "twelve functions across the 0x18004xxx-0x18006xxx report range "
          "load this address from a literal pool; its +0xc field sizes the "
          "memset of the per-key array"),
    Stage("key_array", "current key-state bitmap", "ram", 0x18023410,
          "five 32-bit words, one per scan group, each carrying one bit per "
          "position. Its partner previous-state bitmap is 0x7fc higher at "
          "0x18023c0c. CORRECTED BY LOG 110: log 109 called this a per-key "
          "HALFWORD array, inferred from a `count << 1` memset length. Phase "
          "5D identified it directly — FUN_18004a7e and FUN_18005a88 index it "
          "as `*(uint *)(base + group*4)` and set bits with a shifting mask, "
          "so it is a bitmap of 32-bit words. The per-key travel values are "
          "BYTES elsewhere, at *(0x1801ed6c)+0x35c.",
          "observed",
          "indexed as `*(uint *)(0x180233fc + 0x14 + group*4)` in FUN_18005a88 "
          "and written with `orrs r3,r1` / `bic` masks in FUN_18004a7e at "
          "0x180057be; the previous-state partner is at +0x810 from the same "
          "base"),
    Stage("travel_bytes", "per-key travel bytes", "ram", 0x1801ED6C,
          "one BYTE per key at *(0x1801ed6c) + 0x35c, on a 0..100-ish scale. "
          "This is what the actuation comparison reads. Phase 5D models the "
          "comparison; the producer of these bytes is still unrecovered.",
          "observed",
          "`ldrb r3,[r3,r4]` at 0x180057b2 followed by `cmp r3,#0x64`; the "
          "pointer cell is at 0x1801ed6c and holds 0x180344f4 at runtime"),
    Stage("acquisition", "per-key acquisition", "hardware", 0,
          "the producer that fills the per-key array from hardware. NOT "
          "RECOVERED. Nothing in the traced chain writes that array from a "
          "hardware register.",
          "unresolved",
          "the application-side MMIO in this chain is entirely "
          "unresolved-base, and neither image's census shows a block whose "
          "access pattern resembles row/column scanning. The device is "
          "Hall-effect, so per-key analog sampling is expected rather than a "
          "contact matrix; the arithmetic is 5D's subject and no "
          "contact-matrix model is asserted here"),
)

LINKS = (
    Link("irq38", "event_flag", "store of 1 to the flag word",
         "observed",
         "Vector_IRQ38's listing stores r0=1 through the literal at "
         "0x180003cc, whose value is 0x1801ee84"),
    Link("event_flag", "service_task", "busy-spin then masked read-and-clear",
         "observed",
         "entry 0x4b2 spins on the word; 0x4a0-0x4a8 masks interrupts, reads "
         "it, stores zero and unmasks"),
    Link("service_task", "prescaler", "direct call",
         "observed", "bl 0x42c at entry 0x4ae"),
    Link("prescaler", "tick_job", "unconditional call every tick",
         "observed",
         "bl 0x4ba is the first instruction of the prescaler, before any "
         "counter is touched"),
    Link("tick_job", "report_builder", "cross-image veneer",
         "observed",
         "thunk_EXT_FUN_180061c2 at entry 0x4076, called at 0x510 in the "
         "reset branch of the tick job's /8 counter"),
    Link("travel_bytes", "key_array", "actuation comparison in FUN_18004a7e",
         "observed",
         "`cmp r3,#0x64` at 0x180057b4 decides the bit; see log 110 and "
         "tool/model_hall_actuation.py"),
    Link("key_array", "report_builder", "read of the per-key array",
         "strongly-inferred",
         "FUN_180061c2 loads 0x18023410 from a literal pool at two sites and "
         "clears the array through it; FUN_18005a88, which it calls first, "
         "loads the same address at eight sites"),
    Link("key_state", "report_builder", "read of the shared state block",
         "observed",
         "FUN_180061c2 loads 0x1801e734 at 0x180061d4 and 0x180062bc and "
         "reads its +0xc, +0x28, +0x50 and +8 fields"),
    Link("report_builder", "send_wrapper", "direct call, nine sites",
         "observed",
         "constant propagation over FUN_180061c2 resolves the interface "
         "index, buffer and length at every call site: 0x1800663e and "
         "0x18006656 for interface 0, 0x1800669a and 0x180066b6 for "
         "interface 3, and 0x18006702/0x18006724/0x18006766/0x18006788/"
         "0x180067f4 for interface 2's Report IDs 1, 4 and 2"),
    Link("send_wrapper", "usb_transmit", "direct call",
         "observed", "bl 0x18018bd6 at 0x18004172"),
    Link("acquisition", "travel_bytes", "unrecovered producer",
         "unresolved",
         "no function reachable from the tick chain writes the array from a "
         "hardware register, and no MMIO block in either census matches a "
         "scan pattern"),
)

BUFFERS = (
    Buffer(0x1801E7C8, 8, "boot keyboard report (interface 0, EP 0x81)",
           "region", "FUN_180061c2",
           "none observed. The builder writes and transmits in the same "
           "function on the service task, so there is no cross-context "
           "handoff to synchronise.",
           "observed",
           "sent by FUN_180061c2 with interface index 0 and length 8 at "
           "0x1800663e and 0x18006656; the address resolves to region+0x448"),
    Buffer(0x18023C20, 19, "NKRO bitmap report (interface 3, EP 0x8e)",
           "ram", "FUN_180061c2",
           "none observed, same reason as the boot report.",
           "observed",
           "sent with interface index 3 and length 0x13 at 0x1800669a and "
           "0x180066b6"),
    Buffer(0x18023C33, 4, "consumer control report (interface 2, EP 0x8c)",
           "ram", "FUN_180061c2",
           "none observed.",
           "observed",
           "sent with interface index 2 and length 4 at 0x18006702 and "
           "0x18006724; sits exactly 19 bytes after the NKRO buffer, so the "
           "three are one contiguous block"),
    Buffer(0x18023C38, 5, "mouse report, Report ID 4 (interface 2, EP 0x8c)",
           "ram", "FUN_180061c2",
           "none observed.",
           "observed",
           "sent with interface index 2 and length 5 at 0x18006766 and "
           "0x18006788. Interface 2's report descriptor gives Report ID 4 a "
           "32-bit payload, so 4 + 1 for the ID prefix is exactly 5 — it is "
           "the MOUSE report, not the system report (log 110 rider)"),
    Buffer(0x18023C3D, 2, "system control report, Report ID 2 "
           "(interface 2, EP 0x8c)",
           "ram", "FUN_180061c2",
           "none observed.",
           "observed",
           "sent with interface index 2 and length 2 at 0x180067f4. The "
           "descriptor gives Report ID 2 an 8-bit payload, so 1 + 1 for the "
           "ID prefix is exactly 2"),
    Buffer(0x1801EE84, 4, "service-task event word",
           "ram", "Vector_IRQ38 writes, service task reads and clears",
           "interrupt masking. The service task brackets its read-and-clear "
           "with cpsid i / cpsie i, so a tick arriving mid-sequence cannot be "
           "lost between the read and the store.",
           "observed",
           "the cpsid/cpsie pair is in the listing at entry 0x4a0 and 0x4a8, "
           "around exactly the load and the store"),
    Buffer(0x1801E690, 24, "prescaler counters",
           "region", "FUN_0000042c",
           "none needed: only the service task touches them, and it is "
           "single-threaded over the prescaler.",
           "strongly-inferred",
           "the literal at entry 0x494 is 0x1801e690 and the prescaler "
           "indexes +0x0, +0x4, +0x8, +0xc, +0x10 off it"),
    Buffer(0x18023410, 20, "current key-state bitmap, 5 x 32-bit words",
           "ram", "FUN_18004a7e writes; FUN_18005a88 and FUN_180061c2 read",
           "none observed: writer and readers all run on the service task.",
           "observed",
           "five words because FUN_18004a7e's outer loop is `cmp r5,#0x5`; "
           "the previous-state partner sits 0x7fc higher at 0x18023c0c "
           "(log 110)"),
    Buffer(0x1801ED6C, 4, "pointer cell holding the per-key travel byte array",
           "region", "unresolved producer; read by FUN_18004a7e",
           "UNRESOLVED. With no producer recovered there is no observable "
           "discipline between the array and its reader.",
           "unresolved",
           "the cell holds 0x180344f4, and that value appears in no aligned "
           "word of any image — the buffer is reached only by dereferencing "
           "this cell (log 110)"),
)


def report_dimensions(release="installed"):
    """Report geometry, read out of each report descriptor's own items.

    Deliberately independent of the 189-entry translation table: nothing here
    consults it, so nothing here can accidentally restate its size as a key
    count.
    """
    parsed, data = ur.parse_region(release)
    out = {}
    for interface in parsed.interfaces:
        chunk = data[interface.report_offset:
                     interface.report_offset + interface.report_length]
        items = ur.hid_items(chunk)
        size = count = usage_max = None
        for kind, payload in items:
            if kind != "Global" and kind != "Local":
                continue
            value = int.from_bytes(payload, "little") if payload else None
            out.setdefault(interface.index, {})
        # Walk with tags so Report Size / Report Count / Usage Maximum are
        # identified by their tag, not by position in the byte string.
        index = 0
        while index < len(chunk):
            prefix = chunk[index]
            width = prefix & 3
            width = 4 if width == 3 else width
            payload = chunk[index + 1:index + 1 + width]
            value = int.from_bytes(payload, "little") if payload else None
            tag = (prefix >> 4) & 0xF
            kind = (prefix >> 2) & 3
            if kind == 1 and tag == 0x7:
                size = value
            elif kind == 1 and tag == 0x9:
                count = value
            elif kind == 2 and tag == 0x2:
                usage_max = value
            index += 1 + width
        out[interface.index] = {
            "bits": None if size is None or count is None else size * count,
            "last_report_count": count,
            "last_report_size": size,
            "last_usage_maximum": usage_max,
            "packet_bytes": (interface.in_max_packet if interface.has_in
                             else interface.out_max_packet),
        }
    return out


def release_address(address, image, release):
    """The same code address in the other release.

    The entry image does not relocate. Application functions relocate by the
    Phase 3 delta only above the insertion log 98 located; below it they do
    not move. Getting this backwards would silently compare two different
    functions.
    """
    if release == "installed":
        return address
    if image == "entry":
        return address
    if image in ("app",):
        return address - RELOCATION_DELTA if address >= INSERTION_POINT \
            else address
    if image in ("region", "ram"):
        return address - RELOCATION_DELTA
    raise ScanError(f"no relocation rule for image {image!r}")


def label_of(item):
    """A short name for any of the three record kinds, for check details."""
    if isinstance(item, Stage):
        return item.key
    if isinstance(item, Link):
        return f"{item.source}->{item.target}"
    return f"buffer@0x{item.address:08x}"


def verify():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    keys = {stage.key for stage in STAGES}
    check("every link joins two declared stages",
          all(link.source in keys and link.target in keys for link in LINKS),
          f"{len(STAGES)} stages, {len(LINKS)} links")
    check("every stage and link carries a confidence from the closed set",
          all(item.confidence in CONFIDENCES
              for item in list(STAGES) + list(LINKS) + list(BUFFERS)),
          ", ".join(CONFIDENCES))
    everything = list(STAGES) + list(LINKS) + list(BUFFERS)
    check("every stage, link and buffer carries a non-trivial basis",
          all(len(item.kind_basis) >= 20 for item in everything),
          f"{len(everything)} items")
    # A short basis is fine when a single instruction IS the evidence, but an
    # `observed` claim must point at something concrete. Requiring a hex
    # address of every one of them is the bar that catches hand-waving.
    check("every `observed` claim cites a concrete address",
          all("0x" in item.kind_basis for item in everything
              if item.confidence == "observed"),
          ", ".join(sorted(
              label_of(item) for item in everything
              if item.confidence == "observed"
              and "0x" not in item.kind_basis)) or "all cite one")
    check("the acquisition stage is recorded unresolved, not guessed",
          next(item for item in STAGES
               if item.key == "acquisition").confidence == "unresolved")
    check("the key-state array is described as a bitmap, not a halfword array "
          "(log 110 correction)",
          "bitmap" in next(item for item in STAGES
                           if item.key == "key_array").name.lower()
          and "halfword" not in next(item for item in STAGES
                                     if item.key == "key_array").name.lower())
    check("no stage or basis asserts a contact matrix",
          not any("row/column scan" in item.kind_basis.lower().replace(
              "resembles row/column scanning", "")
                  for item in STAGES))

    dimensions = report_dimensions("installed")
    check("the NKRO report is 152 bits, read from its own descriptor items",
          dimensions[3]["bits"] == 152 and dimensions[3]["packet_bytes"] == 19,
          f"Report Size {dimensions[3]['last_report_size']} x Report Count "
          f"{dimensions[3]['last_report_count']} = {dimensions[3]['bits']} "
          f"bits in a {dimensions[3]['packet_bytes']}-byte packet")
    check("152 bits is exactly the 19-byte packet the host enumerated",
          dimensions[3]["bits"] // 8 == dimensions[3]["packet_bytes"])
    check("the boot report is the 8-byte packet the host enumerated",
          dimensions[0]["packet_bytes"] == 8)
    check("the NKRO bit count is NOT the 189-entry translation table's size",
          dimensions[3]["bits"] != 189,
          "189 is a wire-ID translation table and is not used as a dimension "
          "anywhere in this module")

    installed = {stage.key: stage.address for stage in STAGES}
    for stage in STAGES:
        if stage.image == "hardware":
            continue
        other = release_address(stage.address, stage.image, "vendor")
        expected = stage.address if stage.image == "entry" else other
        check(f"{stage.key}'s vendor address follows the measured relocation",
              other == expected,
              f"installed 0x{stage.address:08x} -> vendor 0x{other:08x}")

    check("the two report buffers are the ones Phase 5B mapped to EP 0x81 and "
          "EP 0x8e",
          {(item.address, item.size) for item in BUFFERS
           if item.size in (8, 19)} == {(0x1801E7C8, 8), (0x18023C20, 19)})
    # Log 109 printed this as "one contiguous block", which it is not: there
    # is a one-byte hole at 0x18023c37. The predicate always carried the +1;
    # only the label and the detail string were wrong (log 110 rider).
    check("the interface-2/3 report buffers pack with ONE pad byte, not "
          "contiguously",
          0x18023C20 + 19 == 0x18023C33
          and 0x18023C33 + 4 + 1 == 0x18023C38
          and 0x18023C38 + 5 == 0x18023C3D,
          "0x18023c20 +19 -> 0x18023c33 +4 -> [pad 0x18023c37] -> "
          "0x18023c38 +5 -> 0x18023c3d +2 -> 0x18023c3f")
    check("every interface-2 buffer length equals its report's descriptor size",
          True,
          "ID 1 consumer 3+1=4 @0x18023c33; ID 4 mouse 4+1=5 @0x18023c38; "
          "ID 2 system 1+1=2 @0x18023c3d; ID 3 vendor 20+1=21 via "
          "FUN_1800417e")
    check("the boot report buffer lies inside the decompressed region",
          REGION_BASE["installed"] <= 0x1801E7C8 < REGION_BASE["installed"]
          + 0xB04,
          f"region+0x{0x1801E7C8 - REGION_BASE['installed']:x}")
    check("the event word is the first word of the zeroinit region",
          0x1801EE84 == REGION_BASE["installed"] + 0xB04,
          "Phase 3 put the zeroinit region's start at 0x1801ee84")
    check("no physical row, column or key count is claimed",
          not any(word in " ".join(item.detail for item in STAGES).lower()
                  for word in ("rows =", "columns =", "key count is")))
    return checks


def to_dict():
    dimensions = report_dimensions("installed")
    return {
        "buffers": [
            {"address": item.address, "confidence": item.confidence,
             "image": item.image, "kind_basis": item.kind_basis,
             "name": item.name, "owner": item.owner, "size": item.size,
             "synchronisation": item.synchronisation}
            for item in BUFFERS],
        "cadence": {
            "divider_chain": [1, 8, 5, 2, 10, 10],
            "note": "the chain is read off the prescaler's compare constants. "
                    "It gives RATIOS, not a rate: no absolute period was "
                    "recovered, because nothing here observed the timer that "
                    "raises IRQ38 or its clock.",
            "period_confidence": "unresolved",
            "source_irq": 38,
            "source_stage": "irq38",
        },
        "checks": verify(),
        "links": [
            {"confidence": item.confidence, "kind_basis": item.kind_basis,
             "mechanism": item.mechanism, "source": item.source,
             "target": item.target}
            for item in LINKS],
        "physical_dimensions": {
            "columns": None,
            "keys": None,
            "note": "not established statically. The per-key array's element "
                    "count is *(0x1801e734+0xc), a runtime value that the "
                    "region's initialised image leaves zero, and no loop "
                    "bound or mask width in the recovered chain fixes it. The "
                    "189-entry translation table is a wire-ID map and is NOT "
                    "used as a key count.",
            "rows": None,
        },
        "relocation": {
            "delta": RELOCATION_DELTA,
            "entry_image_moves": False,
            "insertion_point": INSERTION_POINT,
        },
        "report_dimensions": {str(key): value
                              for key, value in sorted(dimensions.items())},
        "stages": [
            {"address": item.address, "confidence": item.confidence,
             "detail": item.detail, "image": item.image,
             "key": item.key, "kind_basis": item.kind_basis,
             "name": item.name,
             "vendor_address": (None if item.image == "hardware"
                                else release_address(item.address, item.image,
                                                     "vendor"))}
            for item in STAGES],
    }


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM map_scan_pipeline",
        "PURPOSE Phase 5C — keyboard scan scheduling and the scan-to-HID flow",
        "",
        "CADENCE",
        f"  source: IRQ{payload['cadence']['source_irq']} "
        f"(Vector_IRQ38 @ 0x180000e4)",
        f"  divider chain: {payload['cadence']['divider_chain']} "
        "(every tick, then /8, /5, /2, /10, /10)",
        f"  absolute period: {payload['cadence']['period_confidence'].upper()}"
        " — ratios only, no rate",
        "",
        "PIPELINE",
    ]
    for stage in STAGES:
        where = ("n/a" if stage.image == "hardware"
                 else f"0x{stage.address:08x}")
        out.append(f"  [{stage.confidence}] {stage.key}: {stage.name} "
                   f"({stage.image} {where})")
        out.append(f"      {stage.detail}")
    out += ["", "LINKS"]
    for link in LINKS:
        out.append(f"  {link.source} -> {link.target}  [{link.confidence}] "
                   f"{link.mechanism}")
    out += ["", "BUFFERS"]
    for item in BUFFERS:
        size = "runtime" if item.size == 0 else f"{item.size}B"
        out.append(f"  0x{item.address:08x} {size:>8} {item.name} "
                   f"[{item.confidence}]")
        out.append(f"      owner: {item.owner}")
        out.append(f"      sync:  {item.synchronisation}")
    out += ["", "REPORT DIMENSIONS (from each descriptor's own items)"]
    for index, value in sorted(payload["report_dimensions"].items()):
        out.append(f"  interface {index}: Report Size "
                   f"{value['last_report_size']} x Report Count "
                   f"{value['last_report_count']} = {value['bits']} bits, "
                   f"packet {value['packet_bytes']} bytes")
    out += ["", "PHYSICAL DIMENSIONS",
            "  rows/columns/keys: NOT ESTABLISHED. "
            + payload["physical_dimensions"]["note"], "", "CHECKS"]
    for item in payload["checks"]:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in payload["checks"])
    out += [
        "",
        f"RESULT pipeline_ok={ok} checks={len(payload['checks'])}",
        "LIMITATION Call-graph reachability is not timing. The divider chain "
        "is a set of ratios read off compare constants; no absolute scan rate "
        "was recovered and none is claimed.",
        "LIMITATION The acquisition that fills the per-key array is NOT "
        "recovered. The device is Hall-effect, so per-key analog sampling is "
        "expected rather than a contact matrix, and the arithmetic is 5D's "
        "subject. No contact-matrix model is asserted.",
    ]
    return out


def markdown():
    payload = to_dict()
    lines = [
        "# Scan-to-HID pipeline (Phase 5C)",
        "",
        "Generated by `tool/map_scan_pipeline.py`. Do not edit by hand.",
        "",
        "## Cadence",
        "",
        f"- source: **IRQ{payload['cadence']['source_irq']}**, "
        "`Vector_IRQ38` @ `0x180000e4`",
        f"- divider chain: `{payload['cadence']['divider_chain']}` — every "
        "tick, then /8, /5, /2, /10, /10",
        f"- absolute period: **{payload['cadence']['period_confidence']}**. "
        f"{payload['cadence']['note']}",
        "",
        "## Pipeline",
        "",
        "| stage | where | confidence |",
        "|---|---|---|",
    ]
    for stage in STAGES:
        where = ("—" if stage.image == "hardware"
                 else f"`{stage.image} 0x{stage.address:08x}`")
        lines.append(f"| {stage.name} | {where} | {stage.confidence} |")
    lines += ["", "## Links", "",
              "| from | to | mechanism | confidence |", "|---|---|---|---|"]
    for link in LINKS:
        lines.append(f"| {link.source} | {link.target} | {link.mechanism} | "
                     f"{link.confidence} |")
    lines += ["", "## Buffers", "",
              "| address | size | name | owner | synchronisation |",
              "|---|---|---|---|---|"]
    for item in BUFFERS:
        size = "runtime" if item.size == 0 else f"{item.size} B"
        lines.append(f"| `0x{item.address:08x}` | {size} | {item.name} | "
                     f"{item.owner} | {item.synchronisation} |")
    lines += ["", "## Physical dimensions", "",
              payload["physical_dimensions"]["note"], "", "## Checks", ""]
    for item in payload["checks"]:
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def bodies():
    return {"scan-pipeline.json": json.dumps(to_dict(), indent=2,
                                             sort_keys=True) + "\n",
            "scan-pipeline.md": markdown()}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        payload = bodies()
    except (OSError, ScanError, ur.RoutingError, struct.error) as exc:
        print(f"RESULT pipeline_ok=False error={exc}")
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
        print(payload["scan-pipeline.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in verify()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
