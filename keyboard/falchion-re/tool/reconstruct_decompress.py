#!/usr/bin/env python3
"""Reconstruct Candidate A's decompressed scatter region, offline.

Read-only with respect to every dump. Phase 5A continuation: scatter region 1 is
decompressed into RAM at boot and exists in no dump, so `0xb04` bytes of the
runtime image have never been examined. Any dispatch table inside it is invisible
to the pointer-table survey, and the functions it would reach stay unreachable.

The decoder below is a **direct translation of the firmware's own handler**, the
`0x5c` bytes at Candidate A program offset `0x17c` that the scatter descriptor
names, not of a generic ARM library routine. Those bytes are byte-identical in
the preserved vendor 1.00.58 and installed 1.59 images, and the tool refuses to
run if the handler it finds does not hash to the bytes it was translated from.

The instruction sequence, from log 73, with r0=src, r1=dst, r2=length:

    add   r2,r1              ; r2 = end of output
    mov   r12,#0             ; the zero-fill byte
  token:
    ldrb  r3,[r0],#1         ; control byte
    ands  r4,r3,#7           ; literal field
    it eq / ldrb r4,[r0],#1  ;   0 means "take the next byte instead"
    asrs  r5,r3,#4           ; copy field
    it eq / ldrb r5,[r0],#1  ;   0 means "take the next byte instead"
    subs  r4,r4,#1           ; so N literals means N-1 bytes
    beq   +                  ;
    ldrb/strb loop           ; emit r4 literal bytes
    tst   r3,#8              ; bit 3 selects back-reference or zero fill
    ittt ne / ldrb r4        ;   set: distance byte follows,
       add r5,#2             ;        copy length is field+2,
       sub r4,r1,r4          ;        source is dst-distance
    else: strb r12 loop      ;   clear: emit `field` zero bytes
    cmp   r1,r2 / bcc token  ; until the output is full

No device access. Examples:
    python3 tool/reconstruct_decompress.py
    python3 tool/reconstruct_decompress.py --write --json
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_installed_records as ex
import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "ghidra/imports"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"

# The handler this decoder was translated from: Candidate A program offset and
# length, plus the hash of those exact bytes. Identical in both preserved images.
HANDLER_SPAN = (0x17C, 0x1D8)
# Phase 3 measured this shift between the two releases from the flash images
# alone; the decoder is not given it, so seeing it again inside the
# reconstructed region is corroboration rather than a restatement.
RELOCATION_DELTA = 0x2C
# The decoded region turns out to hold the USB descriptor set. These are the
# device's own identifiers as independently recorded in notes/findings.md from
# sysfs and lsusb long before this region was decoded: ASUSTeK 0x0b05, product
# 0x1b7e in normal mode, bcdDevice 1.59 installed and 1.00.58 vendor. Finding
# them in the decoded bytes, in device-descriptor order, is external evidence
# the decode is right — the decoder was never told any of these values.
USB_VENDOR_ID = 0x0B05
USB_PRODUCT_ID = 0x1B7E
INSTALLED_BCD_DEVICE = 0x159
VENDOR_BCD_DEVICE = 0x158
BCD_DEVICE = {"installed": INSTALLED_BCD_DEVICE, "vendor": VENDOR_BCD_DEVICE}
HANDLER_SHA256 = (
    "582c480472872687b56e13f46ba6bbfb"
    "754d0449964344206bb23def06f56ae0")


class DecompressError(ValueError):
    """The compressed stream does not decode under the firmware's own rules."""


@dataclass(frozen=True)
class Reconstruction:
    release: str
    image_sha256: str
    handler_sha256: str
    handler_matches: bool
    source_lo: int
    source_hi: int
    destination: int
    declared_length: int
    produced_length: int
    consumed_length: int
    padding_length: int
    tokens: int
    literal_bytes: int
    copy_bytes: int
    zero_bytes: int
    output_sha256: str
    usb_identity_offset: int
    name: str
    checks: tuple


def handler_bytes(view):
    """The decompress handler as it appears in this image."""
    lo, hi = HANDLER_SPAN
    return view.read(0x11000 + lo, hi - lo)


def decompress(source, length):
    """Decode `length` output bytes, exactly as the handler at 0x17c does.

    Returns (output, consumed, statistics). Raises DecompressError when the
    stream runs out or a back-reference points before the start of the output,
    rather than producing a plausible-looking wrong answer.
    """
    out = bytearray()
    index = 0
    tokens = literal_bytes = copy_bytes = zero_bytes = 0

    def take():
        nonlocal index
        if index >= len(source):
            raise DecompressError(
                f"compressed stream exhausted after {index} bytes with "
                f"{len(out)} of {length} output bytes produced")
        value = source[index]
        index += 1
        return value

    while len(out) < length:
        tokens += 1
        control = take()

        literals = control & 7
        if literals == 0:
            literals = take()
        copies = control >> 4
        if copies == 0:
            copies = take()

        # `subs r4,r4,#1` before the loop: a field of N emits N-1 literals.
        for _ in range(literals - 1):
            out.append(take())
            literal_bytes += 1

        if control & 8:
            distance = take()
            if distance > len(out):
                raise DecompressError(
                    f"back-reference distance {distance} exceeds the "
                    f"{len(out)} bytes produced so far")
            start = len(out) - distance
            # `subs r5,r5,#1; bpl` after `add r5,#2` emits field + 2 bytes, one
            # at a time, so an overlapping reference repeats what it just wrote.
            for step in range(copies + 2):
                out.append(out[start + step])
                copy_bytes += 1
        else:
            # `subs r5,r5,#1; it pl; strb.pl` emits `field` zero bytes.
            out.extend(b"\x00" * copies)
            zero_bytes += copies

    return bytes(out), index, {
        "tokens": tokens, "literal_bytes": literal_bytes,
        "copy_bytes": copy_bytes, "zero_bytes": zero_bytes,
    }


@dataclass(frozen=True)
class Correspondence:
    """How the two releases' reconstructed regions relate to each other."""
    equal_length: bool
    length: int
    differing_bytes: int
    differing_words: tuple
    deltas: tuple
    checks: tuple


def correspond(installed, vendor):
    """Compare the two reconstructions word by word.

    This is the strongest available structural evidence short of a RAM dump.
    Neither output can be checked against the device, but they can be checked
    against each other: two independently decoded streams from two different
    releases should differ only where the releases themselves differ. If the
    decoder were wrong, the two wrong answers would have no reason to line up.
    """
    checks = []

    def check(name, ok, detail=""):
        checks.append(fi.Check(f"{name}{(' — ' + detail) if detail else ''}", ok))

    equal_length = len(installed) == len(vendor)
    check("both releases decode to the same length", equal_length,
          f"0x{len(installed):x} vs 0x{len(vendor):x}")
    if not equal_length:
        return Correspondence(False, 0, 0, (), (), tuple(checks))

    differing = [index for index in range(len(installed))
                 if installed[index] != vendor[index]]
    words = sorted({index & ~3 for index in differing})
    tally = {}
    for offset in words:
        left, = struct.unpack_from("<I", installed, offset)
        right, = struct.unpack_from("<I", vendor, offset)
        tally.setdefault(left - right, []).append(offset)
    deltas = tuple(sorted(
        (delta, tuple(offsets)) for delta, offsets in tally.items()))

    check("the two releases differ in only a small minority of bytes",
          len(differing) * 100 < len(installed) * 5,
          f"{len(differing)} of {len(installed)} bytes "
          f"({100 * len(differing) / len(installed):.2f}%)")
    # RELOCATION_DELTA is what Phase 3 measured between the two releases from
    # the flash images alone. Finding the same shift on most of the differing
    # words inside a region neither release stores decompressed is independent
    # corroboration: the decoder was not told this number.
    relocated = len(tally.get(RELOCATION_DELTA, ()))
    check("most differing words are the Phase 3 relocation shift apart",
          relocated * 2 > len(words),
          f"{relocated} of {len(words)} words shift by exactly "
          f"0x{RELOCATION_DELTA:x}")
    # The two releases are 1.59 and 1.00.58. A word holding one BCD version in
    # the installed output and the other in the vendor output cannot be an
    # artefact of a broken decoder: it is a known value, decoded correctly.
    version_words = [offset for offset in words
                     if struct.unpack_from("<I", installed, offset)[0] & 0xFFF
                     == INSTALLED_BCD_DEVICE
                     and struct.unpack_from("<I", vendor, offset)[0] & 0xFFF
                     == VENDOR_BCD_DEVICE]
    check("a decoded word carries each release's own bcdDevice",
          bool(version_words),
          ", ".join(f"+0x{offset:x}" for offset in version_words) or "none")

    return Correspondence(
        equal_length=True, length=len(installed),
        differing_bytes=len(differing), differing_words=tuple(words),
        deltas=deltas, checks=tuple(checks))


def region_one(view):
    """The decompress descriptor and its compressed source, from this image."""
    extraction = ex.extract(view)
    regions = [item for item in extraction.regions
               if item.handler_name == "__scatterload_decompress"]
    if len(regions) != 1:
        raise DecompressError(
            f"expected exactly one decompress region, found {len(regions)}")
    region = regions[0]
    payload = fi.parse(view).records[1]
    source_lo = region.src_flash
    source_hi = payload.flash_end
    return region, source_lo, source_hi


def reconstruct(view, release):
    checks = []

    def check(name, ok, detail=""):
        checks.append(fi.Check(f"{name}{(' — ' + detail) if detail else ''}", ok))
        return ok

    found = handler_bytes(view)
    digest = hashlib.sha256(found).hexdigest()
    matches = digest == HANDLER_SHA256
    check("the handler is the one this decoder was translated from",
          matches, digest)
    if not matches:
        raise DecompressError(
            "the decompress handler in this image does not match the bytes the "
            f"decoder was translated from (found {digest}). Refusing to decode: "
            "a different handler may use a different format.")

    region, source_lo, source_hi = region_one(view)
    source = view.read(source_lo, source_hi - source_lo)
    output, consumed, stats = decompress(source, region.size)

    check("output length equals the scatter descriptor",
          len(output) == region.size,
          f"0x{len(output):x} vs 0x{region.size:x}")
    # The compressed length is not stored anywhere. It is derived as "region
    # 1's source to the end of SN_FWIN record 1", and the record length is a
    # multiple of four, so the stream is padded up to a word boundary. The
    # check is therefore that the decoder consumes the stream up to that
    # boundary and that every byte it did not consume is zero padding — not
    # that it consumes the derived length exactly, which would be false.
    padding = source[consumed:]
    check("the decoder consumed the compressed stream to a word boundary",
          (consumed + 3) & ~3 == len(source),
          f"consumed 0x{consumed:x}, rounds up to 0x{(consumed + 3) & ~3:x}, "
          f"source is 0x{len(source):x}")
    check("every unconsumed byte is zero padding",
          all(byte == 0 for byte in padding),
          f"{len(padding)} byte(s): {padding.hex(' ') or 'none'}")
    check("no output byte was produced past the declared length",
          len(output) <= region.size)

    # idVendor, idProduct, bcdDevice are adjacent little-endian halfwords in a
    # USB device descriptor. Requiring them adjacent and in that order makes a
    # coincidental match far less likely than three separate searches would.
    expected = struct.pack("<HHH", USB_VENDOR_ID, USB_PRODUCT_ID,
                           BCD_DEVICE.get(release, 0))
    identity = output.find(expected) if release in BCD_DEVICE else -1
    check("the decoded bytes carry this device's USB identity",
          identity >= 0,
          f"idVendor=0x{USB_VENDOR_ID:04x} idProduct=0x{USB_PRODUCT_ID:04x} "
          f"bcdDevice=0x{BCD_DEVICE.get(release, 0):04x} at "
          + (f"+0x{identity:x}" if identity >= 0 else "not found"))

    name = (f"{release}_decompressed_region1_flash{source_lo:05x}"
            f"_dst{region.dst:08x}_len{region.size:05x}"
            f"_{hashlib.sha256(output).hexdigest()[:8]}.bin")

    return Reconstruction(
        release=release, image_sha256=view.sha256(), handler_sha256=digest,
        handler_matches=matches, source_lo=source_lo, source_hi=source_hi,
        destination=region.dst, declared_length=region.size,
        produced_length=len(output), consumed_length=consumed,
        padding_length=len(source) - consumed,
        tokens=stats["tokens"], literal_bytes=stats["literal_bytes"],
        copy_bytes=stats["copy_bytes"], zero_bytes=stats["zero_bytes"],
        output_sha256=hashlib.sha256(output).hexdigest(),
        usb_identity_offset=identity, name=name,
        checks=tuple(checks)), output


def build():
    installed, installed_bytes = reconstruct(
        fi.ImageView(INSTALLED.read_bytes(), 0x10000), "installed")
    vendor, vendor_bytes = reconstruct(
        fi.ImageView(VENDOR.read_bytes(), 0x0), "vendor")
    return (((installed, installed_bytes), (vendor, vendor_bytes)),
            correspond(installed_bytes, vendor_bytes))


def write_outputs(results, out_dir=DEFAULT_OUT):
    """Exclusive create only. Never overwrites, never touches dumps/."""
    if out_dir.resolve().is_relative_to((ROOT / "dumps").resolve()):
        raise DecompressError("refusing to write under dumps/")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for result, payload in results:
        path = out_dir / result.name
        if path.exists():
            if path.read_bytes() != payload:
                raise DecompressError(
                    f"{result.name} exists with different content; refusing to "
                    "overwrite")
            continue
        with open(path, "xb") as handle:
            handle.write(payload)
        written.append(result.name)
    return tuple(written)


def to_dict(results, link):
    return {
        "correspondence": {
            "checks": [{"name": check.name, "ok": check.ok}
                       for check in link.checks],
            "deltas": [{"delta": delta, "offsets": list(offsets)}
                       for delta, offsets in link.deltas],
            "differing_bytes": link.differing_bytes,
            "differing_words": list(link.differing_words),
            "equal_length": link.equal_length,
            "length": link.length,
        },
        "handler": {"length": HANDLER_SPAN[1] - HANDLER_SPAN[0],
                    "program_offset": HANDLER_SPAN[0],
                    "sha256": HANDLER_SHA256},
        "reconstructions": [
            {
                "checks": [{"name": check.name, "ok": check.ok}
                           for check in result.checks],
                "consumed_length": result.consumed_length,
                "copy_bytes": result.copy_bytes,
                "declared_length": result.declared_length,
                "destination": result.destination,
                "handler_matches": result.handler_matches,
                "handler_sha256": result.handler_sha256,
                "image_sha256": result.image_sha256,
                "literal_bytes": result.literal_bytes,
                "name": result.name,
                "output_sha256": result.output_sha256,
                "padding_length": result.padding_length,
                "produced_length": result.produced_length,
                "release": result.release,
                "source_hi": result.source_hi,
                "source_lo": result.source_lo,
                "tokens": result.tokens,
                "usb_identity_offset": result.usb_identity_offset,
                "zero_bytes": result.zero_bytes,
            }
            for result, _payload in results
        ],
    }


def report_lines(results, link):
    out = [
        "PROGRAM reconstruct_decompress",
        "PURPOSE reconstruct Candidate A's decompressed scatter region offline",
        f"HANDLER Candidate A program 0x{HANDLER_SPAN[0]:x}.."
        f"0x{HANDLER_SPAN[1]:x} sha256={HANDLER_SHA256}",
        "HANDLER_SOURCE the decoder is a translation of these bytes, not of a "
        "generic ARM library routine. It refuses to run against a handler that "
        "does not hash to them.",
    ]
    for result, _payload in results:
        out += [
            "",
            f"RELEASE {result.release}",
            f"  image_sha256={result.image_sha256}",
            f"  handler_sha256={result.handler_sha256} "
            f"matches={result.handler_matches}",
            f"  source=flash 0x{result.source_lo:x}..0x{result.source_hi:x} "
            f"(0x{result.source_hi - result.source_lo:x} bytes)",
            f"  destination=0x{result.destination:08x} "
            f"declared_length=0x{result.declared_length:x}",
            f"  produced=0x{result.produced_length:x} "
            f"consumed=0x{result.consumed_length:x} "
            f"zero_padding={result.padding_length}",
            f"  tokens={result.tokens} literal_bytes={result.literal_bytes} "
            f"copy_bytes={result.copy_bytes} zero_bytes={result.zero_bytes}",
            f"  output_sha256={result.output_sha256}",
            f"  usb_identity_at=+0x{result.usb_identity_offset:x}",
            f"  name={result.name}",
        ]
        for check in result.checks:
            out.append(f"  {'PASS' if check.ok else 'FAIL'} {check.name}")
    out += [
        "",
        "CORRESPONDENCE installed vs vendor, decoded independently",
        f"  length=0x{link.length:x} differing_bytes={link.differing_bytes} "
        f"differing_words={len(link.differing_words)}",
    ]
    for delta, offsets in link.deltas:
        out.append(f"  DELTA 0x{delta & 0xFFFFFFFF:08x} ({delta:+d}) "
                   f"words={len(offsets)} at "
                   + ", ".join(f"+0x{offset:x}" for offset in offsets[:8])
                   + (" ..." if len(offsets) > 8 else ""))
    for check in link.checks:
        out.append(f"  {'PASS' if check.ok else 'FAIL'} {check.name}")
    ok = all(check.ok for result, _payload in results
             for check in result.checks) and all(
                 check.ok for check in link.checks)
    out += [
        "",
        f"RESULT reconstruction_ok={ok} releases={len(results)}",
        "LIMITATION The length and consumption checks are STRUCTURAL. They show "
        "the stream decodes cleanly under the firmware's own rules and fills the "
        "descriptor exactly. They are not proof that these are the bytes the "
        "device holds at runtime: nothing here observed the device, and no dump "
        "of that RAM exists to compare against.",
        "EVIDENCE The correspondence above is the strongest available check "
        "short of a RAM dump: two streams decoded independently from two "
        "releases agree except where the releases differ, and the differences "
        "are the relocation shift Phase 3 measured plus each release's own "
        "version number. A wrong decoder would have no reason to "
        "produce two wrong answers that line up this way.",
        "LIMITATION Whether the reconstructed bytes are code is settled by "
        "disassembling them, and the success rate of that is reported "
        "separately rather than assumed here.",
    ]
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true",
                        help="write the regions into the ignored import area")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        results, link = build()
        if args.write:
            written = write_outputs(results, args.out)
        else:
            written = ()
    except (OSError, DecompressError, fi.ImageFormatError,
            ex.ExtractError) as exc:
        print(f"RESULT reconstruction_ok=False error={exc}")
        return 1
    if args.json:
        payload = to_dict(results, link)
        payload["written"] = list(written)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(results, link)))
        for name in written:
            print(f"WROTE {name}")
    checks = [check for result, _payload in results for check in result.checks]
    return 0 if all(check.ok for check in checks + list(link.checks)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
