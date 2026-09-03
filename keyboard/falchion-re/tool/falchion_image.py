#!/usr/bin/env python3
"""Version-aware offline model of the Falchion Ace HFX flash image format.

One shared parser for every later offline tool, so comparators, extractors and
builders never re-derive container offsets, record layout or checksum policy.

Three responsibilities are deliberately separated:

* **Parsing** (`parse`) may inspect an unknown image. It only reports what the
  bytes say and fails closed with `ImageFormatError` when the structure is not
  readable at the supplied base.
* **Validation** (`validate`) reports the known static constraints and names the
  regions it could not check, so a passing partial image is never mistaken for a
  passing full one.
* **Source policy** (`require_supported_source`) refuses any image whose SHA-256
  and base are not explicitly allowlisted. Mutation tooling must call it; read
  only analysis must not.

Every offset in this module is a **logical flash offset** (the address the
bootloader sees, minus `FLASH_BASE`). File indices exist only inside
`ImageView.index`. Record lengths are always read from the image being parsed;
no vendor 1.00.58 length is ever reused for another release.

Evidence: logs 74/75/76 (checksum algorithms), log 78 (boot containers),
log 92 (installed base-0x10000 dump). See FINDINGS.md.

No device access. Examples:
    python3 tool/falchion_image.py
    python3 tool/falchion_image.py installed-app.bin --base 0x10000 --json
"""
import argparse
import binascii
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BIN = ROOT / "dumps/vendor/M605_V01_00_58.bin"

M = 0xFFFFFFFF
FLASH_BASE = 0x60000000
CHUNK = 0x10000

SNC_MAGIC = b"SNC7320A"
BCFG_MAGIC = b"SN_BCFG\x00"
FWIN_MAGIC = b"SN_FWIN\x00"

FWIN_OFF = 0x10000
FWIN_VERSION_OFF = 0x08
FWIN_ENTRY_PTR_OFF = 0x10
FWIN_GATE_OFF = 0x18
FWIN_REC0_OFF = 0x24
FWIN_HEADER_SIZE = 0x34
REC_STRIDE = 0x10
MAX_RECORDS = 8

CONTAINER_BCFG_OFF = 0x200
CONTAINER_SLOTS_OFF = 0x208
CONTAINER_SPAN = CONTAINER_SLOTS_OFF + 8
EXPECTED_CONTAINER_SIZE = 0x10000
# name -> (container flash offset, expected bootloader pointer)
CONTAINERS = (
    ("primary", 0x00000, 0x60001000),
    ("backup", 0x60000, 0x60062000),
)

APPLICATION_REGION = (0x10000, 0x7C000)
# name -> (lo, hi); the final word of each range is an additive sum of the rest.
# "bootloader_mirror" is the byte-identical copy of [0,0x10000) that lives inside
# the application region; its guard word is at 0x70ffc (verified in both images).
WORD_SUM_REGIONS = (
    ("bootloader", 0x00000, 0x10000),
    ("application", 0x10000, 0x7C000),
    ("bootloader_mirror", 0x61000, 0x71000),
)

SP_RANGES = ((0x18000000, 0x18040000), (0x20000000, 0x20001000))

# Carried through every report so a passing run is never read as "this boots".
UNRESOLVED = (
    "FUN_000029d4 is not decompiled; its role in the boot path is unknown.",
    "The top-level comparison applied to the selected entry value before the "
    "jump is not recovered, so the caller's accept/reject rule is unknown.",
    "Any ROM/first-stage conditions ahead of the bootloader are unexamined.",
)


class ImageFormatError(ValueError):
    """The image cannot be parsed as a Falchion flash image at this base."""


class UnsupportedSourceError(ValueError):
    """The image is not an allowlisted source for mutation."""


@dataclass(frozen=True)
class SourceSpec:
    """An explicitly supported source image."""
    name: str
    sha256: str
    base: int
    size: int


SUPPORTED_SOURCES = (
    SourceSpec(
        "vendor-1.00.58-full",
        "6d410ee0a54f640b4ab016cdb973f08e3d3d0ab7a716c7368167e562e0e19f1d",
        0x0, 0x7C000),
    SourceSpec(
        "installed-1.59-application",
        "fc6128ab089e4fd712b172c54cd88b7f28476b55bdac688134e052281ded637b",
        0x10000, 0x6C000),
)


@dataclass(frozen=True)
class ImageView:
    """Immutable bytes plus the logical flash offset of byte zero."""
    data: bytes
    base: int = 0

    def __post_init__(self):
        if self.base < 0:
            raise ImageFormatError(f"negative image base 0x{self.base:x}")
        if len(self.data) % 4:
            raise ImageFormatError(
                f"image size 0x{len(self.data):x} is not word-aligned")

    @property
    def size(self):
        return len(self.data)

    @property
    def end(self):
        """Logical offset one past the last byte."""
        return self.base + len(self.data)

    def has(self, flash_off, size=1):
        return size >= 0 and self.base <= flash_off <= flash_off + size <= self.end

    def index(self, flash_off, size=1):
        """Translate a logical flash offset to a file index, or fail closed."""
        if not self.has(flash_off, size):
            raise ImageFormatError(
                f"flash range 0x{flash_off:x}..0x{flash_off + size:x} is absent "
                f"from image base 0x{self.base:x} size 0x{len(self.data):x}")
        return flash_off - self.base

    def read(self, flash_off, size):
        start = self.index(flash_off, size)
        return self.data[start:start + size]

    def u32(self, flash_off):
        return struct.unpack("<I", self.read(flash_off, 4))[0]

    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class Container:
    """A SNC7320A wrapper and its SN_BCFG boot-priority table."""
    name: str
    flash_off: int
    boot_ptr: int
    expected_boot_ptr: int
    declared_size: int
    slot0: int
    slot1: int
    snc_magic: bool
    bcfg_magic: bool


@dataclass(frozen=True)
class FwinHeader:
    """The SN_FWIN application header."""
    flash_off: int
    magic: bool
    version: str
    entry_ptr: int
    crc_gate: int


@dataclass(frozen=True)
class Record:
    """One SN_FWIN payload record. `length` always comes from this image."""
    index: int
    addr: int
    length: int
    stored_checksum: int
    dst: int

    @property
    def flash_off(self):
        return self.addr - FLASH_BASE

    @property
    def flash_end(self):
        return self.flash_off + self.length


@dataclass(frozen=True)
class WordSum:
    name: str
    lo: int
    hi: int
    stored: int
    computed: int

    @property
    def ok(self):
        return self.stored == self.computed


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool


@dataclass(frozen=True)
class Layout:
    """Pure parse result: what the bytes say, with no pass/fail policy."""
    base: int
    size: int
    sha256: str
    fwin: FwinHeader
    records: tuple
    containers: tuple
    skipped_containers: tuple


@dataclass(frozen=True)
class Validation:
    """Machine-readable validation result. Never parse the CLI text instead."""
    layout: Layout
    checks: tuple
    word_sums: tuple
    skipped_word_sums: tuple
    source: Optional[SourceSpec]
    unresolved: tuple = UNRESOLVED

    @property
    def ok(self):
        return all(check.ok for check in self.checks)


def crc32(data, init=0):
    return binascii.crc32(data, init) & M


def chunked_crc_sum(view, flash_off, length, chunk=CHUNK):
    """Reproduce FUN_00005028: sum of independent CRC-32s, one per chunk.

    The source advances its pointer by the word-aligned chunk size, which is
    kept here for bit-exact parity with the audited implementation; it can only
    differ from `size` on the final chunk, after which nothing is left to read.
    """
    if length <= 0:
        raise ImageFormatError(f"CRC length 0x{length:x} must be positive")
    start = view.index(flash_off, length)
    acc, pos, rem = 0, start, length
    while rem:
        size = min(rem, chunk)
        acc = (acc + crc32(view.data[pos:pos + size])) & M
        pos += size & 0xFFFFFFFC
        rem -= size
    return acc


def word_sum(view, lo, hi):
    """Return the WordSum for logical range [lo,hi): last word vs sum of rest."""
    if hi <= lo or (hi - lo) % 4:
        raise ImageFormatError(f"invalid word-sum range 0x{lo:x}..0x{hi:x}")
    words = struct.unpack(f"<{(hi - lo) // 4}I", view.read(lo, hi - lo))
    return WordSum("", lo, hi, words[-1], sum(words[:-1]) & M)


def parse_fwin(view):
    header = view.read(FWIN_OFF, FWIN_HEADER_SIZE)
    version = header[FWIN_VERSION_OFF:FWIN_VERSION_OFF + 8]
    entry_ptr, = struct.unpack_from("<I", header, FWIN_ENTRY_PTR_OFF)
    gate, = struct.unpack_from("<I", header, FWIN_GATE_OFF)
    return FwinHeader(
        flash_off=FWIN_OFF,
        magic=header[:8] == FWIN_MAGIC,
        version=version.split(b"\x00")[0].decode("ascii", "replace"),
        entry_ptr=entry_ptr,
        crc_gate=gate)


def parse_records(view):
    """Read the fixed eight-slot record table exactly as FUN_0000511c does.

    The bootloader scans `MAX_RECORDS` slots and processes every slot whose
    **length** field (record `+0x4`) is nonzero; log 75 shows the loop bound
    `uVar1 < 8` with no terminator condition. So:

    * a zero-length slot is a hole to skip, not the end of the table — later
      slots are still live and still contribute checksum dependencies;
    * a zero address with a nonzero length is an active slot with an invalid
      address, never an empty one, so it must fail rather than be dropped;
    * a fully populated eight-slot table is legal.

    Physical slot indices are preserved so a record's identity survives a hole.
    """
    table = FWIN_OFF + FWIN_REC0_OFF
    span = MAX_RECORDS * REC_STRIDE
    if not view.has(table, span):
        raise ImageFormatError(
            f"the fixed {MAX_RECORDS}-slot record table at 0x{table:x}.."
            f"0x{table + span:x} is truncated in this image")
    blob = view.read(table, span)
    records = []
    for index in range(MAX_RECORDS):
        addr, length, checksum, dst = struct.unpack_from(
            "<4I", blob, index * REC_STRIDE)
        if length == 0:
            continue
        record = Record(index, addr, length, checksum, dst)
        if addr < FLASH_BASE:
            raise ImageFormatError(
                f"record[{index}] has length 0x{length:x} but address "
                f"0x{addr:08x}, which is below the mapped flash base "
                f"0x{FLASH_BASE:08x}")
        view.index(record.flash_off, record.length)
        records.append(record)
    if not records:
        raise ImageFormatError(
            f"no slot in the {MAX_RECORDS}-slot record table has a nonzero length")
    return tuple(records)


def parse_containers(view):
    present, skipped = [], []
    for name, off, expected_ptr in CONTAINERS:
        if not view.has(off, CONTAINER_SPAN):
            skipped.append(name)
            continue
        blob = view.read(off, CONTAINER_SPAN)
        boot_ptr, declared = struct.unpack_from("<2I", blob, 0x10)
        slot0, slot1 = struct.unpack_from("<2I", blob, CONTAINER_SLOTS_OFF)
        present.append(Container(
            name=name, flash_off=off, boot_ptr=boot_ptr,
            expected_boot_ptr=expected_ptr, declared_size=declared,
            slot0=slot0, slot1=slot1,
            snc_magic=blob[:8] == SNC_MAGIC,
            bcfg_magic=blob[CONTAINER_BCFG_OFF:CONTAINER_BCFG_OFF + 8] == BCFG_MAGIC))
    return tuple(present), tuple(skipped)


def parse(view):
    """Parse an image of unknown provenance. Raises ImageFormatError only."""
    try:
        fwin = parse_fwin(view)
        records = parse_records(view)
        containers, skipped = parse_containers(view)
    except struct.error as exc:
        raise ImageFormatError(f"truncated structure: {exc}") from exc
    return Layout(
        base=view.base, size=view.size, sha256=view.sha256(), fwin=fwin,
        records=records, containers=containers, skipped_containers=skipped)


def find_source(view):
    """Return the allowlisted SourceSpec for this image, or None."""
    digest = view.sha256()
    for spec in SUPPORTED_SOURCES:
        if spec.sha256 == digest and spec.base == view.base and spec.size == view.size:
            return spec
    return None


def require_supported_source(view):
    """Gate for mutation tooling. Read-only analysis must not call this."""
    spec = find_source(view)
    if spec is None:
        raise UnsupportedSourceError(
            f"sha256={view.sha256()} base=0x{view.base:x} size=0x{view.size:x} "
            "is not an allowlisted mutation source")
    return spec


def validate(view):
    """Report every known constraint observable in this image."""
    layout = parse(view)
    checks = []
    word_sums, skipped_word_sums = [], []

    for container in layout.containers:
        name = container.name
        checks.append(Check(f"{name} SNC7320A magic", container.snc_magic))
        checks.append(Check(f"{name} SN_BCFG magic", container.bcfg_magic))
        checks.append(Check(f"{name} bootloader pointer",
                            container.boot_ptr == container.expected_boot_ptr))
        checks.append(Check(f"{name} declared size",
                            container.declared_size == EXPECTED_CONTAINER_SIZE))
        checks.append(Check(f"{name} slot0 -> SN_FWIN",
                            container.slot0 == FLASH_BASE + FWIN_OFF))
        checks.append(Check(f"{name} slot1 empty", container.slot1 == 0))

    checks.append(Check("SN_FWIN magic", layout.fwin.magic))
    checks.append(Check("SN_FWIN CRC-enable gate nonzero",
                        layout.fwin.crc_gate != 0))
    # `records[0]` is the first *active* slot, which is slot 0 in both preserved
    # images. The name is kept verbatim from analyze_boot_structures.py so results
    # stay comparable with log 92. This is an observed coincidence in these
    # releases, not a rule the bootloader enforces: FUN_00005240 dereferences the
    # entry pointer without consulting slot indices.
    checks.append(Check("entry equals record[0] address",
                        layout.fwin.entry_ptr == layout.records[0].addr))

    lo, hi = APPLICATION_REGION
    checks.append(Check("record ranges inside application region", all(
        lo <= record.flash_off and record.length > 0 and record.flash_end <= hi
        for record in layout.records)))

    for record in layout.records:
        computed = chunked_crc_sum(view, record.flash_off, record.length)
        checks.append(Check(f"record[{record.index}] checksum",
                            computed == record.stored_checksum))

    for name, region_lo, region_hi in WORD_SUM_REGIONS:
        if not view.has(region_lo, region_hi - region_lo):
            skipped_word_sums.append(name)
            continue
        result = word_sum(view, region_lo, region_hi)
        word_sums.append(WordSum(name, result.lo, result.hi,
                                 result.stored, result.computed))

    entry_sp, entry_reset = struct.unpack(
        "<2I", view.read(layout.fwin.entry_ptr - FLASH_BASE, 8))
    checks.append(Check("entry initial-SP in observed RAM ranges",
                        any(low < entry_sp <= high for low, high in SP_RANGES)))
    # The length bound is only meaningful when the entry pointer really is the
    # first active record's address; the check above is what establishes that.
    checks.append(Check("entry reset vector is Thumb and within record[0] length",
                        bool(entry_reset & 1)
                        and (entry_reset & ~1) < layout.records[0].length))

    for result in word_sums:
        checks.append(Check(f"{result.name} word-sum", result.ok))

    return Validation(
        layout=layout, checks=tuple(checks), word_sums=tuple(word_sums),
        skipped_word_sums=tuple(skipped_word_sums), source=find_source(view))


def to_dict(validation):
    """Deterministic machine-readable result. Key and list order are stable."""
    layout = validation.layout
    return {
        "base": layout.base,
        "checks": [{"name": c.name, "ok": c.ok} for c in validation.checks],
        "containers": [
            {
                "bcfg_magic": c.bcfg_magic,
                "boot_ptr": c.boot_ptr,
                "declared_size": c.declared_size,
                "expected_boot_ptr": c.expected_boot_ptr,
                "flash_off": c.flash_off,
                "name": c.name,
                "slot0": c.slot0,
                "slot1": c.slot1,
                "snc_magic": c.snc_magic,
            }
            for c in layout.containers
        ],
        "fwin": {
            "crc_gate": layout.fwin.crc_gate,
            "entry_ptr": layout.fwin.entry_ptr,
            "flash_off": layout.fwin.flash_off,
            "magic": layout.fwin.magic,
            "version": layout.fwin.version,
        },
        "ok": validation.ok,
        "records": [
            {
                "addr": r.addr,
                "dst": r.dst,
                "flash_end": r.flash_end,
                "flash_off": r.flash_off,
                "index": r.index,
                "length": r.length,
                "stored_checksum": r.stored_checksum,
            }
            for r in layout.records
        ],
        "sha256": layout.sha256,
        "size": layout.size,
        "skipped_containers": list(layout.skipped_containers),
        "skipped_word_sums": list(validation.skipped_word_sums),
        "source": None if validation.source is None else validation.source.name,
        "unresolved": list(validation.unresolved),
        "word_sums": [
            {
                "computed": w.computed,
                "hi": w.hi,
                "lo": w.lo,
                "name": w.name,
                "ok": w.ok,
                "stored": w.stored,
            }
            for w in validation.word_sums
        ],
    }


def report_lines(validation):
    layout = validation.layout
    lines = [
        "PROGRAM falchion_image",
        "PURPOSE shared offline image-format parse and validation",
        f"IMAGE_BASE 0x{layout.base:x}",
        f"IMAGE_SIZE 0x{layout.size:x}",
        f"IMAGE_SHA256 {layout.sha256}",
        f"SOURCE {validation.source.name if validation.source else 'unknown (analysis only)'}",
        f"FWIN flash_off=0x{layout.fwin.flash_off:x} magic={layout.fwin.magic} "
        f"format_version={layout.fwin.version!r} "
        f"entry_ptr=0x{layout.fwin.entry_ptr:08x} crc_gate={layout.fwin.crc_gate}",
    ]
    lines.append("PRESENT_CONTAINERS " + (
        ",".join(c.name for c in layout.containers) if layout.containers else "none"))
    for name in layout.skipped_containers:
        lines.append(f"  SKIP {name} container: absent from this image")
    for record in layout.records:
        lines.append(
            f"RECORD {record.index} addr=0x{record.addr:08x} "
            f"flash=0x{record.flash_off:x}..0x{record.flash_end:x} "
            f"len=0x{record.length:x} checksum=0x{record.stored_checksum:08x} "
            f"dst=0x{record.dst:08x}")
    for result in validation.word_sums:
        lines.append(
            f"WORD_SUM {result.name} range=0x{result.lo:x}..0x{result.hi:x} "
            f"stored=0x{result.stored:08x} computed=0x{result.computed:08x} "
            f"match={result.ok}")
    for name in validation.skipped_word_sums:
        lines.append(f"  SKIP {name} word-sum: region absent from this image")
    for check in validation.checks:
        lines.append(f"  {'PASS' if check.ok else 'FAIL'} {check.name}")
    lines.append(
        f"RESULT known_checks_ok={validation.ok} "
        f"checks_run={len(validation.checks)} "
        f"containers_skipped={len(layout.skipped_containers)} "
        f"word_sums_skipped={len(validation.skipped_word_sums)}")
    for line in validation.unresolved:
        lines.append(f"UNRESOLVED {line}")
    lines.append("LIMITATION Passing means the known constraints are internally "
                 "consistent. It does not prove an edited image boots.")
    return lines


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_BIN)
    parser.add_argument(
        "--base", type=lambda value: int(value, 0), default=0,
        help="flash offset represented by image byte zero (USB app dump: 0x10000)")
    parser.add_argument("--json", action="store_true",
                        help="emit the deterministic machine-readable result")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    data = args.image.read_bytes()
    try:
        validation = validate(ImageView(data, args.base))
    except ImageFormatError as exc:
        # Fail closed: one line, no traceback, no partial report.
        print(f"RESULT known_checks_ok=False error={exc}")
        return 1
    if args.json:
        print(json.dumps(to_dict(validation), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(validation)))
    return 0 if validation.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
