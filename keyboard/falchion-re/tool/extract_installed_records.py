#!/usr/bin/env python3
"""Extract the installed application's code images and map them to runtime.

Read-only with respect to every dump. Slices are written under the ignored
`ghidra/imports/` area, never into `dumps/`, and every output byte is proved to
round-trip against the source range it came from.

Nothing here is taken from the vendor 1.00.58 image. Record addresses and lengths
come from the installed SN_FWIN table via the Phase-1 parser, and the runtime
layout comes from Candidate A's own scatter-region table, located by structure
and then cross-checked against three independent facts:

  * region 0's source and destination equal the SN_FWIN record they load;
  * the regions are contiguous in both flash and RAM;
  * the last region's RAM end equals the entry image's initial stack pointer.

If any of those fail the tool refuses rather than emitting a map.

No device access. Examples:
    python3 tool/extract_installed_records.py
    python3 tool/extract_installed_records.py --write --json
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Optional

import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = (ROOT / "dumps/device"
                 / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")
DEFAULT_BASE = 0x10000
DEFAULT_OUT = ROOT / "ghidra/imports"

REGION_ENTRY_SIZE = 0x10
MAX_REGIONS = 8
# Region handlers, identified in log 73 from the vendor bytes. Kept as evidence
# labels only: the tool checks that the installed image still points at the same
# handler offsets, and reports it if it does not.
KNOWN_HANDLERS = {
    0x17C: "__scatterload_decompress",
    0x1D8: "__scatterload_copy",
    0x1F4: "__scatterload_zeroinit",
}
RAM_RANGES = ((0x18000000, 0x18040000), (0x20000000, 0x20001000))


class ExtractError(ValueError):
    """The installed image does not support an evidence-based extraction."""


@dataclass(frozen=True)
class Slice:
    """One extracted byte range, with the source it must round-trip against.

    `import_base` is None for a complete-record slice that is not a single
    runtime image, such as a record made of a copy source plus a compressed
    tail. Those exist so every active record byte is represented on disk, not to
    be loaded at one address.
    """
    name: str
    slot: int
    role: str
    source_lo: int
    source_hi: int
    import_base: Optional[int]
    import_base_basis: str
    sha256: str

    @property
    def length(self):
        return self.source_hi - self.source_lo


@dataclass(frozen=True)
class Region:
    """One Candidate A scatter-region descriptor, read from installed bytes."""
    index: int
    src: int
    dst: int
    size: int
    handler: int
    handler_name: str

    @property
    def src_flash(self):
        return self.src - fi.FLASH_BASE

    @property
    def dst_end(self):
        return self.dst + self.size


@dataclass(frozen=True)
class RuntimeRange:
    """A runtime RAM range and the loader evidence that puts it there."""
    lo: int
    hi: int
    kind: str
    basis: str
    source_lo: Optional[int]
    source_hi: Optional[int]
    materialized: bool

    @property
    def length(self):
        return self.hi - self.lo


@dataclass(frozen=True)
class CoverageRun:
    """A span of the source image and what structure claims it."""
    lo: int
    hi: int
    role: str
    fill: str

    @property
    def length(self):
        return self.hi - self.lo


@dataclass(frozen=True)
class Extraction:
    image_sha256: str
    base: int
    size: int
    source: object
    entry_ptr: int
    entry_sp: int
    entry_reset: int
    region_table: int
    regions: tuple
    slices: tuple
    runtime: tuple
    coverage: tuple
    checks: tuple


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def merge_spans(spans):
    """Merge possibly overlapping (lo, hi) spans into maximal ones."""
    merged = []
    for lo, hi in sorted(spans):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return tuple(merged)


def in_ram(address):
    return any(low <= address < high for low, high in RAM_RANGES)


def read_region(view, offset, index):
    src, dst, size, handler = struct.unpack("<4I", view.read(offset, REGION_ENTRY_SIZE))
    return Region(index=index, src=src, dst=dst, size=size, handler=handler,
                  handler_name=KNOWN_HANDLERS.get(handler, "unidentified"))


def locate_region_table(view, layout):
    """Find Candidate A's scatter-region table by structure, not by a vendor offset.

    The table is recognised only when its first entry loads exactly the SN_FWIN
    record that Candidate A is known to pull in, so a coincidental byte pattern
    cannot be mistaken for it.
    """
    entry = layout.records[0]
    payload = layout.records[1]
    lo = entry.flash_off
    hi = entry.flash_end - REGION_ENTRY_SIZE
    hits = []
    for offset in range(lo, hi + 1, 4):
        src, dst, size, _handler = struct.unpack(
            "<4I", view.read(offset, REGION_ENTRY_SIZE))
        if src == payload.addr and in_ram(dst) and 0 < size <= payload.length:
            hits.append(offset)
    if len(hits) != 1:
        raise ExtractError(
            f"expected exactly one scatter-region table in the entry image, "
            f"found {len(hits)}: "
            + ", ".join(f"0x{offset:x}" for offset in hits))
    return hits[0]


def read_regions(view, table):
    """Read consecutive region descriptors while they stay self-consistent."""
    regions = []
    for index in range(MAX_REGIONS):
        offset = table + index * REGION_ENTRY_SIZE
        if not view.has(offset, REGION_ENTRY_SIZE):
            break
        region = read_region(view, offset, index)
        if not in_ram(region.dst) or region.size == 0:
            break
        if regions and region.dst != regions[-1].dst_end:
            break
        regions.append(region)
    if not regions:
        raise ExtractError("no usable scatter-region descriptor at the table")
    return tuple(regions)


def extract(view, out_dir=DEFAULT_OUT, write=False):
    layout = fi.parse(view)
    entry = layout.records[0]
    payload = layout.records[1]
    entry_sp, entry_reset = struct.unpack(
        "<2I", view.read(layout.fwin.entry_ptr - fi.FLASH_BASE, 8))

    table = locate_region_table(view, layout)
    regions = read_regions(view, table)

    checks = []

    def check(name, ok, detail=""):
        checks.append(fi.Check(f"{name}{(' — ' + detail) if detail else ''}", ok))
        return ok

    check("entry pointer is record slot 0",
          layout.fwin.entry_ptr == entry.addr,
          f"0x{layout.fwin.entry_ptr:08x}")
    check("region table lies inside the entry image",
          entry.flash_off <= table < entry.flash_end,
          f"0x{table:x} in 0x{entry.flash_off:x}..0x{entry.flash_end:x}")
    check("region 0 source is record slot 1",
          regions[0].src == payload.addr, f"0x{regions[0].src:08x}")
    check("region destinations are contiguous", all(
        regions[i].dst_end == regions[i + 1].dst
        for i in range(len(regions) - 1)))
    check("last region RAM end equals the entry initial stack pointer",
          regions[-1].dst_end == entry_sp,
          f"0x{regions[-1].dst_end:08x} vs 0x{entry_sp:08x}")
    check("every region handler is one identified in log 73",
          all(region.handler_name != "unidentified" for region in regions),
          ", ".join(f"0x{region.handler:x}={region.handler_name}"
                    for region in regions))

    # Input spans, which are not the same as the region sizes: a copy region's
    # size is both its input and output length, but a decompressor's size is the
    # *output* length only. Its input length is not in the table, so it is taken
    # as running to wherever the next region's source starts, and the tiling
    # check below is what makes that safe rather than assumed.
    flash_backed = [region for region in regions
                    if region.handler_name != "__scatterload_zeroinit"]
    flash_spans = []
    for position, region in enumerate(flash_backed):
        if region.handler_name == "__scatterload_copy":
            span = (region.src_flash, region.src_flash + region.size)
        elif position + 1 < len(regions):
            span = (region.src_flash, regions[position + 1].src_flash)
        else:
            span = (region.src_flash, payload.flash_end)
        flash_spans.append((region, span))

    tiled = (bool(flash_spans)
             and flash_spans[0][1][0] == payload.flash_off
             and flash_spans[-1][1][1] == payload.flash_end
             and all(flash_spans[i][1][1] == flash_spans[i + 1][1][0]
                     for i in range(len(flash_spans) - 1))
             and all(lo < hi for _region, (lo, hi) in flash_spans))
    check("flash-backed region inputs tile record slot 1 exactly", tiled,
          " + ".join(f"0x{lo:x}..0x{hi:x}" for _region, (lo, hi) in flash_spans)
          + f" == 0x{payload.flash_off:x}..0x{payload.flash_end:x}")

    prefix = source_tag(fi.find_source(view))
    slices = []

    # One complete slice per active record, so every active record byte is
    # represented on disk rather than only the parts that happen to be loadable.
    for record in layout.records:
        data = view.read(record.flash_off, record.length)
        if record.index == entry.index:
            tag, base = "app_a", 0x0
            role = "complete SN_FWIN record and the entry image, executed in place"
            basis = (
                "linked at 0: the reset vector 0x%08x, the region table at 0x%x "
                "and its handler pointers are all base-0 offsets within this "
                "image" % (entry_reset, table - entry.flash_off))
        else:
            tag, base = f"rec{record.index}", None
            role = ("complete SN_FWIN record: scatter region sources "
                    + " + ".join(
                        f"{region.handler_name} 0x{lo:x}..0x{hi:x}"
                        for region, (lo, hi) in flash_spans)
                    + " — not one runtime image, so it has no import base")
            basis = ("kept whole so the round-trip gate covers every active "
                     "record byte; the loadable part is extracted separately")
        slices.append(Slice(
            name=slice_name(prefix, tag, record.index, record.flash_off, base,
                            record.length, data),
            slot=record.index, role=role,
            source_lo=record.flash_off, source_hi=record.flash_end,
            import_base=base, import_base_basis=basis, sha256=sha256(data)))

    for region, (lo, hi) in flash_spans:
        if region.handler_name != "__scatterload_copy":
            continue
        data = view.read(lo, hi - lo)
        slices.append(Slice(
            name=slice_name(prefix, "app_b", payload.index, lo, region.dst,
                            hi - lo, data),
            slot=payload.index,
            role=f"runtime image from scatter region {region.index}, "
                 f"{region.handler_name}",
            source_lo=lo, source_hi=hi, import_base=region.dst,
            import_base_basis=(
                "Candidate A region %d copies flash 0x%x..0x%x to RAM "
                "0x%08x..0x%08x" % (region.index, lo, hi, region.dst,
                                    region.dst_end)),
            sha256=sha256(data)))
    slices = tuple(slices)

    covered = merge_spans((item.source_lo, item.source_hi) for item in slices)
    check("every active record byte is covered by an extracted slice", all(
        any(lo <= record.flash_off and record.flash_end <= hi
            for lo, hi in covered)
        for record in layout.records),
        "; ".join(f"slot {record.index} 0x{record.flash_off:x}.."
                  f"0x{record.flash_end:x}" for record in layout.records))

    runtime = []
    for region, (lo, hi) in flash_spans:
        materialized = region.handler_name == "__scatterload_copy"
        runtime.append(RuntimeRange(
            lo=region.dst, hi=region.dst_end, kind=region.handler_name,
            basis=f"Candidate A region {region.index} at "
                  f"0x{table + region.index * REGION_ENTRY_SIZE:x}, source "
                  f"0x{region.src:08x} inside SN_FWIN record slot {payload.index}",
            source_lo=lo, source_hi=hi, materialized=materialized))
    for region in regions:
        if region.handler_name != "__scatterload_zeroinit":
            continue
        runtime.append(RuntimeRange(
            lo=region.dst, hi=region.dst_end, kind=region.handler_name,
            basis=f"Candidate A region {region.index} at "
                  f"0x{table + region.index * REGION_ENTRY_SIZE:x}, zero-filled "
                  f"with no flash source",
            source_lo=None, source_hi=None, materialized=True))
    runtime = tuple(sorted(runtime, key=lambda item: item.lo))

    check("every extracted byte round-trips to its source range", all(
        sha256(view.read(item.source_lo, item.length)) == item.sha256
        for item in slices))

    # Nothing is written until every check has passed. A failed check means the
    # map is not trustworthy, and emitting slices anyway would leave unexplained
    # files behind next to a non-zero exit.
    if write:
        failed = [item.name for item in checks if not item.ok]
        if failed:
            raise ExtractError(
                "refusing to write slices because "
                + str(len(failed)) + " check(s) failed: " + "; ".join(failed))
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in slices:
            data = view.read(item.source_lo, item.length)
            if sha256(data) != item.sha256:
                raise ExtractError(f"{item.name} changed under us; refusing to write")
            (out_dir / item.name).write_bytes(data)

    return Extraction(
        image_sha256=view.sha256(), base=view.base, size=view.size,
        source=fi.find_source(view), entry_ptr=layout.fwin.entry_ptr,
        entry_sp=entry_sp, entry_reset=entry_reset, region_table=table,
        regions=regions, slices=slices, runtime=runtime,
        coverage=source_coverage(view, layout, flash_spans),
        checks=tuple(checks))


def source_tag(source):
    """Short prefix identifying which allowlisted image a slice came from."""
    return "image" if source is None else source.name.split("-")[0]


def slice_name(prefix, tag, slot, flash_lo, runtime_base, length, data):
    """Encode slot, logical source, runtime destination, length and a short hash.

    `runtime_base` is the destination the loader evidence supports, not the
    SN_FWIN record's `+0xc` word, which `FUN_0000511c` never reads. `None`
    renders as `dstNA`, for a complete record that is not one runtime image.
    """
    destination = "NA" if runtime_base is None else f"{runtime_base:08x}"
    return (f"{prefix}_{tag}_slot{slot}_flash{flash_lo:05x}_dst{destination}"
            f"_len{length:05x}_{sha256(data)[:8]}.bin")


def source_coverage(view, layout, flash_spans):
    """Account for every byte of the source image, including the gaps."""
    claimed = [
        (fi.FWIN_OFF, fi.FWIN_OFF + fi.FWIN_REC0_OFF, "SN_FWIN header"),
        (fi.FWIN_OFF + fi.FWIN_REC0_OFF,
         fi.FWIN_OFF + fi.FWIN_REC0_OFF + fi.MAX_RECORDS * fi.REC_STRIDE,
         f"SN_FWIN {fi.MAX_RECORDS}-slot record table"),
        (layout.records[0].flash_off, layout.records[0].flash_end,
         f"record slot {layout.records[0].index} payload (entry image)"),
    ]
    for region, (lo, hi) in flash_spans:
        claimed.append((lo, hi, f"record slot {layout.records[1].index} "
                                f"region {region.index} ({region.handler_name} source)"))
    for name, off, _ptr in fi.CONTAINERS:
        if view.has(off, fi.CONTAINER_SPAN):
            claimed.append((off, off + fi.CONTAINER_SPAN, f"{name} container header"))
    for name, lo, hi in fi.WORD_SUM_REGIONS:
        if name == "bootloader_mirror" and view.has(lo, hi - lo):
            claimed.append((lo, hi, "mirrored bootloader copy"))
    claimed.sort()

    runs = []
    cursor = view.base
    for lo, hi, role in claimed:
        if lo > cursor:
            runs.append(gap_run(view, cursor, lo))
        if hi > cursor:
            runs.append(CoverageRun(max(lo, cursor), hi, role,
                                    fill_of(view, max(lo, cursor), hi)))
            cursor = hi
    if cursor < view.end:
        runs.append(gap_run(view, cursor, view.end))
    return tuple(runs)


def fill_of(view, lo, hi):
    return fi.classify_fill(view.read(lo, hi - lo))


def gap_run(view, lo, hi):
    return CoverageRun(lo, hi, "unclaimed by any parsed structure",
                       fill_of(view, lo, hi))


def to_dict(extraction):
    """Deterministic machine-readable extraction result."""
    return {
        "base": extraction.base,
        "checks": [{"name": check.name, "ok": check.ok}
                   for check in extraction.checks],
        "coverage": [
            {"fill": run.fill, "hi": run.hi, "length": run.length, "lo": run.lo,
             "role": run.role}
            for run in extraction.coverage
        ],
        "entry": {"initial_sp": extraction.entry_sp, "pointer": extraction.entry_ptr,
                  "reset_vector": extraction.entry_reset},
        "image_sha256": extraction.image_sha256,
        "ok": all(check.ok for check in extraction.checks),
        "region_table": extraction.region_table,
        "regions": [
            {"dst": region.dst, "dst_end": region.dst_end, "handler": region.handler,
             "handler_name": region.handler_name, "index": region.index,
             "size": region.size, "src": region.src, "src_flash": region.src_flash}
            for region in extraction.regions
        ],
        "runtime": [
            {"basis": item.basis, "hi": item.hi, "kind": item.kind,
             "length": item.length, "lo": item.lo,
             "materialized": item.materialized,
             "source_hi": item.source_hi, "source_lo": item.source_lo}
            for item in extraction.runtime
        ],
        "size": extraction.size,
        "slices": [
            {"import_base": item.import_base,
             "import_base_basis": item.import_base_basis,
             "length": item.length, "name": item.name, "role": item.role,
             "sha256": item.sha256, "slot": item.slot,
             "source_hi": item.source_hi, "source_lo": item.source_lo}
            for item in extraction.slices
        ],
        "source": None if extraction.source is None else extraction.source.name,
    }


def report_lines(extraction):
    out = [
        "PROGRAM extract_installed_records",
        "PURPOSE installed record extraction and runtime map",
        f"IMAGE_BASE 0x{extraction.base:x}",
        f"IMAGE_SIZE 0x{extraction.size:x}",
        f"IMAGE_SHA256 {extraction.image_sha256}",
        f"SOURCE {extraction.source.name if extraction.source else 'unknown'}",
        f"ENTRY pointer=0x{extraction.entry_ptr:08x} "
        f"initial_sp=0x{extraction.entry_sp:08x} "
        f"reset=0x{extraction.entry_reset:08x}",
        f"REGION_TABLE flash=0x{extraction.region_table:x}",
    ]
    for region in extraction.regions:
        out.append(
            f"REGION {region.index} src=0x{region.src:08x} "
            f"(flash 0x{region.src_flash:x}) dst=0x{region.dst:08x}.."
            f"0x{region.dst_end:08x} size=0x{region.size:x} "
            f"handler=0x{region.handler:x} {region.handler_name}")
    for item in extraction.slices:
        out += [
            f"SLICE {item.name}",
            f"  slot={item.slot} role={item.role}",
            f"  source=0x{item.source_lo:x}..0x{item.source_hi:x} "
            f"(0x{item.length:x} bytes) sha256={item.sha256}",
            "  import_base=" + ("none" if item.import_base is None
                                    else f"0x{item.import_base:08x}"),
            f"  basis={item.import_base_basis}",
        ]
    for item in extraction.runtime:
        source = ("none (zero-filled)" if item.source_lo is None
                  else f"0x{item.source_lo:x}..0x{item.source_hi:x}")
        out += [
            f"RUNTIME 0x{item.lo:08x}..0x{item.hi:08x} (0x{item.length:x}) "
            f"{item.kind} materialized={item.materialized}",
            f"  source={source}",
            f"  basis={item.basis}",
        ]
    for run in extraction.coverage:
        out.append(f"COVERAGE 0x{run.lo:x}..0x{run.hi:x} (0x{run.length:x}) "
                   f"fill={run.fill} {run.role}")
    for check in extraction.checks:
        out.append(f"  {'PASS' if check.ok else 'FAIL'} {check.name}")
    ok = all(check.ok for check in extraction.checks)
    out.append(f"RESULT extraction_ok={ok} checks_run={len(extraction.checks)} "
               f"slices={len(extraction.slices)} "
               f"runtime_ranges={len(extraction.runtime)}")
    for line in fi.UNRESOLVED:
        out.append(f"UNRESOLVED {line}")
    out.append("UNRESOLVED The SN_FWIN record word at +0xc is not read by "
               "FUN_0000511c, so calling it a RAM destination is an assumption, "
               "not recovered behavior.")
    out.append("UNRESOLVED The decompressed RAM range is located and sized by "
               "the region table, but its contents are not reconstructed here, "
               "so its runtime bytes are mapped rather than known.")
    out.append("UNRESOLVED The separately documented RAM image at flash "
               "0x74000..0x7c000 (log 43) is reachable from no SN_FWIN record "
               "and no scatter region on this path, so how it is loaded is not "
               "established by this extraction.")
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--base", type=lambda value: int(value, 0),
                        default=DEFAULT_BASE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="ignored Ghidra import directory for the slices")
    parser.add_argument("--write", action="store_true",
                        help="write the slices (never touches dumps/)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--analysis-only", action="store_true",
                        help="permit an image that is not an allowlisted source")
    return parser.parse_args(argv)


def main(argv=None):
    import sys
    args = parse_args(argv)
    try:
        view = fi.ImageView(args.image.read_bytes(), args.base)
    except fi.ImageFormatError as exc:
        print(f"RESULT extraction_ok=False error={exc}")
        return 1
    if fi.find_source(view) is None:
        if not args.analysis_only:
            print("RESULT extraction_ok=False error=unknown source image; "
                  "expected an allowlisted SHA-256/base/size tuple. Re-run with "
                  "--analysis-only to extract anyway.")
            return 1
        print("WARNING the image is not an allowlisted source; the extraction "
              "describes bytes of unverified provenance.", file=sys.stderr)
    if args.out.resolve().is_relative_to((ROOT / "dumps").resolve()):
        print("RESULT extraction_ok=False error=refusing to write slices under dumps/")
        return 1
    try:
        extraction = extract(view, args.out, args.write)
    except (fi.ImageFormatError, ExtractError) as exc:
        print(f"RESULT extraction_ok=False error={exc}")
        return 1
    if args.json:
        print(json.dumps(to_dict(extraction), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(extraction)))
    return 0 if all(check.ok for check in extraction.checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
