#!/usr/bin/env python3
"""Offline comparison of the installed 1.59 application dump with vendor 1.00.58.

Read-only. Establishes *what* changed between the two preserved images. It does
not interpret why: a changed byte range is a fact, its purpose is a later
hypothesis, and nothing here infers function semantics.

The installed dump covers logical flash `[0x10000,0x7c000)`. The vendor file is a
full image based at `0`, so it is compared over the *same logical range*, never
byte 0 against byte 0. All structure parsing, offset translation and checksum
policy come from `falchion_image`; this module adds no second SN_FWIN parser.

By default both inputs must be allowlisted sources. `--analysis-only` lifts that
after printing a warning, for inspecting an image nobody has vouched for.

No device access. Examples:
    python3 tool/compare_firmware_images.py
    python3 tool/compare_firmware_images.py --json
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Optional

import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VENDOR = ROOT / "dumps/vendor/M605_V01_00_58.bin"
DEFAULT_INSTALLED = (ROOT / "dumps/device"
                     / "ROG_Falchion_Ace_HFX_installed_bcdDevice_1.59_app_0x10000_0x7bfff.bin")

# The installed dump's extent, and therefore the comparable logical range.
COMPARE_RANGE = fi.APPLICATION_REGION
PAGE = 0x1000

# The mirrored bootloader copy and the two vendor ranges it should equal.
MIRROR_RANGE = (0x61000, 0x71000)
VENDOR_PRIMARY_RANGE = (0x00000, 0x10000)

STRING_RE = re.compile(rb"[\x20-\x7e]{6,}")
STRING_MATCH_CUTOFF = 0.8


class ComparisonError(ValueError):
    """The two images cannot be compared as requested."""


@dataclass(frozen=True)
class Span:
    """A logical flash range [lo,hi)."""
    lo: int
    hi: int

    @property
    def length(self):
        return self.hi - self.lo


@dataclass(frozen=True)
class PageCompare:
    lo: int
    hi: int
    installed_sha256: str
    vendor_sha256: str
    installed_kind: str
    vendor_kind: str
    differing_bytes: int

    @property
    def changed(self):
        return self.installed_sha256 != self.vendor_sha256


@dataclass(frozen=True)
class RegionRun:
    """Consecutive pages sharing the same change state and fill classification."""
    lo: int
    hi: int
    changed: bool
    installed_kind: str
    vendor_kind: str
    pages: int


@dataclass(frozen=True)
class RecordCompare:
    """Both images' complete record fields for one physical slot.

    `installed_only` / `vendor_only` carry the tail that exists in one image and
    has no counterpart in the other, so a length change is never disclosed as a
    bare scalar.
    """
    slot: int
    installed_length: int
    vendor_length: int
    installed_sha256: str
    vendor_sha256: str
    installed_addr: int
    vendor_addr: int
    installed_dst: int
    vendor_dst: int
    installed_stored_checksum: int
    vendor_stored_checksum: int
    overlap: int
    differing_bytes: int
    differing_ranges: tuple
    installed_only: Optional[Span]
    vendor_only: Optional[Span]

    @property
    def length_delta(self):
        return self.installed_length - self.vendor_length

    @property
    def addr_changed(self):
        return self.installed_addr != self.vendor_addr

    @property
    def dst_changed(self):
        return self.installed_dst != self.vendor_dst

    @property
    def checksum_changed(self):
        return self.installed_stored_checksum != self.vendor_stored_checksum


@dataclass(frozen=True)
class MirrorCompare:
    installed_mirror_sha256: str
    vendor_mirror_sha256: str
    vendor_primary_sha256: str
    installed_vs_vendor_mirror: tuple
    installed_vs_vendor_primary: tuple


@dataclass(frozen=True)
class StringCompare:
    """Comparison of ASCII runs by value and by occurrence count.

    `distinct_common` counts values present in both images. `count_changed`
    catches a value whose number of occurrences moved, which a set comparison
    alone would hide. Offsets are not compared here; the byte-range diff already
    carries position.
    """
    added: tuple
    removed: tuple
    changed: tuple
    count_changed: tuple
    distinct_common: int
    installed_distinct: int
    vendor_distinct: int
    installed_occurrences: int
    vendor_occurrences: int
    multisets_equal: bool


@dataclass(frozen=True)
class Comparison:
    range: Span
    installed_sha256: str
    vendor_sha256: str
    installed_range_sha256: str
    vendor_range_sha256: str
    equal: bool
    differing_bytes: int
    differing_ranges: tuple
    pages: tuple
    regions: tuple
    records: tuple
    mirror: MirrorCompare
    strings: StringCompare
    installed_validation: fi.Validation
    vendor_validation: fi.Validation
    installed_source: object
    vendor_source: object

    @property
    def changed_pages(self):
        return tuple(page for page in self.pages if page.changed)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# Re-exported so existing callers and tests keep one import site.
classify_fill = fi.classify_fill


def diff_ranges(left, right, base):
    """Contiguous logical ranges where the two equal-length buffers differ."""
    if len(left) != len(right):
        raise ComparisonError(
            f"cannot diff 0x{len(left):x} bytes against 0x{len(right):x}")
    ranges = []
    start = None
    for index in range(len(left)):
        if left[index] != right[index]:
            if start is None:
                start = index
        elif start is not None:
            ranges.append(Span(base + start, base + index))
            start = None
    if start is not None:
        ranges.append(Span(base + start, base + len(left)))
    return tuple(ranges)


def compare_pages(installed, vendor, span):
    pages = []
    for lo in range(span.lo, span.hi, PAGE):
        hi = min(lo + PAGE, span.hi)
        left = installed.read(lo, hi - lo)
        right = vendor.read(lo, hi - lo)
        pages.append(PageCompare(
            lo=lo, hi=hi,
            installed_sha256=sha256(left), vendor_sha256=sha256(right),
            installed_kind=classify_fill(left), vendor_kind=classify_fill(right),
            differing_bytes=sum(1 for a, b in zip(left, right) if a != b)))
    return tuple(pages)


def collapse_regions(pages):
    runs = []
    for page in pages:
        key = (page.changed, page.installed_kind, page.vendor_kind)
        if runs and runs[-1][0] == key and runs[-1][1].hi == page.lo:
            previous = runs[-1][1]
            runs[-1] = (key, RegionRun(
                lo=previous.lo, hi=page.hi, changed=page.changed,
                installed_kind=page.installed_kind, vendor_kind=page.vendor_kind,
                pages=previous.pages + 1))
        else:
            runs.append((key, RegionRun(
                lo=page.lo, hi=page.hi, changed=page.changed,
                installed_kind=page.installed_kind,
                vendor_kind=page.vendor_kind, pages=1)))
    return tuple(run for _key, run in runs)


def compare_records(installed, vendor, installed_layout, vendor_layout):
    by_slot = {}
    for layout, key in ((installed_layout, "installed"), (vendor_layout, "vendor")):
        for record in layout.records:
            by_slot.setdefault(record.index, {})[key] = record
    results = []
    for slot in sorted(by_slot):
        pair = by_slot[slot]
        left = pair.get("installed")
        right = pair.get("vendor")
        if left is None or right is None:
            raise ComparisonError(
                f"record slot {slot} is active in only one image; that is a "
                "layout change this comparator does not model")
        left_bytes = installed.read(left.flash_off, left.length)
        right_bytes = vendor.read(right.flash_off, right.length)
        overlap = min(left.length, right.length)
        if left.flash_off != right.flash_off:
            raise ComparisonError(
                f"record slot {slot} moved from 0x{right.flash_off:x} to "
                f"0x{left.flash_off:x}; ranges are not comparable in place")
        ranges = diff_ranges(left_bytes[:overlap], right_bytes[:overlap],
                             left.flash_off)
        tail_lo = left.flash_off + overlap
        results.append(RecordCompare(
            slot=slot,
            installed_length=left.length, vendor_length=right.length,
            installed_sha256=sha256(left_bytes), vendor_sha256=sha256(right_bytes),
            installed_addr=left.addr, vendor_addr=right.addr,
            installed_dst=left.dst, vendor_dst=right.dst,
            installed_stored_checksum=left.stored_checksum,
            vendor_stored_checksum=right.stored_checksum,
            overlap=overlap,
            differing_bytes=sum(span.length for span in ranges),
            differing_ranges=ranges,
            installed_only=(Span(tail_lo, left.flash_end)
                            if left.length > overlap else None),
            vendor_only=(Span(tail_lo, right.flash_end)
                         if right.length > overlap else None)))
    return tuple(results)


def compare_mirror(installed, vendor):
    lo, hi = MIRROR_RANGE
    installed_mirror = installed.read(lo, hi - lo)
    vendor_mirror = vendor.read(lo, hi - lo)
    primary_lo, primary_hi = VENDOR_PRIMARY_RANGE
    vendor_primary = vendor.read(primary_lo, primary_hi - primary_lo)
    return MirrorCompare(
        installed_mirror_sha256=sha256(installed_mirror),
        vendor_mirror_sha256=sha256(vendor_mirror),
        vendor_primary_sha256=sha256(vendor_primary),
        installed_vs_vendor_mirror=diff_ranges(installed_mirror, vendor_mirror, lo),
        installed_vs_vendor_primary=diff_ranges(
            installed_mirror, vendor_primary, lo))


def drop_substrings(values):
    """Keep only maximal strings, so one edit does not report as ten hits."""
    ordered = sorted(values, key=lambda value: (-len(value), value))
    kept = []
    for value in ordered:
        if not any(value in longer for longer in kept):
            kept.append(value)
    return tuple(sorted(kept))


def compare_strings(installed, vendor, span):
    """Compare ASCII runs by value and by occurrence count.

    Counting occurrences, not just distinct values, is what keeps a change in how
    many times a string appears from vanishing into an unchanged set difference.
    """
    left_counts = Counter(match.group() for match in STRING_RE.finditer(
        installed.read(span.lo, span.length)))
    right_counts = Counter(match.group() for match in STRING_RE.finditer(
        vendor.read(span.lo, span.length)))
    left, right = set(left_counts), set(right_counts)
    added = drop_substrings(left - right)
    removed = drop_substrings(right - left)
    count_changed = tuple(
        (value, left_counts[value], right_counts[value])
        for value in sorted(left & right)
        if left_counts[value] != right_counts[value])

    # Pair a removed string with its closest addition so a rewritten string is
    # reported once as a change instead of twice as unrelated churn.
    changed = []
    remaining_added = list(added)
    remaining_removed = []
    for gone in removed:
        candidates = [value.decode("ascii") for value in remaining_added]
        matches = difflib.get_close_matches(
            gone.decode("ascii"), candidates, n=1, cutoff=STRING_MATCH_CUTOFF)
        if matches:
            new = matches[0].encode("ascii")
            remaining_added.remove(new)
            changed.append((gone, new))
        else:
            remaining_removed.append(gone)
    return StringCompare(
        added=tuple(remaining_added),
        removed=tuple(remaining_removed),
        changed=tuple(changed),
        count_changed=count_changed,
        distinct_common=len(left & right),
        installed_distinct=len(left), vendor_distinct=len(right),
        installed_occurrences=sum(left_counts.values()),
        vendor_occurrences=sum(right_counts.values()),
        multisets_equal=left_counts == right_counts)


def compare(installed, vendor, span=None):
    """Compare two ImageViews over their shared logical range."""
    lo, hi = span if span else COMPARE_RANGE
    region = Span(lo, hi)
    for name, view in (("installed", installed), ("vendor", vendor)):
        if not view.has(region.lo, region.length):
            raise ComparisonError(
                f"the {name} image does not cover logical "
                f"0x{region.lo:x}..0x{region.hi:x} at base 0x{view.base:x}")
    left = installed.read(region.lo, region.length)
    right = vendor.read(region.lo, region.length)
    pages = compare_pages(installed, vendor, region)
    ranges = diff_ranges(left, right, region.lo)
    installed_validation = fi.validate(installed)
    vendor_validation = fi.validate(vendor)
    return Comparison(
        range=region,
        installed_sha256=installed.sha256(), vendor_sha256=vendor.sha256(),
        installed_range_sha256=sha256(left), vendor_range_sha256=sha256(right),
        equal=left == right,
        differing_bytes=sum(item.length for item in ranges),
        differing_ranges=ranges,
        pages=pages,
        regions=collapse_regions(pages),
        records=compare_records(installed, vendor,
                                installed_validation.layout,
                                vendor_validation.layout),
        mirror=compare_mirror(installed, vendor),
        strings=compare_strings(installed, vendor, region),
        installed_validation=installed_validation,
        vendor_validation=vendor_validation,
        installed_source=fi.find_source(installed),
        vendor_source=fi.find_source(vendor))


def word_sums(validation):
    return {result.name: (result.stored, result.computed)
            for result in validation.word_sums}


def to_dict(comparison, analysis_only=False, unknown=()):
    """Deterministic machine-readable comparison. Complete, never truncated."""
    def span_list(spans):
        return [{"hi": span.hi, "length": span.length, "lo": span.lo}
                for span in spans]

    def sums(validation):
        return {
            "skipped": list(validation.skipped_word_sums),
            "regions": {
                result.name: {"computed": result.computed, "hi": result.hi,
                              "lo": result.lo, "ok": result.ok,
                              "stored": result.stored}
                for result in validation.word_sums
            },
        }

    def fwin(validation):
        header = validation.layout.fwin
        return {"crc_gate": header.crc_gate, "entry_ptr": header.entry_ptr,
                "flash_off": header.flash_off, "magic": header.magic,
                "version": header.version}

    return {
        "compare_range": {"hi": comparison.range.hi, "lo": comparison.range.lo,
                          "length": comparison.range.length},
        "differing_bytes": comparison.differing_bytes,
        "differing_ranges": span_list(comparison.differing_ranges),
        "differing_range_count": len(comparison.differing_ranges),
        "equal": comparison.equal,
        "fwin": {"installed": fwin(comparison.installed_validation),
                 "vendor": fwin(comparison.vendor_validation)},
        "images": {
            "installed": {
                "base": comparison.installed_validation.layout.base,
                "range_sha256": comparison.installed_range_sha256,
                "sha256": comparison.installed_sha256,
                "size": comparison.installed_validation.layout.size,
                "source": (None if comparison.installed_source is None
                           else comparison.installed_source.name),
            },
            "vendor": {
                "base": comparison.vendor_validation.layout.base,
                "range_sha256": comparison.vendor_range_sha256,
                "sha256": comparison.vendor_sha256,
                "size": comparison.vendor_validation.layout.size,
                "source": (None if comparison.vendor_source is None
                           else comparison.vendor_source.name),
            },
        },
        "mirror": {
            "installed_mirror_sha256": comparison.mirror.installed_mirror_sha256,
            "installed_vs_vendor_mirror": span_list(
                comparison.mirror.installed_vs_vendor_mirror),
            "installed_vs_vendor_primary": span_list(
                comparison.mirror.installed_vs_vendor_primary),
            "mirror_range": {"hi": MIRROR_RANGE[1], "lo": MIRROR_RANGE[0]},
            "vendor_mirror_sha256": comparison.mirror.vendor_mirror_sha256,
            "vendor_primary_range": {"hi": VENDOR_PRIMARY_RANGE[1],
                                     "lo": VENDOR_PRIMARY_RANGE[0]},
            "vendor_primary_sha256": comparison.mirror.vendor_primary_sha256,
        },
        "pages": [
            {
                "changed": page.changed,
                "differing_bytes": page.differing_bytes,
                "hi": page.hi,
                "installed_kind": page.installed_kind,
                "installed_sha256": page.installed_sha256,
                "lo": page.lo,
                "vendor_kind": page.vendor_kind,
                "vendor_sha256": page.vendor_sha256,
            }
            for page in comparison.pages
        ],
        "page_size": PAGE,
        "changed_page_count": len(comparison.changed_pages),
        "changed_pages": [page.lo for page in comparison.changed_pages],
        "provenance": {"analysis_only": bool(analysis_only),
                       "unknown_sources": list(unknown)},
        "records": [
            {
                "addr_changed": record.addr_changed,
                "checksum_changed": record.checksum_changed,
                "differing_bytes": record.differing_bytes,
                "differing_ranges": span_list(record.differing_ranges),
                "dst_changed": record.dst_changed,
                "installed": {
                    "addr": record.installed_addr,
                    "dst": record.installed_dst,
                    "length": record.installed_length,
                    "sha256": record.installed_sha256,
                    "stored_checksum": record.installed_stored_checksum,
                },
                "installed_only": (None if record.installed_only is None
                                   else span_list((record.installed_only,))[0]),
                "length_delta": record.length_delta,
                "overlap": record.overlap,
                "slot": record.slot,
                "vendor": {
                    "addr": record.vendor_addr,
                    "dst": record.vendor_dst,
                    "length": record.vendor_length,
                    "sha256": record.vendor_sha256,
                    "stored_checksum": record.vendor_stored_checksum,
                },
                "vendor_only": (None if record.vendor_only is None
                                else span_list((record.vendor_only,))[0]),
            }
            for record in comparison.records
        ],
        "regions": [
            {
                "changed": run.changed,
                "hi": run.hi,
                "installed_kind": run.installed_kind,
                "lo": run.lo,
                "pages": run.pages,
                "vendor_kind": run.vendor_kind,
            }
            for run in comparison.regions
        ],
        "strings": {
            "added": [value.decode("ascii") for value in comparison.strings.added],
            "changed": [{"installed": added.decode("ascii"),
                         "vendor": gone.decode("ascii")}
                        for gone, added in comparison.strings.changed],
            "count_changed": [
                {"installed_occurrences": left, "value": value.decode("ascii"),
                 "vendor_occurrences": right}
                for value, left, right in comparison.strings.count_changed
            ],
            "distinct_common": comparison.strings.distinct_common,
            "installed_distinct": comparison.strings.installed_distinct,
            "installed_occurrences": comparison.strings.installed_occurrences,
            "match_cutoff": STRING_MATCH_CUTOFF,
            "minimum_length": 6,
            "multisets_equal": comparison.strings.multisets_equal,
            "removed": [value.decode("ascii")
                        for value in comparison.strings.removed],
            "vendor_distinct": comparison.strings.vendor_distinct,
            "vendor_occurrences": comparison.strings.vendor_occurrences,
        },
        "word_sums": {"installed": sums(comparison.installed_validation),
                      "vendor": sums(comparison.vendor_validation)},
    }


def markdown_lines(comparison, max_ranges=25):
    """Human-readable report. Counts are complete; long lists say what they omit."""
    installed = comparison.installed_validation
    vendor = comparison.vendor_validation
    region = comparison.range
    out = [
        "# Installed 1.59 application versus vendor 1.00.58",
        "",
        "Generated by `tool/compare_firmware_images.py`. Offline and read-only; no",
        "device was accessed. A changed byte range is a fact — this report assigns",
        "no meaning to any change.",
        "",
        "## Inputs",
        "",
        "| Image | Base | Size | SHA-256 | Allowlisted source |",
        "|---|---|---|---|---|",
        f"| installed | `0x{installed.layout.base:x}` | `0x{installed.layout.size:x}` | "
        f"`{comparison.installed_sha256}` | "
        f"{comparison.installed_source.name if comparison.installed_source else '**no**'} |",
        f"| vendor | `0x{vendor.layout.base:x}` | `0x{vendor.layout.size:x}` | "
        f"`{comparison.vendor_sha256}` | "
        f"{comparison.vendor_source.name if comparison.vendor_source else '**no**'} |",
        "",
        f"Compared over logical flash `0x{region.lo:x}..0x{region.hi:x}` "
        f"(`0x{region.length:x}` bytes), which is the installed dump's whole extent",
        "translated onto the same logical range of the vendor file. Byte 0 of the",
        "installed dump is never compared with byte 0 of the vendor file.",
        "",
        "## Whole-range result",
        "",
        f"- installed range SHA-256: `{comparison.installed_range_sha256}`",
        f"- vendor range SHA-256: `{comparison.vendor_range_sha256}`",
        f"- ranges equal: **{comparison.equal}**",
        f"- differing bytes: **{comparison.differing_bytes}** of {region.length} "
        f"({100.0 * comparison.differing_bytes / region.length:.2f}%)",
        f"- contiguous differing ranges: **{len(comparison.differing_ranges)}**",
        f"- changed `0x{PAGE:x}` pages: **{len(comparison.changed_pages)}** of "
        f"{len(comparison.pages)}",
        "",
    ]

    shown = comparison.differing_ranges
    note = ""
    if max_ranges and len(shown) > max_ranges:
        shown = tuple(sorted(shown, key=lambda span: (-span.length, span.lo))[:max_ranges])
        shown = tuple(sorted(shown, key=lambda span: span.lo))
        note = (f" Showing the {max_ranges} longest of "
                f"{len(comparison.differing_ranges)}; the complete list is in the JSON output.")
    out += [
        "## Contiguous differing ranges",
        "",
        f"{len(comparison.differing_ranges)} ranges total.{note}",
        "",
        "| logical range | length |",
        "|---|---|",
    ]
    out += [f"| `0x{span.lo:x}..0x{span.hi:x}` | {span.length} |" for span in shown]

    out += [
        "",
        "## Record payloads",
        "",
        "Slots are physical slot indices in the fixed eight-slot table. Where the",
        "lengths differ, differing ranges cover the common prefix only.",
        "",
        "| slot | source addr | addr changed | runtime dst | dst changed | "
        "installed len | vendor len | delta | differing bytes | ranges |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in comparison.records:
        addr = (f"`0x{record.installed_addr:08x}`" if not record.addr_changed
                else f"`0x{record.vendor_addr:08x}` -> `0x{record.installed_addr:08x}`")
        dst = (f"`0x{record.installed_dst:08x}`" if not record.dst_changed
               else f"`0x{record.vendor_dst:08x}` -> `0x{record.installed_dst:08x}`")
        out.append(
            f"| {record.slot} | {addr} | "
            f"{'**yes**' if record.addr_changed else 'no'} | {dst} | "
            f"{'**yes**' if record.dst_changed else 'no'} | "
            f"`0x{record.installed_length:x}` | `0x{record.vendor_length:x}` | "
            f"{record.length_delta:+d} | {record.differing_bytes} | "
            f"{len(record.differing_ranges)} |")
    out.append("")
    for record in comparison.records:
        out += [
            f"- slot {record.slot} installed payload SHA-256: `{record.installed_sha256}`",
            f"- slot {record.slot} vendor payload SHA-256: `{record.vendor_sha256}`",
            f"- slot {record.slot} stored checksums: installed "
            f"`0x{record.installed_stored_checksum:08x}`, vendor "
            f"`0x{record.vendor_stored_checksum:08x}` "
            f"(changed: {record.checksum_changed})",
            f"- slot {record.slot} compared prefix: "
            f"`0x{record.installed_addr - fi.FLASH_BASE:x}.."
            f"0x{record.installed_addr - fi.FLASH_BASE + record.overlap:x}` "
            f"(`0x{record.overlap:x}` bytes)",
        ]
        for label, span in (("installed-only", record.installed_only),
                            ("vendor-only", record.vendor_only)):
            if span is not None:
                out.append(
                    f"- slot {record.slot} {label} tail: "
                    f"`0x{span.lo:x}..0x{span.hi:x}` (`0x{span.length:x}` bytes, "
                    f"{span.length} decimal) — present in one image only, so it "
                    f"has no counterpart to differ from")

    out += [
        "",
        "## Word sums",
        "",
        "| region | installed stored | installed computed | vendor stored | vendor computed |",
        "|---|---|---|---|---|",
    ]
    installed_sums = word_sums(installed)
    vendor_sums = word_sums(vendor)
    for name in sorted(set(installed_sums) | set(vendor_sums)):
        left = installed_sums.get(name)
        right = vendor_sums.get(name)
        out.append(
            f"| `{name}` | "
            + (f"`0x{left[0]:08x}` | `0x{left[1]:08x}` | " if left else "absent | absent | ")
            + (f"`0x{right[0]:08x}` | `0x{right[1]:08x}` |" if right else "absent | absent |"))
    if installed.skipped_word_sums:
        out += ["", "Skipped in the installed dump (region absent): "
                + ", ".join(f"`{name}`" for name in installed.skipped_word_sums) + "."]

    mirror = comparison.mirror
    out += [
        "",
        "## Bootloader copy, three-way",
        "",
        f"Installed logical `0x{MIRROR_RANGE[0]:x}..0x{MIRROR_RANGE[1]:x}` against the",
        "same vendor range and against the vendor primary bootloader region",
        f"`0x{VENDOR_PRIMARY_RANGE[0]:x}..0x{VENDOR_PRIMARY_RANGE[1]:x}`.",
        "",
        f"- installed mirror SHA-256: `{mirror.installed_mirror_sha256}`",
        f"- vendor mirror SHA-256: `{mirror.vendor_mirror_sha256}`",
        f"- vendor primary SHA-256: `{mirror.vendor_primary_sha256}`",
        f"- installed mirror vs vendor mirror: "
        f"{len(mirror.installed_vs_vendor_mirror)} differing ranges",
        f"- installed mirror vs vendor primary: "
        f"{len(mirror.installed_vs_vendor_primary)} differing ranges",
        "",
        "This shows the bootloader bytes under static analysis are present on the",
        "device as the mirrored copy. It says nothing about the unread installed",
        "primary region, which container the device booted, or ROM behaviour.",
        "",
        "## Region map",
        "",
        f"Consecutive `0x{PAGE:x}` pages collapsed by change state and fill.",
        "",
        "| logical range | pages | changed | installed | vendor |",
        "|---|---|---|---|---|",
    ]
    for run in comparison.regions:
        out.append(
            f"| `0x{run.lo:x}..0x{run.hi:x}` | {run.pages} | "
            f"{'yes' if run.changed else 'no'} | {run.installed_kind} | "
            f"{run.vendor_kind} |")

    out += [
        "",
        "## Changed pages",
        "",
        ", ".join(f"`0x{page.lo:x}`" for page in comparison.changed_pages) or "none",
        "",
        "## Strings",
        "",
        f"ASCII runs of at least 6 printable bytes. Substrings of a longer hit are",
        f"dropped. A removed string paired with an addition at difflib ratio "
        f">= {STRING_MATCH_CUTOFF} is reported once as changed.",
        "",
        f"- installed: {comparison.strings.installed_distinct} distinct values in "
        f"{comparison.strings.installed_occurrences} occurrences",
        f"- vendor: {comparison.strings.vendor_distinct} distinct values in "
        f"{comparison.strings.vendor_occurrences} occurrences",
        f"- distinct values present in both: {comparison.strings.distinct_common}",
        f"- multisets equal (same values, same occurrence counts): "
        f"**{comparison.strings.multisets_equal}**",
        f"- added: {len(comparison.strings.added)}",
        f"- removed: {len(comparison.strings.removed)}",
        f"- changed: {len(comparison.strings.changed)}",
        f"- occurrence count changed: {len(comparison.strings.count_changed)}",
        "",
        "Occurrence counts are compared, not just the set of values, so a string "
        "appearing a different number of times cannot hide. Offsets are not "
        "compared here — the byte-range diff above already carries position, and "
        "an identical multiset does not mean identical placement.",
        "",
    ]
    if comparison.strings.count_changed:
        out += ["| value | vendor occurrences | installed occurrences |",
                "|---|---|---|"]
        out += [f"| `{value.decode('ascii')}` | {right} | {left} |"
                for value, left, right in comparison.strings.count_changed]
        out.append("")
    if comparison.strings.changed:
        out += ["| vendor | installed |", "|---|---|"]
        out += [f"| `{old.decode('ascii')}` | `{new.decode('ascii')}` |"
                for old, new in comparison.strings.changed]
        out.append("")
    for label, values in (("Added", comparison.strings.added),
                          ("Removed", comparison.strings.removed)):
        out.append(f"{label}:")
        out.append("")
        out += ([f"- `{value.decode('ascii')}`" for value in values] or ["- none"])
        out.append("")

    out += [
        "## Not concluded here",
        "",
        "- No meaning is assigned to any changed range; that is Phase 3 onward.",
        "- Both images pass their own known structural checks; that is not a claim",
        "  that either boots after modification.",
    ]
    for line in fi.UNRESOLVED:
        out.append(f"- Still unresolved: {line}")
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", type=Path, default=DEFAULT_INSTALLED)
    parser.add_argument("--installed-base", type=lambda value: int(value, 0),
                        default=0x10000)
    parser.add_argument("--vendor", type=Path, default=DEFAULT_VENDOR)
    parser.add_argument("--vendor-base", type=lambda value: int(value, 0),
                        default=0x0)
    parser.add_argument("--json", action="store_true",
                        help="emit the complete deterministic JSON result")
    parser.add_argument(
        "--max-ranges", type=int, default=25,
        help="longest differing ranges to table in the Markdown report; 0 for all")
    parser.add_argument(
        "--analysis-only", action="store_true",
        help="permit inputs that are not allowlisted sources (prints a warning)")
    return parser.parse_args(argv)


def unknown_sources(installed, vendor):
    """Names of the inputs whose SHA-256/base/size tuple is not allowlisted."""
    return tuple(name for name, view in (("installed", installed),
                                         ("vendor", vendor))
                 if fi.find_source(view) is None)


def check_sources(installed, vendor, analysis_only, out, err):
    """Gate on provenance *before* any parsing, hashing or diffing happens.

    Returns the unknown-source names when the run may proceed, or None to refuse.
    The warning goes to stderr so `--analysis-only --json` still emits a single
    parseable document on stdout; it is also recorded inside the JSON.
    """
    unknown = unknown_sources(installed, vendor)
    if not unknown:
        return unknown
    if not analysis_only:
        print("RESULT compared=False error=unknown source image(s): "
              + ", ".join(unknown)
              + "; expected an allowlisted SHA-256/base/size tuple. Re-run with "
                "--analysis-only to compare anyway.", file=out)
        return None
    print("WARNING " + ", ".join(unknown) + " is not an allowlisted source image. "
          "Every conclusion below describes bytes of unverified provenance and "
          "must not be cited as evidence about the shipped firmware.", file=err)
    return unknown


def main(argv=None):
    args = parse_args(argv)
    try:
        installed = fi.ImageView(args.installed.read_bytes(), args.installed_base)
        vendor = fi.ImageView(args.vendor.read_bytes(), args.vendor_base)
    except fi.ImageFormatError as exc:
        print(f"RESULT compared=False error={exc}")
        return 1

    # Provenance first: nothing is parsed, hashed or diffed until the two
    # SHA-256/base/size tuples are either allowlisted or explicitly waived.
    unknown = check_sources(installed, vendor, args.analysis_only,
                            sys.stdout, sys.stderr)
    if unknown is None:
        return 1

    try:
        comparison = compare(installed, vendor)
    except (fi.ImageFormatError, ComparisonError) as exc:
        # Fail closed: one line, no traceback, no partial report.
        print(f"RESULT compared=False error={exc}")
        return 1

    if args.json:
        print(json.dumps(to_dict(comparison, args.analysis_only, unknown),
                         indent=2, sort_keys=True))
    else:
        print("\n".join(markdown_lines(comparison, args.max_ranges)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
