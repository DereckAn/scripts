#!/usr/bin/env python3
"""Phase 8: independent validation of a patched compressed-region artefact.

INDEPENDENCE IS THE POINT. This module imports NOTHING from the builder. It
re-decodes the compressed scatter region with its own decoder written from the
log-105 rules, recomputes both integrity fields from `zlib` and `struct`
directly, and diffs the decoded regions. A bug shared between the builder and
its checker cannot hide behind a validator that shares the builder's code, so
this one does not.

WHY A COMPRESSED-REGION PATCH NEEDS THIS AT ALL. The product string lives in
the decompressed region, so the flash bytes that encode it are inside a
compressed stream. A same-length replacement is only safe when two things hold,
and neither is obvious from the bytes:

  1. every replaced stream byte is a LITERAL in the token stream, not a
     back-reference parameter — patching a distance or a count byte would
     rewrite the token structure;
  2. no LATER back-reference reads from the output positions the patch
     changes — otherwise the change propagates into bytes nobody intended to
     touch.

The decoder here records, for every output byte, whether it came from a
literal (and from which stream offset), a copy (and from which output offset),
or a zero fill. That provenance is what makes both conditions checkable rather
than assumed.

ACCEPTANCE AND BOOTING ARE NOT CLAIMED ANYWHERE. This validates structure.

No device access. Examples:
    python3 tool/verify_patched_region.py
    python3 tool/verify_patched_region.py --json
    python3 tool/verify_patched_region.py --write
    python3 tool/verify_patched_region.py --check
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))

import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / "notes"
GENERATED = ROOT / "generated"
DUMPS = ROOT / "dumps"

M32 = 0xFFFFFFFF
REGION_LENGTH = 0xB04
STRING_OFFSET = 0x882
ORIGINAL_STRING = b"ROG FALCHION ACE HFX"
REPLACEMENT_STRING = b"UNTESTED FALCHION FW"

# Logical offsets, mirrored from the layout rather than imported from the
# builder, so a change in one is not silently accepted by the other.
RECORD_TABLE_LO = fi.FWIN_OFF + fi.FWIN_REC0_OFF
RECORD_CHECKSUM_OFF = 0x8
APPLICATION_WORD_SUM = ((0x10000, 0x7BFFC), 0x7BFFC)

SOURCES = {
    "installed": (DUMPS / "device/ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59"
                          "_app_0x10000_0x7bfff.bin", 0x10000),
    "vendor": (DUMPS / "vendor/M605_V01_00_58.bin", 0x0),
}
ARTEFACTS = {
    "installed": ("installed-1.59-application_productstring_UNTESTED"
                  "_96f6157868da.bin",
                  "installed-1.59-application_noop_UNTESTED_fc6128ab089e.bin"),
    "vendor": ("vendor-1.00.58-full_productstring_UNTESTED_fda342b393a7.bin",
               "vendor-1.00.58-full_noop_UNTESTED_6d410ee0a54f.bin"),
}


class VerifyError(ValueError):
    """The artefact does not hold up."""


@dataclass(frozen=True)
class Decoded:
    output: bytes
    consumed: int
    provenance: tuple      # per output byte: ("literal", stream_off) | ("copy", src) | ("zero", None)
    copy_reads: tuple      # (source_output_index, destination_output_index)
    tokens: tuple          # (stream_start, stream_end, control_byte)


def decode(stream, length):
    """The log-105 decoder, reimplemented here with per-byte provenance.

    `subs r4,r4,#1` before the literal loop means a field of N emits N-1
    bytes; `add r5,#2` then a byte-at-a-time copy means a back-reference emits
    field+2 bytes and an overlapping one repeats what it just wrote.
    """
    out = bytearray()
    provenance = []
    reads = []
    tokens = []
    index = 0

    def take():
        nonlocal index
        if index >= len(stream):
            raise VerifyError(
                f"stream exhausted after {index} bytes with {len(out)} of "
                f"{length} output bytes produced")
        value = stream[index]
        index += 1
        return value

    while len(out) < length:
        start = index
        control = take()
        literals = control & 7
        if literals == 0:
            literals = take()
        copies = control >> 4
        if copies == 0:
            copies = take()
        for _ in range(literals - 1):
            provenance.append(("literal", index))
            out.append(take())
        if control & 8:
            distance = take()
            if distance > len(out):
                raise VerifyError(
                    f"back-reference distance {distance} exceeds the "
                    f"{len(out)} bytes produced so far")
            origin = len(out) - distance
            for step in range(copies + 2):
                source = origin + step
                reads.append((source, len(out)))
                provenance.append(("copy", source))
                out.append(out[source])
        else:
            for _ in range(copies):
                provenance.append(("zero", None))
                out.append(0)
        tokens.append((start, index, control))
    return Decoded(bytes(out), index, tuple(provenance), tuple(reads),
                   tuple(tokens))


def independent_chunked_crc(data, start, length, chunk=0x10000):
    """From `zlib` directly; shares no code with any builder."""
    acc, pos, rem = 0, start, length
    while rem:
        size = min(rem, chunk)
        acc = (acc + zlib.crc32(data[pos:pos + size])) & M32
        pos += size & 0xFFFFFFFC
        rem -= size
    return acc


def independent_word_sum(data, start, end):
    words = struct.unpack(f"<{(end - start) // 4}I", data[start:end])
    return sum(words) & M32


def region_bounds(view):
    """The decompress region's flash source span, from the scatter table."""
    import extract_installed_records as ex
    extraction = ex.extract(view)
    regions = [item for item in extraction.regions
               if item.handler_name == "__scatterload_decompress"]
    if len(regions) != 1:
        raise VerifyError(
            f"expected one decompress region, found {len(regions)}")
    region = regions[0]
    payload = fi.parse(view).records[1]
    return region, region.src_flash, payload.flash_end


def propagation_reads(decoded, lo, hi):
    """Copies whose SOURCE lies in [lo,hi) — the propagation risk."""
    return tuple((source, destination)
                 for source, destination in decoded.copy_reads
                 if lo <= source < hi)


def verify_release(release):
    """Every structural check for one release. Returns a result dict."""
    source_path, base = SOURCES[release]
    patched_name, rollback_name = ARTEFACTS[release]
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return ok

    original = source_path.read_bytes()
    patched_path = GENERATED / patched_name
    rollback_path = GENERATED / rollback_name
    for path in (patched_path, rollback_path):
        if not path.exists():
            raise VerifyError(f"artefact {path.name} is missing")
    patched = patched_path.read_bytes()
    rollback = rollback_path.read_bytes()

    check("the artefact filename carries UNTESTED",
          "UNTESTED" in patched_name and "UNTESTED" in rollback_name)
    check("the rollback build is byte-identical to the source",
          rollback == original,
          f"sha256 {hashlib.sha256(rollback).hexdigest()[:16]}")

    view_o = fi.ImageView(original, base)
    view_p = fi.ImageView(patched, base)
    region_o, lo_o, hi_o = region_bounds(view_o)
    region_p, lo_p, hi_p = region_bounds(view_p)
    check("the patch did not move the compressed region",
          (lo_o, hi_o, region_o.size) == (lo_p, hi_p, region_p.size),
          f"flash 0x{lo_o:x}..0x{hi_o:x} size 0x{region_o.size:x}")

    stream_o = view_o.read(lo_o, hi_o - lo_o)
    stream_p = view_p.read(lo_p, hi_p - lo_p)
    decoded_o = decode(stream_o, region_o.size)
    decoded_p = decode(stream_p, region_p.size)

    check("the original region still decodes to its declared length",
          len(decoded_o.output) == REGION_LENGTH,
          f"0x{len(decoded_o.output):x}")
    check("the patched region decodes to the same declared length",
          len(decoded_p.output) == REGION_LENGTH,
          f"0x{len(decoded_p.output):x}")
    check("the patched stream consumes identically",
          decoded_o.consumed == decoded_p.consumed,
          f"0x{decoded_o.consumed:x} both")
    check("the token structure is unchanged",
          decoded_o.tokens == decoded_p.tokens,
          f"{len(decoded_o.tokens)} tokens, identical boundaries and "
          "control bytes")

    # --- the literal proof --------------------------------------------------
    span = range(STRING_OFFSET, STRING_OFFSET + len(ORIGINAL_STRING))
    kinds = {decoded_o.provenance[i][0] for i in span}
    check("every patched output byte is a LITERAL in the token stream",
          kinds == {"literal"}, ", ".join(sorted(kinds)))
    stream_offsets = [decoded_o.provenance[i][1] for i in span]
    contiguous = stream_offsets == list(
        range(stream_offsets[0], stream_offsets[0] + len(span)))
    check("the literal stream offsets are contiguous",
          contiguous,
          f"0x{stream_offsets[0]:x}..0x{stream_offsets[-1]:x}")
    propagation = propagation_reads(decoded_o, span.start, span.stop)
    check("NO later back-reference reads from the patched output range",
          not propagation,
          f"{len(propagation)} reads" if propagation else "zero reads")

    # --- the decoded diff ---------------------------------------------------
    differing = [i for i in range(REGION_LENGTH)
                 if decoded_o.output[i] != decoded_p.output[i]]
    # The invariant that matters is CONTAINMENT, not a count. Two strings can
    # coincide at a position — here index 18 is 'F' in both — and a byte that
    # did not change is not a defect. What would be a defect is a byte
    # differing OUTSIDE the intended span, which is exactly what propagation
    # through a back-reference would look like.
    outside = [i for i in differing if i not in span]
    check("NO decoded byte outside the intended span changed",
          not outside,
          f"{len(outside)} bytes" if outside else "zero bytes outside "
          f"0x{span.start:x}..0x{span.stop:x}")
    coinciding = [i for i in span
                  if ORIGINAL_STRING[i - span.start]
                  == REPLACEMENT_STRING[i - span.start]]
    check("every differing byte is accounted for by the replacement",
          sorted(differing) == sorted(set(span) - set(coinciding)),
          f"{len(differing)} differ, {len(coinciding)} coincide "
          f"({', '.join(f'0x{i:x}' for i in coinciding) or 'none'}), "
          f"{len(differing) + len(coinciding)} = {len(span)} total")
    check("the original decoded bytes are the expected string",
          decoded_o.output[span.start:span.stop] == ORIGINAL_STRING,
          decoded_o.output[span.start:span.stop].decode("ascii", "replace"))
    check("the patched decoded bytes are the replacement string",
          decoded_p.output[span.start:span.stop] == REPLACEMENT_STRING,
          decoded_p.output[span.start:span.stop].decode("ascii", "replace"))
    check("the replacement preserves length and character class",
          len(REPLACEMENT_STRING) == len(ORIGINAL_STRING)
          and all(48 <= byte <= 90 or byte == 32
                  for byte in REPLACEMENT_STRING))

    # --- integrity, recomputed independently --------------------------------
    index = -base
    record = fi.parse(view_p).records[1]
    record_lo = record.addr - fi.FLASH_BASE
    crc_field = (RECORD_TABLE_LO + record.index * fi.REC_STRIDE
                 + RECORD_CHECKSUM_OFF)
    stored_crc, = struct.unpack_from("<I", patched, crc_field + index)
    expected_crc = independent_chunked_crc(patched, record_lo + index,
                                           record.length)
    check("the record chunked-CRC matches an independent recomputation",
          stored_crc == expected_crc,
          f"0x{stored_crc:08x}")
    (ws_lo, ws_hi), ws_field = APPLICATION_WORD_SUM
    stored_sum, = struct.unpack_from("<I", patched, ws_field + index)
    expected_sum = independent_word_sum(patched, ws_lo + index, ws_hi + index)
    check("the application word-sum matches an independent recomputation",
          stored_sum == expected_sum, f"0x{stored_sum:08x}")
    check("the word-sum's covered range contains the record CRC field",
          ws_lo <= crc_field < ws_hi,
          "so a reversed dependency order would have left it stale")

    # --- boot-structure checks ---------------------------------------------
    original_checks = {item.name: item.ok
                       for item in fi.validate(view_o).checks}
    patched_checks = {item.name: item.ok
                      for item in fi.validate(view_p).checks}
    regressed = sorted(name for name, ok in original_checks.items()
                       if ok and not patched_checks.get(name))
    check("every layout check that passed on the source still passes",
          not regressed, ", ".join(regressed) or f"{len(original_checks)} checks")

    return {
        "artefact": patched_name,
        "artefact_sha256": hashlib.sha256(patched).hexdigest(),
        "checks": checks,
        "consumed": decoded_p.consumed,
        "coinciding_positions": [i for i in span
                                 if ORIGINAL_STRING[i - span.start]
                                 == REPLACEMENT_STRING[i - span.start]],
        "decoded_diff": [{"offset": i, "original": decoded_o.output[i],
                          "patched": decoded_p.output[i]} for i in differing],
        "decoded_diff_outside_span": [i for i in differing if i not in span],
        "literal_stream_offsets": stream_offsets,
        "literal_flash_offsets": [lo_o + off for off in stream_offsets],
        "propagation_reads": len(propagation),
        "record_crc": stored_crc,
        "region_flash": [lo_o, hi_o],
        "rollback": rollback_name,
        "rollback_sha256": hashlib.sha256(rollback).hexdigest(),
        "source_sha256": hashlib.sha256(original).hexdigest(),
        "tokens": len(decoded_p.tokens),
        "word_sum": stored_sum,
    }


def to_dict():
    return {
        "acceptance": "NOT CLAIMED. This validates structure only. Nothing "
                      "here is evidence that any image boots, and no device "
                      "was accessed.",
        "original_string": ORIGINAL_STRING.decode(),
        "region_length": REGION_LENGTH,
        "releases": {name: verify_release(name) for name in sorted(SOURCES)},
        "replacement_string": REPLACEMENT_STRING.decode(),
        "string_offset": STRING_OFFSET,
    }


def all_checks(payload):
    return [item for release in payload["releases"].values()
            for item in release["checks"]]


def report_lines():
    payload = to_dict()
    out = [
        "PROGRAM verify_patched_region",
        "PURPOSE Phase 8 — independent validation of the patched artefact",
        "NOTE This module imports nothing from the builder.",
        "",
        f"TARGET the USB product string at region+0x{payload['string_offset']:x}",
        f"  {payload['original_string']!r} -> {payload['replacement_string']!r}",
        "",
    ]
    for name, release in sorted(payload["releases"].items()):
        out += [
            f"RELEASE {name}",
            f"  artefact  {release['artefact']}",
            f"            sha256={release['artefact_sha256']}",
            f"  rollback  {release['rollback']}",
            f"            sha256={release['rollback_sha256']}",
            f"  source    sha256={release['source_sha256']}",
            f"  region    flash 0x{release['region_flash'][0]:x}.."
            f"0x{release['region_flash'][1]:x}  tokens={release['tokens']}  "
            f"consumed=0x{release['consumed']:x}",
            f"  literals  stream 0x{release['literal_stream_offsets'][0]:x}.."
            f"0x{release['literal_stream_offsets'][-1]:x}  flash "
            f"0x{release['literal_flash_offsets'][0]:x}.."
            f"0x{release['literal_flash_offsets'][-1]:x}",
            f"  propagation reads: {release['propagation_reads']}",
            f"  decoded diff: {len(release['decoded_diff'])} bytes changed, "
            f"{len(release['coinciding_positions'])} coincided, "
            f"{len(release['decoded_diff_outside_span'])} outside the span",
            f"  record CRC 0x{release['record_crc']:08x}  "
            f"word-sum 0x{release['word_sum']:08x}",
        ]
        for item in release["checks"]:
            out.append(f"    {'PASS' if item['ok'] else 'FAIL'} {item['name']}"
                       + (f" — {item['detail']}" if item["detail"] else ""))
        out.append("")
    ok = all(item["ok"] for item in all_checks(payload))
    out += [
        f"RESULT verified={ok} checks={len(all_checks(payload))}",
        "ACCEPTANCE " + payload["acceptance"],
    ]
    return out


def markdown():
    payload = to_dict()
    lines = [
        "# Phase 8 artefact validation",
        "",
        "Generated by `tool/verify_patched_region.py`. Do not edit by hand.",
        "",
        f"> **{payload['acceptance']}**",
        "",
        f"Target: the USB product string at region+`0x{payload['string_offset']:x}`, "
        f"`{payload['original_string']}` → `{payload['replacement_string']}`.",
        "",
    ]
    for name, release in sorted(payload["releases"].items()):
        lines += [
            f"## {name}",
            "",
            f"- artefact `{release['artefact']}`",
            f"- rollback `{release['rollback']}` "
            f"(sha256 `{release['rollback_sha256'][:16]}…`)",
            f"- compressed region flash "
            f"`0x{release['region_flash'][0]:x}..0x{release['region_flash'][1]:x}`, "
            f"{release['tokens']} tokens, consumed `0x{release['consumed']:x}`",
            f"- patched literals at stream "
            f"`0x{release['literal_stream_offsets'][0]:x}..`"
            f"`0x{release['literal_stream_offsets'][-1]:x}` "
            f"= flash `0x{release['literal_flash_offsets'][0]:x}..`"
            f"`0x{release['literal_flash_offsets'][-1]:x}`",
            f"- propagation reads: **{release['propagation_reads']}**",
            f"- decoded diff: **{len(release['decoded_diff'])} bytes** "
            f"changed, {len(release['coinciding_positions'])} coincided, "
            f"**{len(release['decoded_diff_outside_span'])} outside the "
            "intended span**",
            "",
            "| check | result |",
            "|---|---|",
        ]
        for item in release["checks"]:
            lines.append(f"| {item['name']} | "
                         f"{'PASS' if item['ok'] else 'FAIL'} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def bodies():
    return {"artefact-validation.json": json.dumps(to_dict(), indent=2,
                                                   sort_keys=True) + "\n",
            "artefact-validation.md": markdown()}


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
    except (OSError, VerifyError, fi.ImageFormatError) as exc:
        print(f"RESULT verified=False error={exc}")
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
        print(payload["artefact-validation.json"], end="")
    else:
        print("\n".join(report_lines()))
    return 0 if all(item["ok"] for item in all_checks(to_dict())) else 1


if __name__ == "__main__":
    raise SystemExit(main())
