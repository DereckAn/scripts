#!/usr/bin/env python3
"""Phase 7: the offline image builder, with explicit source adapters.

Offline construction and checking. THIS MODULE CONTAINS NO USB ENUMERATION AND
NO FLASHING CODE, and a test asserts the absence of device framing rather than
trusting the claim. It builds a candidate image and reports what it can and
cannot verify. It is not evidence that an image will boot.

WHY A SECOND BUILDER. tool/build_modified_image.py is locked to the vendor
1.00.58 artifact and is the subject of log 77; it is left exactly as it is so
that log's result stays reproducible. This module is the general one: two
explicit adapters, every offset a LOGICAL FLASH offset translated through the
adapter's base, and the fail-closed policy Phase 7 specifies.

THE ADAPTERS
    vendor-1.00.58-full          base 0x00000  size 0x7c000  the whole image
    installed-1.59-application   base 0x10000  size 0x6c000  the USB readback

An installed source is the application region ONLY. That is not a limitation to
work around; it is the reason the primary bootloader word-sum is reported
UNAVAILABLE rather than recomputed, and the reason any operation that would
require changing it is refused.

WHAT IS RECOMPUTED, in dependency order, and nothing else:
    1. each affected record's chunked-CRC sum at record+0x8 — the per-0x10000
       chunk IEEE CRC-32 results summed mod 2**32 (logs 75, 76)
    2. the backup-bootloader word-sum at logical 0x70ffc — ONLY if a reviewed
       policy ever permits changing [0x61000,0x71000). NO SUCH POLICY EXISTS,
       so this path is present and unreachable by default
    3. the application-region word-sum at logical 0x7bffc, LAST, because it
       covers [0x10000,0x7bffc) including the record checksum fields updated
       in step 1

No device access. Examples:
    python3 tool/build_offline_image.py --source <bin> --noop --out <dir>
    python3 tool/build_offline_image.py --source <bin> \\
        --patch 0x3f66f=52:72 --out <dir>
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_boot_structures as boot
import falchion_image as fi

TOOL_VERSION = "phase7.1"

# Logical flash offsets. Every one is a LOGICAL offset; an adapter translates.
FWIN_OFF = fi.FWIN_OFF                       # 0x10000
RECORD_TABLE_LO = FWIN_OFF + fi.FWIN_REC0_OFF
RECORD_TABLE_HI = RECORD_TABLE_LO + fi.MAX_RECORDS * fi.REC_STRIDE
FWIN_HEADER_LO = FWIN_OFF
FWIN_HEADER_HI = FWIN_OFF + fi.FWIN_REC0_OFF
RECORD_CHECKSUM_OFF = 0x8                    # within a record

PRIMARY_BOOTLOADER = (0x0, 0x10000)
BACKUP_BOOTLOADER = (0x61000, 0x71000)

# name -> (covered range, field offset). The field is 4 bytes at the top of
# the range it covers.
WORD_SUMS = {
    "primary_bootloader": ((0x0, 0x0FFFC), 0x0FFFC),
    "backup_bootloader": ((0x61000, 0x70FFC), 0x70FFC),
    "application": ((0x10000, 0x7BFFC), 0x7BFFC),
}
WORD_SUM_FIELD_SIZE = 4

# Which word-sums a reviewed policy currently permits recomputing.
PERMITTED_RECOMPUTE = ("application",)
# Which the builder may recompute only under a policy that does not exist.
POLICY_GATED_RECOMPUTE = ("backup_bootloader",)

UNTESTED_MARKER = "UNTESTED"


class BuildError(ValueError):
    """A refusal. Every one of these is a clean abort with no output."""


@dataclass(frozen=True)
class Adapter:
    """A source shape. `spec` is falchion_image's allowlist entry."""
    spec: object

    @property
    def name(self):
        return self.spec.name

    @property
    def base(self):
        return self.spec.base

    @property
    def size(self):
        return self.spec.size

    @property
    def lo(self):
        return self.base

    @property
    def hi(self):
        return self.base + self.size

    def contains(self, lo, hi):
        return self.lo <= lo and hi <= self.hi

    def offset(self, flash_off):
        """Logical flash offset -> index into this adapter's bytes."""
        if not self.lo <= flash_off < self.hi:
            raise BuildError(
                f"logical offset 0x{flash_off:x} is outside the "
                f"{self.name} adapter's range "
                f"0x{self.lo:x}..0x{self.hi:x}")
        return flash_off - self.base

    def word_sum_status(self):
        """{name: 'available' | 'unavailable'} for this adapter."""
        out = {}
        for name, ((lo, hi), field_off) in WORD_SUMS.items():
            covered = self.contains(lo, hi) and self.contains(
                field_off, field_off + WORD_SUM_FIELD_SIZE)
            out[name] = "available" if covered else "unavailable"
        return out


def adapters():
    return {spec.name: Adapter(spec) for spec in fi.SUPPORTED_SOURCES}


@dataclass(frozen=True)
class Patch:
    """One byte replacement, with its mandatory original-byte assertion."""
    flash_off: int
    original: bytes
    replacement: bytes

    def __post_init__(self):
        if not self.original:
            raise BuildError(
                f"patch at 0x{self.flash_off:x} is empty; a patch must "
                "change at least one byte")
        if len(self.original) != len(self.replacement):
            raise BuildError(
                f"patch at 0x{self.flash_off:x} is {len(self.original)} bytes "
                f"original and {len(self.replacement)} replacement; a patch "
                "may not change a record's length")

    @property
    def lo(self):
        return self.flash_off

    @property
    def hi(self):
        return self.flash_off + len(self.original)


def parse_patch(text):
    """`0xOFFSET=OLDHEX:NEWHEX`. The original bytes are NOT optional."""
    match = re.fullmatch(
        r"\s*(0[xX][0-9a-fA-F]+|\d+)\s*=\s*([0-9a-fA-F]+)\s*:\s*([0-9a-fA-F]+)\s*",
        text)
    if not match:
        raise BuildError(
            f"cannot parse patch {text!r}; the form is "
            "OFFSET=ORIGINALHEX:REPLACEMENTHEX and the original bytes are "
            "mandatory")
    offset = int(match.group(1), 0)
    try:
        original = bytes.fromhex(match.group(2))
        replacement = bytes.fromhex(match.group(3))
    except ValueError as exc:
        raise BuildError(f"patch {text!r}: {exc}") from exc
    return Patch(offset, original, replacement)


def overlaps(lo_a, hi_a, lo_b, hi_b):
    return lo_a < hi_b and lo_b < hi_a


@dataclass(frozen=True)
class Span:
    """One active record's payload, in LOGICAL flash offsets.

    A record's address field carries the 0x60000000 flash base, so it is not
    directly comparable with a logical offset. Mixing the two silently is
    exactly the kind of address-space slip this project keeps finding, so the
    translation happens once, here, and nothing downstream sees a raw field.
    """
    index: int
    lo: int
    hi: int

    @property
    def length(self):
        return self.hi - self.lo


def active_records(view):
    """Active record payload spans, as the bootloader's own scan defines them.

    Logical offsets, base-translated. A slot with a nonzero length is active
    even if a lower slot is a hole (log 95).
    """
    spans = []
    for record in fi.parse(view).records:
        if not record.length:
            continue
        lo = record.addr - fi.FLASH_BASE
        if lo < 0:
            raise BuildError(
                f"record {record.index} address 0x{record.addr:08x} is below "
                f"the flash base 0x{fi.FLASH_BASE:08x}")
        spans.append(Span(record.index, lo, lo + record.length))
    return spans


def reject_reasons(patch, adapter, records):
    """Every reason this patch must be refused. Empty means acceptable."""
    reasons = []
    if not adapter.contains(patch.lo, patch.hi):
        reasons.append(
            f"outside the {adapter.name} adapter's range "
            f"0x{adapter.lo:x}..0x{adapter.hi:x}")
        return reasons  # nothing else can be decided
    if overlaps(patch.lo, patch.hi, *PRIMARY_BOOTLOADER):
        reasons.append("touches the primary bootloader region")
    if overlaps(patch.lo, patch.hi, *BACKUP_BOOTLOADER):
        reasons.append("touches the backup bootloader region")
    if overlaps(patch.lo, patch.hi, FWIN_HEADER_LO, FWIN_HEADER_HI):
        reasons.append("touches the SN_FWIN header")
    if overlaps(patch.lo, patch.hi, RECORD_TABLE_LO, RECORD_TABLE_HI):
        reasons.append("touches the record table metadata")
    for name, (_covered, field_off) in WORD_SUMS.items():
        if overlaps(patch.lo, patch.hi, field_off,
                    field_off + WORD_SUM_FIELD_SIZE):
            reasons.append(f"touches the {name} word-sum field itself")
    inside = [span for span in records
              if span.lo <= patch.lo and patch.hi <= span.hi]
    if not inside:
        reasons.append("does not lie wholly inside one active record's payload")
    return reasons


def affected_records(patches, records):
    return [span for span in records
            if any(overlaps(patch.lo, patch.hi, span.lo, span.hi)
                   for patch in patches)]


def build(source_path, patches, out_dir, label="patched"):
    """Build a candidate image. Returns (output path, manifest dict).

    Every refusal raises BuildError BEFORE anything is written.
    """
    data = Path(source_path).read_bytes()
    view = fi.ImageView(data, 0)
    # The adapter is chosen by matching the allowlist, never by a flag, so a
    # wrong --base cannot be supplied at all.
    spec = None
    for candidate in fi.SUPPORTED_SOURCES:
        if candidate.sha256 == hashlib.sha256(data).hexdigest() \
                and candidate.size == len(data):
            spec = candidate
            break
    if spec is None:
        raise BuildError(
            f"sha256={hashlib.sha256(data).hexdigest()} size=0x{len(data):x} "
            "is not an allowlisted mutation source")
    adapter = Adapter(spec)
    view = fi.ImageView(data, adapter.base)
    fi.require_supported_source(view)

    records = active_records(view)
    if not records:
        raise BuildError("the parsed layout has no active records")

    # --- refusals, all before any mutation ---------------------------------
    seen = []
    for patch in patches:
        reasons = reject_reasons(patch, adapter, records)
        if reasons:
            raise BuildError(
                f"patch at 0x{patch.lo:x}: " + "; ".join(reasons))
        for other in seen:
            if overlaps(patch.lo, patch.hi, other.lo, other.hi):
                raise BuildError(
                    f"patch at 0x{patch.lo:x} overlaps the patch at "
                    f"0x{other.lo:x}")
        seen.append(patch)

    # --- original-byte assertions ------------------------------------------
    out = bytearray(data)
    for patch in patches:
        start = adapter.offset(patch.lo)
        found = bytes(out[start:start + len(patch.original)])
        if found != patch.original:
            raise BuildError(
                f"patch at 0x{patch.lo:x} expected original bytes "
                f"{patch.original.hex()} but the source holds {found.hex()}")
    for patch in patches:
        start = adapter.offset(patch.lo)
        out[start:start + len(patch.replacement)] = patch.replacement

    # --- integrity, in dependency order ------------------------------------
    recomputed = []
    working = fi.ImageView(bytes(out), adapter.base)
    for span in affected_records(patches, records):
        value = fi.chunked_crc_sum(working, span.lo, span.length)
        field_off = (RECORD_TABLE_LO + span.index * fi.REC_STRIDE
                     + RECORD_CHECKSUM_OFF)
        start = adapter.offset(field_off)
        out[start:start + 4] = value.to_bytes(4, "little")
        recomputed.append({"field": "record_chunked_crc", "flash_off": field_off,
                           "record": span.index, "value": value})
        working = fi.ImageView(bytes(out), adapter.base)

    status = adapter.word_sum_status()
    for name in POLICY_GATED_RECOMPUTE:
        (lo, hi), _field = WORD_SUMS[name]
        if any(overlaps(patch.lo, patch.hi, lo, hi) for patch in patches):
            raise BuildError(
                f"a patch would require recomputing the {name} word-sum, and "
                "no reviewed policy permits changing that region")
    for name in PERMITTED_RECOMPUTE:
        if status[name] != "available":
            raise BuildError(
                f"the {name} word-sum is {status[name]} for the "
                f"{adapter.name} adapter, so this build cannot complete")
        (lo, hi), field_off = WORD_SUMS[name]
        computed = fi.word_sum(working, lo, hi)
        value = getattr(computed, "computed", computed)
        start = adapter.offset(field_off)
        out[start:start + 4] = value.to_bytes(4, "little")
        recomputed.append({"field": f"{name}_word_sum", "flash_off": field_off,
                           "record": None, "value": value})
        working = fi.ImageView(bytes(out), adapter.base)

    # --- validation, reported and not claimed as acceptance ----------------
    validation = fi.validate(working)
    checks = [{"name": check.name, "ok": check.ok}
              for check in validation.checks]
    boot_checks = [{"name": name, "ok": bool(ok)}
                   for name, ok, *_ in boot.known_boot_checks(
                       bytes(out), adapter.base)] \
        if _boot_checks_supported() else []

    payload = bytes(out)
    digest = hashlib.sha256(payload).hexdigest()
    name = (f"{adapter.name}_{label}_{UNTESTED_MARKER}_{digest[:12]}.bin")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    manifest = {
        "adapter": adapter.name,
        "adapter_base": adapter.base,
        "boot_checks": boot_checks,
        "output_sha256": digest,
        "output_size": len(payload),
        "patches": [
            {"flash_off": patch.lo,
             "original": patch.original.hex(),
             "replacement": patch.replacement.hex(),
             "length": len(patch.original)}
            for patch in patches],
        "recomputed_fields": recomputed,
        "source_sha256": spec.sha256,
        "source_size": spec.size,
        "tool_version": TOOL_VERSION,
        "unresolved_risks": unresolved_risks(adapter, checks, boot_checks),
        "validations": checks,
        "word_sum_status": status,
        "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(0)),
    }
    _exclusive_write(path, payload)
    try:
        _exclusive_write(path.with_suffix(".manifest.json"),
                         (json.dumps(manifest, indent=2, sort_keys=True)
                          + "\n").encode())
    except BuildError:
        path.unlink(missing_ok=True)
        raise
    return path, manifest


def _boot_checks_supported():
    try:
        boot.known_boot_checks(b"\x00" * 0x100, 0)
        return True
    except Exception:
        return False


def _exclusive_write(path, payload):
    """Exclusive create, never overwrite, never leave a partial file."""
    try:
        handle = open(path, "xb")
    except FileExistsError as exc:
        raise BuildError(f"{path.name} already exists; refusing to "
                         "overwrite") from exc
    try:
        with handle:
            handle.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def unresolved_risks(adapter, checks, boot_checks):
    """What this build could NOT establish. Never empty."""
    risks = [
        "This build is not evidence that the image will boot. No device was "
        "accessed and no execution was observed.",
    ]
    for name, state in sorted(adapter.word_sum_status().items()):
        if state != "available":
            risks.append(
                f"the {name} word-sum is {state} for this adapter: it is "
                "neither verified nor recomputed, and any operation that "
                "would require changing it is refused")
    failed = [item["name"] for item in checks if not item["ok"]]
    if failed:
        risks.append("failed layout checks: " + ", ".join(failed))
    failed_boot = [item["name"] for item in boot_checks if not item["ok"]]
    if failed_boot:
        risks.append("failed boot checks: " + ", ".join(failed_boot))
    risks.extend(f"unresolved boot-structure item: {item}"
                 for item in boot.UNRESOLVED)
    return risks


def report_lines(path, manifest):
    out = [
        "PROGRAM build_offline_image",
        "PURPOSE Phase 7 — offline construction only. No device code.",
        "",
        f"ADAPTER {manifest['adapter']} base=0x{manifest['adapter_base']:x}",
        f"SOURCE  {manifest['source_sha256']}",
        f"OUTPUT  {path.name}",
        f"        sha256={manifest['output_sha256']}",
        f"PATCHES {len(manifest['patches'])}",
    ]
    for patch in manifest["patches"]:
        out.append(f"  0x{patch['flash_off']:x} {patch['original']} -> "
                   f"{patch['replacement']}")
    out.append(f"RECOMPUTED {len(manifest['recomputed_fields'])}")
    for item in manifest["recomputed_fields"]:
        out.append(f"  {item['field']} at 0x{item['flash_off']:x} = "
                   f"0x{item['value']:08x}")
    out.append("WORD SUMS")
    for name, state in sorted(manifest["word_sum_status"].items()):
        out.append(f"  {name}: {state}")
    out.append(f"VALIDATIONS {len(manifest['validations'])}")
    failed = [item["name"] for item in manifest["validations"]
              if not item["ok"]]
    out.append("  failed: " + (", ".join(failed) or "none"))
    out.append("UNRESOLVED RISKS")
    for item in manifest["unresolved_risks"]:
        out.append(f"  - {item}")
    out.append("")
    out.append("RESULT built=1 (construction only; acceptance is NOT claimed)")
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--patch", action="append", default=[],
                        help="OFFSET=ORIGINALHEX:REPLACEMENTHEX")
    parser.add_argument("--noop", action="store_true",
                        help="build with no patches; output must be identical")
    parser.add_argument("--label", default="patched")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.noop and args.patch:
            raise BuildError("--noop takes no patches")
        patches = [parse_patch(text) for text in args.patch]
        path, manifest = build(args.source, patches, args.out,
                               "noop" if args.noop else args.label)
    except (BuildError, fi.ImageFormatError, fi.UnsupportedSourceError,
            OSError) as exc:
        print(f"RESULT built=0 refused={exc}")
        return 1
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(path, manifest)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
