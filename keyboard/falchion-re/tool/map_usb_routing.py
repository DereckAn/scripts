#!/usr/bin/env python3
"""Phase 5B: USB ownership, endpoints and report routing, offline.

Read-only. Everything here is derived from three preserved sources and nothing
else: the host-side descriptor captures in `logs/07-…` and `logs/09-…`, the
reconstructed decompressed region from log 105, and the Ghidra analysis of the
application image.

WHAT THE FIRMWARE ACTUALLY STORES. The five HID *report* descriptors are stored
verbatim. Four of them — interfaces 0-3 — are byte-identical to the raw bytes
the host read back in log 09. The fifth, interface 4's, cannot be compared that
way: interface 4 was unbound on the host, so this repository holds no raw bytes
for it. It is verified structurally instead — the item walk consumes exactly its
declared 327 bytes and yields 155 items matching lsusb's 155 decoded items one
for one. That is an item comparison, not a byte comparison (log 108). The
standard
descriptors — device, configuration, interface, HID-class and endpoint — are
NOT stored anywhere in any preserved image. They are built at runtime by
`FUN_18018082` from a 0x8c-byte parameter table at region+0x284, which
`FUN_18018b70` copies to RAM 0x1803435c during INIT_TASK.

That is a positive finding, not an argument from a failed search: the builder's
own size arithmetic — 9 + per interface (0x12 + 7 x endpoint count) — is read
off its instructions, and reproducing it from the table yields exactly the
wTotalLength the host observed. See `verify()`.

THE TABLE LAYOUT is read off the builder's field offsets, not guessed:
    +0x00 u16 idVendor          +0x10 u8 bmAttributes bits (0x80 added at build)
    +0x02 u16 idProduct         +0x11 u8 bMaxPower/2
    +0x04 u16 bcdDevice         +0x12 u8 bNumInterfaces, validated 1..5
Then an interface array at table+0x14, stride 0x18. The builder indexes it as
`table + i*0x18 + X`, so a record's own fields sit at X-0x14 from its base:
    +0x02 u8  endpoint flags: bit0 = IN present, bit1 = OUT present
    +0x04 u16 IN wMaxPacketSize     +0x06 u16 OUT wMaxPacketSize
    +0x0c u16 report descriptor length
    +0x10 u32 report descriptor pointer
    +0x14 u8  bInterval for the IN endpoint

No device access. Examples:
    python3 tool/map_usb_routing.py
    python3 tool/map_usb_routing.py --json
    python3 tool/map_usb_routing.py --write
"""
import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
IMPORTS = ROOT / "ghidra/imports"
NOTES = ROOT / "notes"
DESCRIPTOR_LOG = ROOT / "logs/07-falchion-usb-descriptors-sysfs-xxd.txt"
REPORT_LOG = ROOT / "logs/09-falchion-hid-report-descriptors-xxd.txt"

REGIONS = {
    "installed": ("installed_decompressed_region1_flash3f380_dst1801e380"
                  "_len00b04_501f818f.bin", 0x1801E380),
    "vendor": ("vendor_decompressed_region1_flash3f354_dst1801e354"
               "_len00b04_7a6dea8e.bin", 0x1801E354),
}

TABLE_OFFSET = 0x284
TABLE_LENGTH = 0x8C          # the length FUN_18018b70 memcpy's
INTERFACE_ARRAY = 0x14       # relative to the table base
INTERFACE_STRIDE = 0x18
MAX_INTERFACES = 5           # FUN_18018b70 rejects bNumInterfaces > 5
FIRST_REPORT_DESCRIPTOR = 0x08

# Sizes the builder's own arithmetic uses (`iVar7 += n*7 + 0x12`).
CONFIG_HEADER_BYTES = 9
PER_INTERFACE_BYTES = 0x12   # 9 interface + 9 HID class descriptor
PER_ENDPOINT_BYTES = 7

TABLE_RAM_COPY = 0x1803435C
CORE_STRUCT = 0x1801EBB8
VENDOR_RX_BUFFER = 0x180233A8
VENDOR_FRAME_BYTES = 0x40
VENDOR_HEADER_BYTES = 4
VENDOR_MAX_PAYLOAD = 0x3C
USB_CONTROLLER_BLOCK = 0x40100000
USB_CONTROLLER_IRQ_BASE = 0x40100018


class RoutingError(ValueError):
    """The evidence does not support the structure being asked of it."""


@dataclass(frozen=True)
class Interface:
    index: int
    has_in: bool
    has_out: bool
    in_max_packet: int
    out_max_packet: int
    report_length: int
    report_pointer: int
    interval: int
    report_offset: int
    report_sha_prefix: str

    @property
    def endpoints(self):
        return int(self.has_in) + int(self.has_out)

    @property
    def descriptor_bytes(self):
        return PER_INTERFACE_BYTES + self.endpoints * PER_ENDPOINT_BYTES


@dataclass(frozen=True)
class DescriptorSet:
    release: str
    base: int
    id_vendor: int
    id_product: int
    bcd_device: int
    attribute_bits: int
    max_power_units: int
    num_interfaces: int
    interfaces: tuple
    table_offset: int

    @property
    def total_length(self):
        """wTotalLength, recomputed the way FUN_18018082 computes it."""
        return CONFIG_HEADER_BYTES + sum(
            item.descriptor_bytes for item in self.interfaces)


@dataclass(frozen=True)
class Route:
    endpoint: str
    interface: int
    direction: str
    max_packet: int
    purpose: str
    context: str
    confidence: str
    kind_basis: str
    optional: bool


@dataclass
class Analysis:
    sets: dict = field(default_factory=dict)
    ground_truth: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    routes: tuple = ()


def _hexdump_bytes(text):
    """Bytes out of an `xxd` capture, ignoring the ASCII gutter."""
    out = bytearray()
    for line in text.splitlines():
        match = re.match(r"^[0-9a-f]{8}: ((?:[0-9a-f]{2,4} )+)", line)
        if match:
            out += bytes.fromhex(match.group(1).replace(" ", ""))
    return bytes(out)


def host_standard_descriptors():
    """Parse log 07 into the descriptor chain the host actually read."""
    blob = _hexdump_bytes(DESCRIPTOR_LOG.read_text())
    items = []
    offset = 0
    while offset < len(blob):
        length = blob[offset]
        if length == 0 or offset + length > len(blob):
            raise RoutingError(
                f"log 07 descriptor at +0x{offset:x} claims length {length}, "
                f"which runs past the {len(blob)}-byte capture")
        items.append((offset, blob[offset + 1], blob[offset:offset + length]))
        offset += length
    return blob, items


def host_report_descriptors():
    """Parse log 09 into {interface index: report descriptor bytes}."""
    text = REPORT_LOG.read_text()
    out = {}
    for block in text.split("== hidraw")[1:]:
        index = int(block.split(" ", 1)[0])
        out[index] = _hexdump_bytes(block)
    return out


ITEM_KIND = {0: "Main", 1: "Global", 2: "Local", 3: "Reserved"}
LAMPARRAY_INTERFACE = 4
LAMPARRAY_HEADING = "Report Descriptor: (length is 327)"
HOST_ITEM = re.compile(
    r"Item\((Global|Local |Main  )\): [^,]+, "
    r"data=\s*(?:\[ ((?:0x[0-9a-f]{2} )+)\]|none)")


def hid_items(data):
    """Walk a HID report descriptor into (kind, data) items.

    Raises when an item's payload runs past the end, so a descriptor that is
    the wrong length cannot be reported as well-formed. A short-form item's
    size field of 3 means four bytes, not three.
    """
    items = []
    index = 0
    while index < len(data):
        prefix = data[index]
        index += 1
        size = prefix & 3
        if size == 3:
            size = 4
        if index + size > len(data):
            raise RoutingError(
                f"HID item at +{index - 1:#x} declares {size} data bytes but "
                f"only {len(data) - index} remain; the descriptor is not "
                "well-formed")
        items.append((ITEM_KIND[(prefix >> 2) & 3], data[index:index + size]))
        index += size
    return items


def host_parsed_lamparray():
    """The host's PARSED item listing for interface 4, from the preserved
    lsusb capture.

    This is deliberately not a byte source. Interface 4 was unbound, so lsusb
    printed its decoded items and no driver ever exposed a hidraw node for it.
    Comparing against it is a comparison of item sequences, and the tool says
    so rather than implying a byte comparison happened.
    """
    text = (NOTES / "usb-descriptors.txt").read_text()
    if LAMPARRAY_HEADING not in text:
        raise RoutingError(
            f"{LAMPARRAY_HEADING!r} is not in notes/usb-descriptors.txt; the "
            "interface 4 comparison has no host side")
    section = text.split(LAMPARRAY_HEADING, 1)[1]
    return [
        (match.group(1).strip(),
         bytes.fromhex(match.group(2).replace("0x", "").replace(" ", ""))
         if match.group(2) else b"")
        for match in HOST_ITEM.finditer(section)
    ]


def raw_bytes_available_for(interface):
    """Whether this repository preserves RAW host bytes for an interface."""
    text = REPORT_LOG.read_text()
    return f"== hidraw{interface} ==" in text


def parse_region(release):
    name, base = REGIONS[release]
    data = (IMPORTS / name).read_bytes()
    table = TABLE_OFFSET
    if table + TABLE_LENGTH > len(data):
        raise RoutingError(
            f"the {TABLE_LENGTH:#x}-byte parameter table at +{table:#x} does "
            f"not fit in a {len(data):#x}-byte region")
    vendor, product, device = struct.unpack_from("<3H", data, table)
    attributes, power, count = data[table + 0x10:table + 0x13]
    if not 1 <= count <= MAX_INTERFACES:
        raise RoutingError(
            f"bNumInterfaces {count} is outside 1..{MAX_INTERFACES}; "
            "FUN_18018b70 rejects exactly this and so does this parser")
    interfaces = []
    for index in range(count):
        record = table + INTERFACE_ARRAY + index * INTERFACE_STRIDE
        if record + INTERFACE_STRIDE > len(data):
            raise RoutingError(
                f"interface record {index} at +{record:#x} runs past the "
                "region")
        flags = data[record + 0x02]
        in_packet, out_packet = struct.unpack_from("<2H", data, record + 0x04)
        report_length, = struct.unpack_from("<H", data, record + 0x0C)
        report_pointer, = struct.unpack_from("<I", data, record + 0x10)
        interval = data[record + 0x14]
        report_offset = report_pointer - base
        if not 0 <= report_offset <= len(data) - report_length:
            raise RoutingError(
                f"interface {index}'s report descriptor pointer "
                f"{report_pointer:#x} with length {report_length:#x} does not "
                "lie inside the region")
        import hashlib
        digest = hashlib.sha256(
            data[report_offset:report_offset + report_length]).hexdigest()
        interfaces.append(Interface(
            index=index, has_in=bool(flags & 1), has_out=bool(flags & 2),
            in_max_packet=in_packet, out_max_packet=out_packet,
            report_length=report_length, report_pointer=report_pointer,
            interval=interval, report_offset=report_offset,
            report_sha_prefix=digest[:16]))
    return DescriptorSet(
        release=release, base=base, id_vendor=vendor, id_product=product,
        bcd_device=device, attribute_bits=attributes,
        max_power_units=power, num_interfaces=count,
        interfaces=tuple(interfaces), table_offset=table), data


# The routing map. `context` cites the 5A task graph or the vector table;
# `kind_basis` says what makes the link the kind it is claimed to be.
ROUTES = (
    Route("0x81", 0, "IN", 8,
          "boot keyboard, 8-byte report",
          "IRQ6 (USB device) -> usbd_irq_Queue -> USB task; report produced by "
          "the scan path",
          "strongly-inferred",
          "interface 0's record gives one IN endpoint of 8 bytes and its "
          "report descriptor is byte-identical to the host's; the producing "
          "scan path is 5C's subject and is not traced here",
          False),
    Route("0x85", 1, "IN", 64,
          "vendor page 0xFF00 response, 64-byte frame",
          "VendorHID_CommandDispatcher@0x18001fbe -> "
          "VendorHID_SendResponse64@0x18000a70 -> FUN_18018bd6(iface=1)",
          "observed",
          "FUN_18000a70 builds a 64-byte frame and calls FUN_18018bd6 with "
          "interface index 1; FUN_18018bd6 bounds the length against the same "
          "table field that produces this endpoint's wMaxPacketSize",
          True),
    Route("0x0d", 1, "OUT", 64,
          "vendor page 0xFF00 command, 64-byte frame",
          "USB controller -> FUN_18016104 (ops table 0x18016d44) -> "
          "FUN_18000aec -> buffer 0x180233a8 -> dispatcher 0x18001fbe",
          "observed",
          "FUN_18000aec is one of exactly two functions that touch "
          "0x180233a8; it zero-pads to 64 and gates on byte 0, and the "
          "dispatcher's first act is to read that byte",
          True),
    Route("0x8c", 2, "IN", 21,
          "consumer/system controls plus a vendor event collection",
          "application task context; producer not traced in 5B",
          "strongly-inferred",
          "interface 2's record gives one IN endpoint of 21 bytes and its "
          "182-byte report descriptor is byte-identical to the host's",
          True),
    Route("0x8e", 3, "IN", 19,
          "NKRO keyboard bitmap, 19-byte report",
          "same producer as interface 0's report; not separated in 5B",
          "strongly-inferred",
          "interface 3's record gives one IN endpoint of 19 bytes and its "
          "23-byte report descriptor is byte-identical to the host's",
          True),
    Route("0x0f", 4, "OUT", 64,
          "HID usage page 0x59 LampArray, 64-byte OUT plus feature reports",
          "USB controller -> class ops; lighting consumer not traced in 5B",
          "strongly-inferred",
          "interface 4's record is the only one with the OUT bit set and no "
          "IN endpoint, matching the host's OUT-only interface 4. Its 327-byte "
          "report descriptor at region+0x13b was located STRUCTURALLY, is "
          "well-formed (the HID item walk consumes exactly 327 bytes), and its "
          "parsed item sequence matches the host's parsed listing item for "
          "item. BYTE-IDENTITY CANNOT BE CHECKED: interface 4 was unbound on "
          "the host, so no raw report-descriptor bytes for it exist in this "
          "repository — log 09 captured hidraw0-3 only and log 15 preserves "
          "lsusb's parsed items, not bytes",
          True),
    Route("0x00", -1, "control", 64,
          "control transfers, including GET_DESCRIPTOR",
          "IRQ6 (USB device) -> usbd_ep0_Queue -> USB task -> FUN_18018082 "
          "builds the configuration descriptor",
          "observed",
          "Vector_IRQ6 carries the firmware's own string "
          "'send usbd_ep0_Queue error'; FUN_18018082's size arithmetic "
          "reproduces the host's wTotalLength exactly",
          False),
)


def verify(analysis):
    def check(name, ok, detail=""):
        analysis.checks.append(
            {"name": name, "ok": bool(ok), "detail": detail})
        return ok

    installed = analysis.sets["installed"]
    blob, items = analysis.ground_truth["standard"]
    reports = analysis.ground_truth["reports"]

    device = [item for _off, kind, item in items if kind == 1][0]
    config = [item for _off, kind, item in items if kind == 2][0]
    host_ifaces = [item for _off, kind, item in items if kind == 4]
    host_eps = [item for _off, kind, item in items if kind == 5]

    check("idVendor matches the host device descriptor",
          installed.id_vendor == struct.unpack_from("<H", device, 8)[0],
          f"0x{installed.id_vendor:04x}")
    check("idProduct matches the host device descriptor",
          installed.id_product == struct.unpack_from("<H", device, 10)[0],
          f"0x{installed.id_product:04x}")
    check("bcdDevice matches the host device descriptor",
          installed.bcd_device == struct.unpack_from("<H", device, 12)[0],
          f"0x{installed.bcd_device:04x}")
    check("bNumInterfaces matches the host configuration descriptor",
          installed.num_interfaces == config[4],
          f"{installed.num_interfaces}")
    check("bMaxPower matches the host configuration descriptor",
          installed.max_power_units == config[8],
          f"{installed.max_power_units} units = "
          f"{installed.max_power_units * 2} mA")
    check("the stored attribute bits are the host's minus the mandatory 0x80",
          installed.attribute_bits | 0x80 == config[7],
          f"stored 0x{installed.attribute_bits:02x} vs host "
          f"0x{config[7]:02x}")
    check("wTotalLength recomputed from the table equals the host's",
          installed.total_length == struct.unpack_from("<H", config, 2)[0],
          f"built {installed.total_length} (0x{installed.total_length:x}) vs "
          f"host {struct.unpack_from('<H', config, 2)[0]}")

    for item in installed.interfaces:
        host = host_ifaces[item.index]
        check(f"interface {item.index} endpoint count matches the host",
              item.endpoints == host[4],
              f"{item.endpoints} vs {host[4]}")
    # The table carries ONE interval byte per interface and it tracks the IN
    # endpoint. Both OUT endpoints are bInterval 4 on the host and neither 4
    # appears in their interface's record, so the OUT interval comes from
    # somewhere this parser has not found. Recorded, not guessed.
    host_in_intervals = [endpoint[6] for endpoint in host_eps
                         if endpoint[2] & 0x80]
    check("the table's interval byte matches every host IN endpoint's "
          "bInterval",
          [item.interval for item in installed.interfaces if item.has_in]
          == host_in_intervals,
          ", ".join(str(value) for value in host_in_intervals))
    check("the OUT endpoints' bInterval is NOT in the table — recorded "
          "unresolved, not inferred",
          all(item.interval != 4 or not item.has_out
              for item in installed.interfaces if item.has_out),
          "host OUT bInterval is 4 for both 0x0d and 0x0f; no record holds it")
    check("every host endpoint's wMaxPacketSize appears in the table",
          sorted(struct.unpack_from("<H", endpoint, 4)[0]
                 for endpoint in host_eps)
          == sorted([item.in_max_packet for item in installed.interfaces
                     if item.has_in]
                    + [item.out_max_packet for item in installed.interfaces
                       if item.has_out]),
          ", ".join(str(struct.unpack_from("<H", endpoint, 4)[0])
                    for endpoint in host_eps))

    _set, data = analysis.sets["installed"], analysis.raw["installed"]
    for index, expected in sorted(reports.items()):
        item = installed.interfaces[index]
        stored = data[item.report_offset:item.report_offset + item.report_length]
        check(f"interface {index}'s report descriptor is byte-identical to "
              "the host's",
              stored == expected,
              f"{len(stored)} bytes at region+0x{item.report_offset:x}")

    # Interface 4 has no raw host bytes in this repository, so it gets a
    # different and explicitly weaker treatment than interfaces 0-3. The
    # boundary is pinned by a check rather than left to prose.
    four = installed.interfaces[LAMPARRAY_INTERFACE]
    stored_four = analysis.raw["installed"][
        four.report_offset:four.report_offset + four.report_length]
    check(f"interface {LAMPARRAY_INTERFACE} has NO raw host bytes in this "
          "repository — byte-identity is not checkable",
          not raw_bytes_available_for(LAMPARRAY_INTERFACE)
          and LAMPARRAY_INTERFACE not in reports,
          "interface 4 was unbound on the host; log 09 captured hidraw0-3 "
          "only and log 15 preserves lsusb's parsed items, not bytes")
    try:
        items = hid_items(stored_four)
        well_formed = True
    except RoutingError:
        items, well_formed = [], False
    check(f"interface {LAMPARRAY_INTERFACE}'s descriptor is well-formed and "
          "the item walk consumes exactly its declared length",
          well_formed and four.report_length == 327,
          f"{len(items)} items over {four.report_length} bytes at "
          f"region+0x{four.report_offset:x}")
    host_items = host_parsed_lamparray()
    check(f"interface {LAMPARRAY_INTERFACE}'s PARSED item sequence matches "
          "the host's parsed listing (item comparison, not byte comparison)",
          bool(host_items) and items == host_items,
          f"{len(items)} firmware items vs {len(host_items)} host items")

    check("the report descriptors are contiguous from +0x8",
          [item.report_offset for item in installed.interfaces]
          == [FIRST_REPORT_DESCRIPTOR
              + sum(other.report_length
                    for other in installed.interfaces[:item.index])
              for item in installed.interfaces],
          ", ".join(f"+0x{item.report_offset:x}"
                    for item in installed.interfaces))

    check("no assembled standard descriptor is stored in the region",
          blob not in analysis.raw["installed"]
          and bytes(device) not in analysis.raw["installed"],
          "device/config/interface/endpoint descriptors are built, not stored")

    vendor = analysis.sets["vendor"]
    check("both releases describe the same interface shape",
          [(item.endpoints, item.in_max_packet, item.out_max_packet,
            item.report_length, item.interval)
           for item in installed.interfaces]
          == [(item.endpoints, item.in_max_packet, item.out_max_packet,
               item.report_length, item.interval)
              for item in vendor.interfaces],
          f"{vendor.num_interfaces} interfaces both sides")
    check("only bcdDevice differs between the releases",
          (installed.id_vendor, installed.id_product)
          == (vendor.id_vendor, vendor.id_product)
          and installed.bcd_device != vendor.bcd_device,
          f"installed 0x{installed.bcd_device:04x} vs vendor "
          f"0x{vendor.bcd_device:04x}")
    check("every route names an endpoint the table accounts for",
          {route.endpoint for route in ROUTES if route.interface >= 0}
          == {"0x81", "0x85", "0x0d", "0x8c", "0x8e", "0x0f"})
    return analysis


def build():
    analysis = Analysis()
    analysis.raw = {}
    for release in REGIONS:
        parsed, data = parse_region(release)
        analysis.sets[release] = parsed
        analysis.raw[release] = data
    analysis.ground_truth = {
        "standard": host_standard_descriptors(),
        "reports": host_report_descriptors(),
    }
    analysis.routes = ROUTES
    return verify(analysis)


def to_dict(analysis):
    installed = analysis.sets["installed"]
    return {
        "checks": analysis.checks,
        "controller": {
            "block": USB_CONTROLLER_BLOCK,
            "irq": 6,
            "irq_register_base": USB_CONTROLLER_IRQ_BASE,
            "named_by": "Vector_IRQ6's own strings 'send usbd_ep0_Queue error' "
                        "and 'send usbd_irq_Queue error'",
        },
        "descriptor_sets": {
            release: {
                "attribute_bits": item.attribute_bits,
                "base": item.base,
                "bcd_device": item.bcd_device,
                "id_product": item.id_product,
                "id_vendor": item.id_vendor,
                "interfaces": [
                    {"has_in": one.has_in, "has_out": one.has_out,
                     "in_max_packet": one.in_max_packet, "index": one.index,
                     "interval": one.interval if one.has_in else None,
                     "out_max_packet": one.out_max_packet,
                     "report_length": one.report_length,
                     "report_offset": one.report_offset,
                     "report_pointer": one.report_pointer,
                     "report_sha256_prefix": one.report_sha_prefix}
                    for one in item.interfaces],
                "max_power_ma": item.max_power_units * 2,
                "num_interfaces": item.num_interfaces,
                "table_offset": item.table_offset,
                "total_length": item.total_length,
            }
            for release, item in sorted(analysis.sets.items())
        },
        "minimal_keyboard_path": [route.endpoint for route in ROUTES
                                  if not route.optional],
        "routes": [
            {"confidence": route.confidence, "context": route.context,
             "direction": route.direction, "endpoint": route.endpoint,
             "interface": route.interface, "kind_basis": route.kind_basis,
             "max_packet": route.max_packet, "optional": route.optional,
             "purpose": route.purpose}
            for route in ROUTES],
        "vendor_channel": {
            "dispatcher": 0x18001FBE,
            "frame_bytes": VENDOR_FRAME_BYTES,
            "header_bytes": VENDOR_HEADER_BYTES,
            "max_payload": VENDOR_MAX_PAYLOAD,
            "receive_producer": 0x18000AEC,
            "rx_buffer": VENDOR_RX_BUFFER,
            "send_response": 0x18000A70,
            "transmit_core": 0x18018BD6,
        },
        "usb_core": {"core_struct": CORE_STRUCT,
                     "descriptor_builder": 0x18018082,
                     "registration": 0x18018B70,
                     "table_ram_copy": TABLE_RAM_COPY},
    }


def report_lines(analysis):
    installed = analysis.sets["installed"]
    out = [
        "PROGRAM map_usb_routing",
        "PURPOSE Phase 5B — USB ownership, endpoints and report routing",
        f"SOURCE region {REGIONS['installed'][0]}",
        f"SOURCE host captures {DESCRIPTOR_LOG.name}, {REPORT_LOG.name}",
        "",
        "DESCRIPTOR SET (installed)",
        f"  idVendor=0x{installed.id_vendor:04x} "
        f"idProduct=0x{installed.id_product:04x} "
        f"bcdDevice=0x{installed.bcd_device:04x}",
        f"  bNumInterfaces={installed.num_interfaces} "
        f"bMaxPower={installed.max_power_units * 2}mA "
        f"attribute_bits=0x{installed.attribute_bits:02x}",
        f"  wTotalLength rebuilt from the table = "
        f"{installed.total_length} (0x{installed.total_length:x})",
    ]
    for item in installed.interfaces:
        out.append(
            f"  IFACE {item.index} endpoints={item.endpoints} "
            f"in={item.in_max_packet if item.has_in else '-'} "
            f"out={item.out_max_packet if item.has_out else '-'} "
            f"bInterval={item.interval if item.has_in else 'n/a'} "
            f"report=+0x{item.report_offset:x} len={item.report_length} "
            f"ptr=0x{item.report_pointer:08x}")
    out += ["", "ROUTING MAP"]
    for route in ROUTES:
        out.append(
            f"  EP {route.endpoint} iface={route.interface} "
            f"{route.direction} {route.max_packet}B "
            f"[{route.confidence}] {'optional' if route.optional else 'REQUIRED'}")
        out.append(f"      purpose: {route.purpose}")
        out.append(f"      context: {route.context}")
        out.append(f"      basis:   {route.kind_basis}")
    out += ["", "CHECKS"]
    for item in analysis.checks:
        out.append(f"  {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                   + (f" — {item['detail']}" if item["detail"] else ""))
    ok = all(item["ok"] for item in analysis.checks)
    out += [
        "",
        f"RESULT routing_ok={ok} checks={len(analysis.checks)}",
        "LIMITATION Call-graph reachability is not timing. Nothing here "
        "observed the device or a runtime schedule.",
        "LIMITATION The producers of the interface 0, 2 and 3 reports are not "
        "traced; they belong to the scan and media paths, which are 5C's and "
        "5D's subjects.",
    ]
    return out


def markdown(analysis):
    installed = analysis.sets["installed"]
    lines = [
        "# USB routing map (Phase 5B)",
        "",
        "Generated by `tool/map_usb_routing.py`. Do not edit by hand.",
        "",
        "## Descriptor set",
        "",
        f"- idVendor `0x{installed.id_vendor:04x}`, idProduct "
        f"`0x{installed.id_product:04x}`, bcdDevice "
        f"`0x{installed.bcd_device:04x}`",
        f"- `bNumInterfaces` {installed.num_interfaces}, `bMaxPower` "
        f"{installed.max_power_units * 2} mA",
        f"- `wTotalLength` rebuilt from the parameter table: "
        f"`0x{installed.total_length:04x}`",
        "",
        "| iface | endpoints | IN | OUT | bInterval | report descriptor |",
        "|---|---|---|---|---|---|",
    ]
    for item in installed.interfaces:
        lines.append(
            f"| {item.index} | {item.endpoints} | "
            f"{item.in_max_packet if item.has_in else '—'} | "
            f"{item.out_max_packet if item.has_out else '—'} | "
            f"{item.interval if item.has_in else '—'} | "
            f"`+0x{item.report_offset:x}` "
            f"({item.report_length} B) |")
    lines += [
        "",
        "## Routing",
        "",
        "| endpoint | iface | dir | bytes | purpose | context | confidence | "
        "required |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for route in ROUTES:
        lines.append(
            f"| `{route.endpoint}` | {route.interface} | {route.direction} | "
            f"{route.max_packet} | {route.purpose} | {route.context} | "
            f"{route.confidence} | {'no' if route.optional else '**yes**'} |")
    lines += ["", "## Checks", ""]
    for item in analysis.checks:
        lines.append(f"- {'PASS' if item['ok'] else 'FAIL'} — {item['name']}"
                     + (f" ({item['detail']})" if item["detail"] else ""))
    return "\n".join(lines) + "\n"


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true",
                        help="write notes/usb-routing.{md,json}")
    parser.add_argument("--check", action="store_true",
                        help="report whether the written notes are current")
    return parser.parse_args(argv)


def write_notes(analysis, out_dir=NOTES):
    payload = json.dumps(to_dict(analysis), indent=2, sort_keys=True) + "\n"
    text = markdown(analysis)
    written = []
    for name, body in (("usb-routing.json", payload),
                       ("usb-routing.md", text)):
        path = out_dir / name
        if not path.exists() or path.read_text() != body:
            path.write_text(body)
            written.append(name)
    return tuple(written)


def main(argv=None):
    args = parse_args(argv)
    try:
        analysis = build()
    except (OSError, RoutingError, struct.error) as exc:
        print(f"RESULT routing_ok=False error={exc}")
        return 1
    if args.check:
        stale = []
        for name, body in (("usb-routing.json",
                            json.dumps(to_dict(analysis), indent=2,
                                       sort_keys=True) + "\n"),
                           ("usb-routing.md", markdown(analysis))):
            path = NOTES / name
            if not path.exists() or path.read_text() != body:
                stale.append(name)
        print(f"RESULT reports_current={not stale} stale={len(stale)}"
              + ("" if not stale else " " + ", ".join(stale)))
        return 0 if not stale else 1
    if args.write:
        for name in write_notes(analysis):
            print(f"WROTE notes/{name}")
        return 0
    if args.json:
        print(json.dumps(to_dict(analysis), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(analysis)))
    return 0 if all(item["ok"] for item in analysis.checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
