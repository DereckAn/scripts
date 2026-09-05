#!/usr/bin/env python3
"""Find function-pointer tables in an extracted image slice.

Read-only and offline. Phase 5A: Ghidra's call graph does not follow a call made
through a pointer held in a table, so most of the application's functions come
back unreached and every later subphase inherits that blindness. This tool finds
the tables in the flash bytes, so their targets can be seeded as functions and
reachability recomputed.

A candidate entry is a word with the Thumb bit set whose target, once that bit is
cleared, is an even address inside the image. A single such word proves nothing —
plenty of data words look like that — so a candidate is only reported as part of
a **table**: at least `MIN_ENTRIES` of them at a constant stride. That run
requirement is what separates a dispatch table from a coincidence, and it is
stated rather than tuned away.

Targets are still only *candidates*. Whether each one is really code is settled
by whether Ghidra can disassemble a function there, not by this tool.

No device access. Examples:
    python3 tool/find_pointer_tables.py
    python3 tool/find_pointer_tables.py --json
    python3 tool/find_pointer_tables.py --seed-args app
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import extract_installed_records as ex
import falchion_image as fi
import match_functions as mf
import reconstruct_decompress as rd

ROOT = Path(__file__).resolve().parent.parent
IMPORTS = ROOT / "ghidra/imports"
INVENTORIES = ROOT / "ghidra/inventories"
INSTALLED = (ROOT / "dumps/device"
             / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")
VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"

# A run shorter than this is not evidence of a table.
MIN_ENTRIES = 3
# Strides worth trying: a plain pointer array, then structures carrying one
# pointer per element.
STRIDES = (4, 8, 12, 16, 20, 24, 32)

# The entry image's vector table is a pointer array too, but it is decoded and
# seeded separately, so it is excluded here to avoid reporting it twice. The
# same span is also not code, so a "pointer" into it is not a function pointer:
# CODE_FLOOR is the first address in each image where code actually begins, and
# a target below it is rejected. Without that floor, structures whose words
# happen to carry the low bit produce targets like 0x00000004.
EXCLUDE = {"entry": ((0x0, 0x140),), "app": (), "ram": ()}
CODE_FLOOR = {"entry": 0x140, "app": 0x18000000, "ram": 0x18000000}
# The reconstructed decompress region sits *above* the code it points into, so
# for it the acceptance window cannot be "inside this slice". CODE_CEIL names
# the end of the runtime code the slice may legitimately point at; where it is
# absent the window ends at the slice itself, which is the original behaviour.
CODE_CEIL = {"ram": 0x1801EE84}


@dataclass(frozen=True)
class Table:
    """A run of Thumb pointers at a constant stride."""
    location: int
    stride: int
    entries: tuple

    @property
    def count(self):
        return len(self.entries)

    @property
    def end(self):
        return self.location + self.stride * (self.count - 1) + 4


@dataclass(frozen=True)
class Survey:
    program: str
    slice_name: str
    base: int
    size: int
    sha256: str
    tables: tuple
    known_targets: tuple
    new_targets: tuple
    loose_candidates: tuple


def candidates(data, base, excluded, code_floor, code_ceil=None):
    """Offsets holding a plausible Thumb pointer into this image's code."""
    if code_ceil is None:
        code_ceil = base + len(data)
    found = {}
    for offset in range(0, len(data) - 3, 4):
        address = base + offset
        if any(low <= address < high for low, high in excluded):
            continue
        word, = struct.unpack_from("<I", data, offset)
        target = word & ~1
        if not word & 1:
            continue
        # No alignment test here: clearing bit 0 always yields an even address,
        # so a "reject odd targets" branch would be dead code.
        if not code_floor <= target < code_ceil:
            continue
        found[address] = target
    return found


def find_tables(found):
    """Group candidates into constant-stride runs, longest stride-4 runs first."""
    tables = []
    claimed = set()
    for stride in STRIDES:
        for address in sorted(found):
            if address in claimed:
                continue
            run = []
            cursor = address
            while cursor in found and cursor not in claimed:
                run.append((cursor, found[cursor]))
                cursor += stride
            if len(run) < MIN_ENTRIES:
                continue
            tables.append(Table(address, stride, tuple(run)))
            claimed.update(item[0] for item in run)
    return tuple(sorted(tables, key=lambda table: table.location)), claimed


def survey(program, slice_name, base, data, known):
    excluded = EXCLUDE.get(program, ())
    found = candidates(data, base, excluded, CODE_FLOOR[program],
                       CODE_CEIL.get(program))
    tables, claimed = find_tables(found)
    targets = {target for table in tables for _address, target in table.entries}
    return Survey(
        program=program, slice_name=slice_name, base=base, size=len(data),
        sha256=ex.sha256(data), tables=tables,
        known_targets=tuple(sorted(targets & known)),
        new_targets=tuple(sorted(targets - known)),
        loose_candidates=tuple(sorted(
            (address, target) for address, target in found.items()
            if address not in claimed)))


def load(view, inventory_name, program, import_base):
    extraction = ex.extract(view)
    item, = [entry for entry in extraction.slices
             if entry.import_base == import_base]
    data = (IMPORTS / item.name).read_bytes()
    records, _header = mf.parse_inventory(
        (INVENTORIES / inventory_name).read_text())
    known = {record.entry for record in records}
    return survey(program, item.name, import_base, data, known)


def reconstructed(view, inventory_name):
    """Survey the decompressed scatter region, if it has been reconstructed.

    Ghidra cannot see this region at all: it exists only after the boot-time
    decompress, so a callback stored in it is invisible to every flash-only
    survey. Returns None when the region has not been written, so the two
    flash surveys behave exactly as they did before this was added.
    """
    result, payload = rd.reconstruct(view, "installed"
                                     if view.base == 0x10000 else "vendor")
    path = IMPORTS / result.name
    if not path.exists():
        return None
    records, _header = mf.parse_inventory(
        (INVENTORIES / inventory_name).read_text())
    known = {record.entry for record in records}
    return survey("ram", result.name, result.destination, path.read_bytes(),
                  known)


def build(image=INSTALLED, base=0x10000, tag="installed"):
    view = fi.ImageView(Path(image).read_bytes(), base)
    surveys = [load(view, f"{tag}_a.txt", "entry", 0x0),
               load(view, f"{tag}_b.txt", "app", 0x18000000)]
    region = reconstructed(view, f"{tag}_b.txt")
    if region is not None:
        surveys.append(region)
    return tuple(surveys)


def seed_arguments(survey_result):
    """`Name=0xaddr` pairs for FalchionSeedVectors.java, one per new target."""
    return tuple(f"PtrTarget_{target:08x}=0x{target:x}"
                 for target in survey_result.new_targets)


def to_dict(surveys):
    return {
        "code_ceilings": {name: value for name, value in CODE_CEIL.items()},
        "code_floors": {name: value for name, value in CODE_FLOOR.items()},
        "min_entries": MIN_ENTRIES,
        "strides": list(STRIDES),
        "surveys": [
            {
                "base": item.base,
                "known_targets": list(item.known_targets),
                "loose_candidates": [{"address": address, "target": target}
                                     for address, target in item.loose_candidates],
                "new_targets": list(item.new_targets),
                "program": item.program,
                "seed_arguments": list(seed_arguments(item)),
                "sha256": item.sha256,
                "size": item.size,
                "slice": item.slice_name,
                "tables": [
                    {"count": table.count, "end": table.end,
                     "entries": [{"address": address, "target": target}
                                 for address, target in table.entries],
                     "location": table.location, "stride": table.stride}
                    for table in item.tables
                ],
            }
            for item in surveys
        ],
    }


def report_lines(surveys):
    out = [
        "PROGRAM find_pointer_tables",
        "PURPOSE locate function-pointer tables so their targets can be seeded",
        f"RULE a run of at least {MIN_ENTRIES} Thumb pointers at a constant "
        f"stride from {STRIDES}, each targeting an even address at or above the "
        "image's first code address. A lone word that looks like a pointer is "
        "not reported as a table.",
    ]
    for item in surveys:
        out += [
            "",
            f"IMAGE {item.program} base=0x{item.base:08x} "
            f"size=0x{item.size:x} code_floor=0x{CODE_FLOOR[item.program]:x}",
            f"  slice={item.slice_name}",
            f"  sha256={item.sha256}",
            f"  tables={len(item.tables)} "
            f"entries={sum(table.count for table in item.tables)} "
            f"known_targets={len(item.known_targets)} "
            f"new_targets={len(item.new_targets)} "
            f"loose_candidates={len(item.loose_candidates)}",
        ]
        if EXCLUDE.get(item.program):
            out.append("  excluded=" + ", ".join(
                f"0x{low:x}..0x{high:x}"
                for low, high in EXCLUDE[item.program])
                + " (decoded and seeded separately)")
        for table in item.tables:
            out.append(f"  TABLE 0x{table.location:08x}..0x{table.end:08x} "
                       f"stride={table.stride} entries={table.count}")
            for address, target in table.entries:
                out.append(f"    0x{address:08x} -> 0x{target:08x}")
        if item.new_targets:
            out.append("  NEW_TARGETS " + ", ".join(
                f"0x{target:08x}" for target in item.new_targets))
        for address, target in item.loose_candidates:
            out.append(f"  LOOSE 0x{address:08x} -> 0x{target:08x} "
                       "(not part of any run; not reported as a table entry)")
    out += [
        "",
        f"RESULT tables={sum(len(item.tables) for item in surveys)} "
        f"new_targets={sum(len(item.new_targets) for item in surveys)}",
        "LIMITATION A target here is a candidate, not a proven function. Whether "
        "it is code is settled by whether Ghidra disassembles a function at it.",
        "LIMITATION Only tables present in the surveyed slices are visible. The "
        "decompressed region is now surveyed as well, but a callback written "
        "into RAM at runtime, by code rather than by an initialiser, still "
        "cannot appear here.",
    ]
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--seed-args", choices=("entry", "app", "ram"),
                        help="print only the seed arguments for one image")
    parser.add_argument("--vendor", action="store_true",
                        help="survey the vendor image instead")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.vendor:
            surveys = build(VENDOR, 0x0, "vendor")
        else:
            surveys = build()
    except (OSError, ValueError, fi.ImageFormatError, ex.ExtractError) as exc:
        print(f"RESULT tables=0 error={exc}")
        return 1
    if args.seed_args:
        item, = [entry for entry in surveys if entry.program == args.seed_args]
        print(" ".join(seed_arguments(item)))
        return 0
    if args.json:
        print(json.dumps(to_dict(surveys), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(surveys)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
