#!/usr/bin/env python3
"""Match functions between two releases of the same Falchion program.

Consumes two `FalchionFunctionInventory.java` outputs and pairs functions using
several independent signals, never an address alone:

  identical   same body bytes; the entry address may or may not agree
  structural  same instruction shape — mnemonics and operand kinds with every
              scalar and address masked — and that shape is unique on both sides
  tentative   no shape match, but size, instruction and block counts, constants,
              strings and call-degree agree closely enough, and the best
              candidate is clearly ahead of the runner-up
  unmatched   nothing left that clears the bar

An address is never the *sole* signal. The identical and structural tiers use no
address at all; one tentative rule combines body-byte equality with the shift
measured from those tiers, and can never promote a pairing above tentative. So no
vendor symbol is transferred to the installed image on an address alone.

Ghidra function bodies are not necessarily contiguous, and many here are not, so
every byte-level operation uses the real ordered body ranges rather than
`entry..entry+size`.

No device access. Example:
    python3 tool/match_functions.py --program app_a \\
        --vendor-inventory ghidra/inventories/vendor_a.txt \\
        --installed-inventory ghidra/inventories/installed_a.txt
"""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Optional

import falchion_image as fi

ROOT = Path(__file__).resolve().parent.parent

# A tentative match needs both a high score and a clear lead over the next best.
TENTATIVE_FLOOR = 0.85
TENTATIVE_MARGIN = 0.05

FIELD_RE = re.compile(r"(\w+)=(.*?)(?=\s+\w+=|$)")


@dataclass(frozen=True)
class FunctionRecord:
    """One function, with the *real* ordered body ranges Ghidra reported.

    A Ghidra function body is not necessarily contiguous, and many here are not,
    so `entry..entry+size` is not the body. Everything that touches bytes uses
    `ranges`.
    """
    entry: int
    name: str
    size: int
    ranges: tuple
    insns: int
    blocks: int
    bytes_sha: str
    shape_sha: str
    callers: int
    callees: tuple
    consts: frozenset
    strings: frozenset

    @property
    def contiguous(self):
        return len(self.ranges) == 1

    @property
    def extent(self):
        """Lowest and highest address the body touches, holes included."""
        return self.ranges[0][0], self.ranges[-1][1]

    def body_bytes(self, data, base):
        """Concatenate the real ranges, or None if any lies outside the image."""
        out = bytearray()
        for lo, hi in self.ranges:
            start, stop = lo - base, hi - base
            if start < 0 or stop > len(data):
                return None
            out += data[start:stop]
        return bytes(out)


@dataclass(frozen=True)
class Match:
    vendor: Optional[FunctionRecord]
    installed: Optional[FunctionRecord]
    confidence: str
    score: float
    reason: str
    differing_bytes: Optional[int]

    @property
    def moved(self):
        return (self.vendor is not None and self.installed is not None
                and self.vendor.entry != self.installed.entry)

    @property
    def changed(self):
        if self.vendor is None or self.installed is None:
            return True
        return self.vendor.bytes_sha != self.installed.bytes_sha


@dataclass(frozen=True)
class DataRegion:
    """A changed byte range in a gap between matched functions.

    Gaps are aligned by the matched functions that bracket them, never by raw
    file offset: an insertion earlier in the image shifts everything after it,
    and comparing shifted bytes at equal offsets manufactures differences that
    are not there.
    """
    vendor_lo: int
    vendor_hi: int
    installed_lo: int
    installed_hi: int
    flash_lo: int
    flash_hi: int

    @property
    def length(self):
        return self.vendor_hi - self.vendor_lo

    @property
    def shift(self):
        return self.installed_lo - self.vendor_lo


@dataclass(frozen=True)
class UnalignedGap:
    """A gap whose two sides differ in length, so it cannot be compared."""
    vendor_lo: int
    vendor_hi: int
    installed_lo: int
    installed_hi: int

    @property
    def vendor_length(self):
        return self.vendor_hi - self.vendor_lo

    @property
    def installed_length(self):
        return self.installed_hi - self.installed_lo


@dataclass(frozen=True)
class MatchReport:
    program: str
    vendor_count: int
    installed_count: int
    matches: tuple
    data_regions: tuple
    unaligned_gaps: tuple
    dominant_shift: Optional[int]
    span_counts: Optional[tuple]
    discontiguous: tuple
    header: dict

    @property
    def span_counts_equal(self):
        """Only that the two sides produced the same number of spans.

        This is deliberately *not* called "aligned": equal counts say nothing
        about whether the spans correspond. Use `spans_fully_compared` for that.
        """
        return (self.span_counts is not None
                and self.span_counts[0] == self.span_counts[1])

    @property
    def spans_compared(self):
        return None if self.span_counts is None else self.span_counts[2]

    @property
    def spans_fully_compared(self):
        """True only when every span on both sides was safely paired."""
        if self.span_counts is None:
            return False
        return (self.span_counts[0] == self.span_counts[1] == self.span_counts[2]
                and not self.unaligned_gaps)


def parse_inventory(text):
    """Parse FalchionFunctionInventory output into records plus its header."""
    header = {}
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("FUNC "):
            fields = dict(FIELD_RE.findall(line[len("FUNC "):]))
            if "ranges" not in fields:
                raise ValueError(
                    "inventory predates real body ranges; regenerate it with "
                    "FalchionFunctionInventory.java")
            ranges = tuple(
                (int(part.split("-")[0], 16), int(part.split("-")[1], 16))
                for part in fields["ranges"].split(";") if part)
            if not ranges:
                raise ValueError(
                    f"function at {fields['entry']} has no body ranges")
            size = int(fields["size"], 16)
            if sum(hi - lo for lo, hi in ranges) != size:
                raise ValueError(
                    f"function at {fields['entry']}: body ranges sum to "
                    f"{sum(hi - lo for lo, hi in ranges)} but size is {size}")
            records.append(FunctionRecord(
                entry=int(fields["entry"], 16),
                name=fields["name"],
                size=size,
                ranges=ranges,
                insns=int(fields["insns"]),
                blocks=int(fields["blocks"]),
                bytes_sha=fields["bytes_sha"],
                shape_sha=fields["shape_sha"],
                callers=int(fields["callers"]),
                callees=tuple(sorted(
                    int(value, 16) for value in fields["callees"].split(",")
                    if value)),
                consts=frozenset(
                    int(value, 16) for value in fields["consts"].split(",")
                    if value),
                strings=frozenset(
                    value for value in fields["strings"].split(",") if value)))
        elif " " in line:
            key, value = line.split(" ", 1)
            header.setdefault(key.lower(), value)
    if not records:
        raise ValueError("inventory contains no FUNC lines")
    return tuple(sorted(records, key=lambda item: item.entry)), header


def jaccard(left, right):
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def ratio(left, right):
    if left == right:
        return 1.0
    high = max(left, right)
    return min(left, right) / high if high else 1.0


def similarity(left, right):
    """Mean of seven independent, order-free signals."""
    parts = (
        ratio(left.size, right.size),
        ratio(left.insns, right.insns),
        ratio(left.blocks, right.blocks),
        jaccard(left.consts, right.consts),
        jaccard(left.strings, right.strings),
        ratio(len(left.callees), len(right.callees)),
        ratio(left.callers, right.callers),
    )
    return sum(parts) / len(parts)


def dominant_shift(pairs):
    """Most common entry-address delta across unambiguous matches, or None.

    Measured from tier-1 and tier-2 pairings only, so it is derived from
    byte/shape evidence rather than assumed from the layout.
    """
    counts = {}
    for left, right, confidence, _score, _reason in pairs:
        if left is None or right is None:
            continue
        if confidence not in ("identical", "structural"):
            continue
        delta = right.entry - left.entry
        counts[delta] = counts.get(delta, 0) + 1
    if not counts:
        return None
    best = max(sorted(counts), key=lambda delta: (counts[delta], -abs(delta)))
    return best if counts[best] > 1 else None


def unique_by(records, attribute):
    seen = {}
    for record in records:
        seen.setdefault(getattr(record, attribute), []).append(record)
    return {key: group[0] for key, group in seen.items() if len(group) == 1}


def match_functions(vendor, installed):
    """Pair the two inventories, strongest evidence first."""
    matches = []
    used_vendor, used_installed = set(), set()

    def take(left, right, confidence, score, reason):
        used_vendor.add(left.entry)
        used_installed.add(right.entry)
        matches.append((left, right, confidence, score, reason))

    # Tier 1: identical body bytes, unique on both sides.
    vendor_bytes = unique_by(vendor, "bytes_sha")
    installed_bytes = unique_by(installed, "bytes_sha")
    for digest, left in sorted(vendor_bytes.items()):
        right = installed_bytes.get(digest)
        if right is None or left.entry in used_vendor or right.entry in used_installed:
            continue
        take(left, right, "identical", 1.0,
             "same body bytes"
             + ("" if left.entry == right.entry else ", relocated"))

    # Tier 2: identical instruction shape, unique on both sides.
    remaining_vendor = [f for f in vendor if f.entry not in used_vendor]
    remaining_installed = [f for f in installed if f.entry not in used_installed]
    vendor_shape = unique_by(remaining_vendor, "shape_sha")
    installed_shape = unique_by(remaining_installed, "shape_sha")
    for digest, left in sorted(vendor_shape.items()):
        right = installed_shape.get(digest)
        if right is None or left.entry in used_vendor or right.entry in used_installed:
            continue
        take(left, right, "structural", 0.99,
             "same instruction shape with scalars and addresses masked"
             + ("" if left.entry == right.entry else ", relocated"))

    # Tier 3a: ambiguous duplicates whose bodies are byte-identical *and* whose
    # offset delta equals the shift measured from the unambiguous matches above.
    # Two independent signals, so this is not matching by address; it still only
    # earns "tentative", because a duplicate body cannot single out one caller.
    shift = dominant_shift(matches)
    if shift is not None:
        remaining_vendor = [f for f in vendor if f.entry not in used_vendor]
        remaining_installed = {f.entry: f for f in installed
                               if f.entry not in used_installed}
        for left in remaining_vendor:
            right = remaining_installed.get(left.entry + shift)
            if right is None or right.entry in used_installed:
                continue
            if right.bytes_sha != left.bytes_sha:
                continue
            take(left, right, "tentative", 0.95,
                 f"byte-identical and consistent with the +0x{shift:x} shift "
                 f"measured from the unambiguous matches, but the body hash is "
                 f"not unique so the pairing is a lead, not a proof")

    # Tier 3b: scored, with a uniqueness margin so a near-tie stays unmatched.
    remaining_vendor = [f for f in vendor if f.entry not in used_vendor]
    remaining_installed = [f for f in installed if f.entry not in used_installed]
    scored = []
    for left in remaining_vendor:
        ranked = sorted(
            ((similarity(left, right), right.entry, right)
             for right in remaining_installed),
            key=lambda item: (-item[0], item[1]))
        if not ranked:
            continue
        best_score, _entry, best = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        scored.append((best_score, best_score - runner_up, left, best))
    for best_score, margin, left, right in sorted(
            scored, key=lambda item: (-item[0], item[2].entry)):
        if left.entry in used_vendor or right.entry in used_installed:
            continue
        if best_score < TENTATIVE_FLOOR or margin < TENTATIVE_MARGIN:
            continue
        same_bytes = ("; bodies are byte-identical but that hash is not unique "
                      "on both sides, so the pairing is still only a lead"
                      if left.bytes_sha == right.bytes_sha else "")
        take(left, right, "tentative", best_score,
             f"scored {best_score:.3f} with a {margin:.3f} lead over the "
             f"next candidate{same_bytes}")

    for left in vendor:
        if left.entry not in used_vendor:
            matches.append((left, None, "unmatched", 0.0,
                            "no installed candidate cleared the bar"))
    for right in installed:
        if right.entry not in used_installed:
            matches.append((None, right, "unmatched", 0.0,
                            "no vendor candidate cleared the bar"))
    return matches


def body_diff(vendor_bytes, installed_bytes, base, left, right):
    """Differing byte count across the real body ranges, or None if not comparable.

    Requires the two bodies to have the same range *shape* — the same number of
    ranges with the same lengths — so bytes are never lined up across a hole.
    """
    if left is None or right is None or left.size != right.size:
        return None
    if vendor_bytes is None or installed_bytes is None:
        return None
    if [hi - lo for lo, hi in left.ranges] != [hi - lo for lo, hi in right.ranges]:
        return None
    first = left.body_bytes(vendor_bytes, base)
    second = right.body_bytes(installed_bytes, base)
    if first is None or second is None:
        return None
    return sum(1 for a, b in zip(first, second) if a != b)


def uncovered_spans(base, length, records):
    """Maximal spans of the image that no function body range covers."""
    covered = sorted((lo, hi) for record in records for lo, hi in record.ranges)
    merged = []
    for lo, hi in covered:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    spans = []
    cursor = base
    for lo, hi in merged:
        if lo > cursor:
            spans.append((cursor, min(lo, base + length)))
        cursor = max(cursor, hi)
        if cursor >= base + length:
            break
    if cursor < base + length:
        spans.append((cursor, base + length))
    return tuple(span for span in spans if span[1] > span[0])


def anchor_keys(spans, anchors):
    """Key each uncovered span by the matched function that precedes it.

    Pairing spans by list index looks safe when both sides produce the same
    number of spans, but it drifts as soon as one side gains or loses a span in
    the middle — the counts still agree while the k-th spans describe different
    regions. Keying by the preceding matched function makes the pairing
    referential instead of positional.

    The key alone is not trusted: the caller additionally requires the span to
    sit at the same distance past its anchor and to have the same length on both
    sides, so a mispaired span is skipped rather than compared. Returns
    key -> (lo, hi, distance_past_anchor).

    `anchors` is a list of (end_address, identity) for matched functions, using
    an identity that means the same thing in both images.
    """
    ordered = sorted(anchors)
    keyed = {}
    counts = {}
    for lo, hi in spans:
        identity = None
        anchor_end = None
        for end, candidate in ordered:
            if end <= lo:
                identity, anchor_end = candidate, end
            else:
                break
        ordinal = counts.get(identity, 0)
        counts[identity] = ordinal + 1
        distance = lo if anchor_end is None else lo - anchor_end
        keyed[(identity, ordinal)] = (lo, hi, distance)
    return keyed


def changed_data_regions(vendor_bytes, installed_bytes, base, flash_base,
                         vendor_records, installed_records, matches):
    """Compare the spans no real body range covers, paired by their anchors.

    Gaps come from the complement of the union of the *real* body ranges, so a
    discontiguous body's holes count as data rather than code. Each span is then
    keyed by the matched function that precedes it, and only spans sharing a key
    are compared. A key present on one side only, or a paired span whose two
    sides differ in length, is reported rather than compared, so nothing is
    diffed across an insertion boundary or against the wrong region.
    """
    if vendor_bytes is None or installed_bytes is None:
        return (), (), None
    left_spans = uncovered_spans(base, len(vendor_bytes), vendor_records)
    right_spans = uncovered_spans(base, len(installed_bytes), installed_records)
    counts = (len(left_spans), len(right_spans))

    vendor_anchors, installed_anchors = [], []
    for match in matches:
        if match.vendor is None or match.installed is None:
            continue
        identity = match.vendor.entry
        vendor_anchors.append((match.vendor.extent[1], identity))
        installed_anchors.append((match.installed.extent[1], identity))
    left_keyed = anchor_keys(left_spans, vendor_anchors)
    right_keyed = anchor_keys(right_spans, installed_anchors)

    regions, unaligned = [], []
    compared = 0
    for key in sorted(set(left_keyed) | set(right_keyed),
                      key=lambda item: (item[0] is None, item)):
        left = left_keyed.get(key)
        right = right_keyed.get(key)
        if left is None or right is None:
            lo, hi, _distance = left or right
            unaligned.append(UnalignedGap(lo, hi, lo, hi) if left is not None
                             else UnalignedGap(lo, lo, lo, hi))
            continue
        vendor_lo, vendor_hi, vendor_distance = left
        installed_lo, installed_hi, installed_distance = right
        if (vendor_hi - vendor_lo != installed_hi - installed_lo
                or vendor_distance != installed_distance):
            unaligned.append(UnalignedGap(vendor_lo, vendor_hi,
                                          installed_lo, installed_hi))
            continue
        compared += 1
        first = vendor_bytes[vendor_lo - base:vendor_hi - base]
        second = installed_bytes[installed_lo - base:installed_hi - base]
        start = None
        for index in range(len(first)):
            if first[index] != second[index]:
                if start is None:
                    start = index
            elif start is not None:
                regions.append(DataRegion(
                    vendor_lo + start, vendor_lo + index,
                    installed_lo + start, installed_lo + index,
                    flash_base + (vendor_lo - base) + start,
                    flash_base + (vendor_lo - base) + index))
                start = None
        if start is not None:
            regions.append(DataRegion(
                vendor_lo + start, vendor_hi,
                installed_lo + start, installed_hi,
                flash_base + (vendor_lo - base) + start,
                flash_base + (vendor_hi - base)))
    regions.sort(key=lambda item: item.vendor_lo)
    unaligned.sort(key=lambda item: item.vendor_lo)
    return tuple(regions), tuple(unaligned), (counts[0], counts[1], compared)


def build_report(program, vendor_text, installed_text, base, flash_base,
                 vendor_bytes=None, installed_bytes=None):
    vendor, vendor_header = parse_inventory(vendor_text)
    installed, installed_header = parse_inventory(installed_text)
    raw = match_functions(vendor, installed)
    matches = tuple(
        Match(vendor=left, installed=right, confidence=confidence, score=score,
              reason=reason,
              differing_bytes=body_diff(vendor_bytes, installed_bytes, base,
                                        left, right))
        for left, right, confidence, score, reason in raw)
    regions, unaligned, span_counts = changed_data_regions(
        vendor_bytes, installed_bytes, base, flash_base, vendor, installed,
        matches)
    return MatchReport(
        program=program, vendor_count=len(vendor), installed_count=len(installed),
        matches=matches, data_regions=regions, unaligned_gaps=unaligned,
        dominant_shift=dominant_shift(raw),
        span_counts=span_counts,
        discontiguous=(sum(1 for f in vendor if not f.contiguous),
                       sum(1 for f in installed if not f.contiguous)),
        header={"base": base, "flash_base": flash_base,
                "vendor_program": vendor_header.get("program", ""),
                "installed_program": installed_header.get("program", "")})


def tally(report):
    counts = {}
    for match in report.matches:
        counts[match.confidence] = counts.get(match.confidence, 0) + 1
    return counts


def review_ranking(report):
    """Changed functions, most in need of manual review first."""
    ranked = [match for match in report.matches if match.changed]

    def key(match):
        size = (match.installed or match.vendor).size
        differing = match.differing_bytes
        tier = {"unmatched": 0, "tentative": 1, "structural": 2,
                "identical": 3}[match.confidence]
        return (tier, -(differing if differing is not None else size),
                -(size), (match.vendor or match.installed).entry)

    return tuple(sorted(ranked, key=key))


def must_not_assume_equal(report):
    """Addresses whose vendor meaning may no longer carry to the installed image."""
    out = []
    for match in report.matches:
        if match.moved:
            out.append((match.vendor.entry, match.installed.entry,
                        f"{match.confidence} match, relocated"))
        elif match.confidence == "unmatched" and match.vendor is not None:
            out.append((match.vendor.entry, None,
                        "vendor function with no installed counterpart"))
        elif match.confidence == "tentative":
            out.append((match.vendor.entry, match.installed.entry,
                        "tentative match only; the correspondence is not proven"))
    return tuple(sorted(out, key=lambda item: item[0]))


def to_dict(report):
    return {
        "counts": tally(report),
        "data_regions": [
            {"flash_hi": region.flash_hi, "flash_lo": region.flash_lo,
             "installed_hi": region.installed_hi,
             "installed_lo": region.installed_lo, "length": region.length,
             "shift": region.shift, "vendor_hi": region.vendor_hi,
             "vendor_lo": region.vendor_lo}
            for region in report.data_regions
        ],
        "data_region_bytes": sum(region.length for region in report.data_regions),
        "discontiguous_bodies": {"installed": report.discontiguous[1],
                                 "vendor": report.discontiguous[0]},
        "dominant_shift": report.dominant_shift,
        "uncovered_span_counts": (None if report.span_counts is None else
                                  {"compared": report.span_counts[2],
                                   "installed": report.span_counts[1],
                                   "vendor": report.span_counts[0]}),
        "uncovered_span_counts_equal": report.span_counts_equal,
        "uncovered_spans_fully_compared": report.spans_fully_compared,
        "unaligned_gaps": [
            {"installed_hi": gap.installed_hi, "installed_length": gap.installed_length,
             "installed_lo": gap.installed_lo, "vendor_hi": gap.vendor_hi,
             "vendor_length": gap.vendor_length, "vendor_lo": gap.vendor_lo}
            for gap in report.unaligned_gaps
        ],
        "header": report.header,
        "installed_count": report.installed_count,
        "matches": [
            {
                "confidence": match.confidence,
                "differing_bytes": match.differing_bytes,
                "installed": None if match.installed is None else {
                    "blocks": match.installed.blocks,
                    "bytes_sha": match.installed.bytes_sha,
                    "entry": match.installed.entry,
                    "insns": match.installed.insns,
                    "name": match.installed.name,
                    "shape_sha": match.installed.shape_sha,
                    "size": match.installed.size,
                },
                "moved": match.moved,
                "reason": match.reason,
                "score": round(match.score, 6),
                "vendor": None if match.vendor is None else {
                    "blocks": match.vendor.blocks,
                    "bytes_sha": match.vendor.bytes_sha,
                    "entry": match.vendor.entry,
                    "insns": match.vendor.insns,
                    "name": match.vendor.name,
                    "shape_sha": match.vendor.shape_sha,
                    "size": match.vendor.size,
                },
            }
            for match in sorted(
                report.matches,
                key=lambda item: ((item.vendor or item.installed).entry,
                                  item.vendor is None))
        ],
        "must_not_assume_equal": [
            {"installed": installed, "reason": reason, "vendor": vendor}
            for vendor, installed, reason in must_not_assume_equal(report)
        ],
        "program": report.program,
        "review_ranking": [
            {"confidence": match.confidence,
             "differing_bytes": match.differing_bytes,
             "installed_entry": None if match.installed is None else match.installed.entry,
             "vendor_entry": None if match.vendor is None else match.vendor.entry}
            for match in review_ranking(report)
        ],
        "vendor_count": report.vendor_count,
    }


def report_lines(report, top=25):
    counts = tally(report)
    out = [
        "PROGRAM match_functions",
        f"PAIR {report.program}",
        f"VENDOR_PROGRAM {report.header['vendor_program']}",
        f"INSTALLED_PROGRAM {report.header['installed_program']}",
        f"BASE 0x{report.header['base']:08x} "
        f"FLASH_BASE 0x{report.header['flash_base']:x}",
        f"COUNTS vendor={report.vendor_count} installed={report.installed_count}",
        "TIERS " + " ".join(f"{name}={counts.get(name, 0)}" for name in
                            ("identical", "structural", "tentative", "unmatched")),
    ]
    changed = [match for match in report.matches if match.changed]
    out.append(f"CHANGED {len(changed)} of {len(report.matches)} pairings")
    out.append(f"MOVED {sum(1 for match in report.matches if match.moved)}")
    out.append(f"DATA_REGIONS {len(report.data_regions)} "
               f"bytes={sum(region.length for region in report.data_regions)} "
               f"unaligned_gaps={len(report.unaligned_gaps)}")
    out.append(f"DISCONTIGUOUS_BODIES vendor={report.discontiguous[0]} "
               f"installed={report.discontiguous[1]} of "
               f"{report.vendor_count}/{report.installed_count} — body bytes and "
               f"gaps come from the real ranges, not entry..entry+size")
    if report.span_counts is None:
        out.append("UNCOVERED_SPANS not computed (no image bytes supplied)")
    else:
        out.append(f"UNCOVERED_SPANS vendor={report.span_counts[0]} "
                   f"installed={report.span_counts[1]} "
                   f"compared={report.spans_compared} "
                   f"unpaired_or_mismatched={len(report.unaligned_gaps)} "
                   f"fully_compared={report.spans_fully_compared} "
                   "— a span is compared only when its anchor key, its distance "
                   "past that anchor and its length all agree on both sides. "
                   "Equal counts alone would prove nothing, so they are not "
                   "reported as alignment.")
    out.append("DOMINANT_SHIFT " + (
        "none" if report.dominant_shift is None
        else f"0x{report.dominant_shift:x} ({report.dominant_shift:+d} bytes), "
             "measured from the identical and structural matches only"))

    ranked = review_ranking(report)
    shown = ranked[:top] if top else ranked
    out.append(f"REVIEW_RANKING showing {len(shown)} of {len(ranked)}")
    for match in shown:
        vendor = "-" if match.vendor is None else f"0x{match.vendor.entry:08x}"
        installed = ("-" if match.installed is None
                     else f"0x{match.installed.entry:08x}")
        size = (match.installed or match.vendor).size
        differing = ("n/a" if match.differing_bytes is None
                     else str(match.differing_bytes))
        out.append(f"  {match.confidence:<10} vendor={vendor} "
                   f"installed={installed} size=0x{size:x} "
                   f"differing_bytes={differing} :: {match.reason}")

    data_shown = report.data_regions[:top] if top else report.data_regions
    out.append(f"DATA_RANGES showing {len(data_shown)} of "
               f"{len(report.data_regions)}; the complete list is in the JSON")
    for region in data_shown:
        out.append(f"DATA vendor 0x{region.vendor_lo:08x}..0x{region.vendor_hi:08x}"
                   f" installed 0x{region.installed_lo:08x}.."
                   f"0x{region.installed_hi:08x} "
                   f"(vendor flash 0x{region.flash_lo:x}..0x{region.flash_hi:x}) "
                   f"length={region.length} shift=0x{region.shift:x}")
    for gap in report.unaligned_gaps:
        out.append(f"UNALIGNED_GAP vendor 0x{gap.vendor_lo:08x}.."
                   f"0x{gap.vendor_hi:08x} (0x{gap.vendor_length:x}) vs "
                   f"installed 0x{gap.installed_lo:08x}..0x{gap.installed_hi:08x} "
                   f"(0x{gap.installed_length:x}) — lengths differ, not compared")

    unequal = must_not_assume_equal(report)
    out.append(f"MUST_NOT_ASSUME_EQUAL {len(unequal)}")
    for vendor, installed, reason in unequal:
        target = "absent" if installed is None else f"0x{installed:08x}"
        out.append(f"  vendor 0x{vendor:08x} -> {target}: {reason}")

    out.append("RESULT matched="
               f"{len(report.matches) - counts.get('unmatched', 0)} "
               f"unmatched={counts.get('unmatched', 0)}")
    out.append("LIMITATION Data regions are the spans no real body range covers, "
               "keyed by the matched function that precedes each span rather "
               "than by list index, so the pairing survives one side gaining or "
               "losing a span. A span with no counterpart key, or a paired span "
               "whose sides differ in length, is reported as unaligned and not "
               "compared, so bytes are never diffed across an insertion "
               "boundary or against the wrong region.")
    out.append("LIMITATION Confidence tiers describe evidence strength, not "
               "correctness. A tentative pairing is a lead for manual review, "
               "not an established correspondence.")
    out.append("LIMITATION An address or a measured shift is never the sole "
               "signal for a pairing. The identical and structural tiers use no "
               "address at all. One tentative rule does use the measured shift, "
               "but only together with body-byte equality, and it can never "
               "raise a pairing above tentative.")
    for line in fi.UNRESOLVED:
        out.append(f"UNRESOLVED {line}")
    return out


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--program", required=True)
    parser.add_argument("--vendor-inventory", required=True, type=Path)
    parser.add_argument("--installed-inventory", required=True, type=Path)
    parser.add_argument("--vendor-bin", type=Path)
    parser.add_argument("--installed-bin", type=Path)
    parser.add_argument("--base", type=lambda value: int(value, 0), default=0)
    parser.add_argument("--flash-base", type=lambda value: int(value, 0),
                        default=0)
    parser.add_argument("--top", type=int, default=25,
                        help="review-ranking rows to print; 0 for all")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        report = build_report(
            args.program,
            args.vendor_inventory.read_text(),
            args.installed_inventory.read_text(),
            args.base, args.flash_base,
            args.vendor_bin.read_bytes() if args.vendor_bin else None,
            args.installed_bin.read_bytes() if args.installed_bin else None)
    except (OSError, ValueError) as exc:
        print(f"RESULT matched=0 error={exc}")
        return 1
    if args.json:
        print(json.dumps(to_dict(report), indent=2, sort_keys=True))
    else:
        print("\n".join(report_lines(report, args.top)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
