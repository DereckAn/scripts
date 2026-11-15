"""How well does the app read a sheet? Compare it with an exact reference MIDI.

Run: .venv/bin/python accuracy.py SHEET.pdf REFERENCE.mid
     (a reference engraved from the same piece, e.g. Mutopia's MIDI; any edition of the sheet)

The sheet goes through the same path as "Play in Practice Studio" (Audiveris, then the
app's MusicXML fixes). Both sides become notes per bar: (position in the bar in quarters,
MIDI pitch, length, staff), with tied notes joined into one held note. Bars are lined up by
content first, so one missing or extra bar doesn't make everything after it count as wrong.
"""
from collections import Counter
from fractions import Fraction
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import mido

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES = "C C# D Eb E F F# G Ab A Bb B".split()
EXACT = 1 / 8  # a note counts as placed right within a 32nd note of the reference position


def reference_bars(midi_path):
    """Reference MIDI -> [[(offset, pitch, length, staff)] per bar]; staff = track order."""
    midi = mido.MidiFile(str(midi_path))
    q = lambda tick: tick / midi.ticks_per_beat
    meters, notes, staff = [], [], 0
    for track in midi.tracks:
        tick, sounding, has_notes = 0, {}, False
        for msg in track:
            tick += msg.time
            if msg.type == "time_signature":
                meters.append((q(tick), msg.numerator * 4 / msg.denominator))
            elif msg.type == "note_on" and msg.velocity:
                sounding[msg.note], has_notes = tick, True
            elif msg.type in ("note_on", "note_off") and msg.note in sounding:
                start = sounding.pop(msg.note)
                notes.append((q(start), msg.note, q(tick) - q(start), staff + 1))
        staff += has_notes
    meters = sorted(meters) or [(0, 4.0)]
    starts, position, i = [], 0.0, 0
    end = max((s + l for s, _, l, _ in notes), default=0)
    while position < end - 1e-6:  # bar lines from the time signatures
        while i + 1 < len(meters) and meters[i + 1][0] <= position + 1e-6:
            i += 1
        starts.append(position)
        position += meters[i][1]
    bars = [[] for _ in starts]
    for start, pitch, length, staff in notes:
        index = max(k for k, s in enumerate(starts) if s <= start + 1e-6)
        bars[index].append((start - starts[index], pitch, length, staff))
    return bars, starts


def musicxml_bars(xml_path):
    """MusicXML -> ([[(offset, pitch, length, staff)] per measure], measures with the wrong length).
    Tied notes are joined: a tie stop extends the open note instead of starting a new one."""
    root = ET.parse(xml_path).getroot()
    parts = root.findall("part")
    count = max(len(p.findall("measure")) for p in parts)
    bars, wrong_length = [[] for _ in range(count)], set()
    staff_base = 0
    for part in parts:
        divisions, meter, open_ties, staves = 1, 4.0, {}, 1
        for index, measure in enumerate(part.findall("measure")):
            divisions = int(measure.findtext("attributes/divisions") or divisions)
            staves = int(measure.findtext("attributes/staves") or staves)
            if measure.find("attributes/time/beats") is not None:
                meter = int(measure.findtext("attributes/time/beats")) * 4 / int(measure.findtext("attributes/time/beat-type"))
            cursor, start, longest = 0, 0, 0
            for el in measure:
                if el.tag in ("backup", "forward"):
                    cursor += int(el.findtext("duration") or 0) * (-1 if el.tag == "backup" else 1)
                if el.tag != "note" or el.find("grace") is not None:
                    continue
                duration = int(el.findtext("duration") or 0)
                if el.find("chord") is None:
                    start, cursor = cursor, cursor + duration
                longest = max(longest, cursor)
                if el.find("rest") is not None or el.find("pitch") is None:
                    continue
                pitch = ((int(el.findtext("pitch/octave")) + 1) * 12 + STEPS[el.findtext("pitch/step")]
                         + round(float(el.findtext("pitch/alter") or 0)))
                staff = staff_base + int(el.findtext("staff") or 1)
                ties = {t.get("type") for t in el.findall("tie")}
                offset, length = start / divisions, duration / divisions
                if "stop" in ties and pitch in open_ties:  # held over: extend, don't strike again
                    bar, k = open_ties.pop(pitch)
                    o, p, l, s = bars[bar][k]
                    bars[bar][k] = (o, p, l + length, s)
                    if "start" in ties:
                        open_ties[pitch] = (bar, k)
                    continue
                bars[index].append((offset, pitch, length, staff))
                if "start" in ties:
                    open_ties[pitch] = (index, len(bars[index]) - 1)
            if longest and abs(longest / divisions - meter) > 1e-6:
                wrong_length.add(index)
        staff_base += staves
    return bars, wrong_length


def similarity(a, b):
    """How alike two bars are by pitch content (0..1), ignoring rhythm."""
    pa, pb = Counter(n[1] for n in a), Counter(n[1] for n in b)
    total = sum(pa.values()) + sum(pb.values())
    return 2 * sum((pa & pb).values()) / total if total else 1.0


SKIP = -0.4  # cost of leaving a bar unpaired: two badly read bars in step still pair up (0 > 2 * SKIP)


def align(ref, got):
    """Line up bar sequences (Needleman-Wunsch on pitch content): [(ref index | None, got index | None)].
    A pair scores its similarity; an unpaired (missing or extra) bar costs SKIP."""
    n, m = len(ref), len(got)
    score = [[SKIP * (i + j) if not (i and j) else 0.0 for j in range(m + 1)] for i in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            score[i][j] = max(score[i - 1][j] + SKIP, score[i][j - 1] + SKIP,
                              score[i - 1][j - 1] + similarity(ref[i - 1], got[j - 1]))
    pairs, i, j = [], n, m
    while i or j:
        if i and j and abs(score[i][j] - score[i - 1][j - 1] - similarity(ref[i - 1], got[j - 1])) < 1e-9:
            pairs.append((i - 1, j - 1)); i, j = i - 1, j - 1
        elif i and (not j or abs(score[i][j] - score[i - 1][j] - SKIP) < 1e-9):
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return pairs[::-1]


def compare(ref, ref_starts, got, wrong_length=()):
    """Scores and per-bar details for one reading against the reference."""
    held = [(ref_starts[b] + o, ref_starts[b] + o + l, p) for b, notes in enumerate(ref) for o, p, l, _ in notes]
    exact = pitch_only = missed_ties = extra_bars = missing_bars = 0
    per_bar = []
    for r, g in align(ref, got):
        if r is None:
            extra_bars += 1
            continue
        if g is None:
            missing_bars += 1
            per_bar.append((r, 0, len(ref[r])))
            continue
        want, have = list(ref[r]), list(got[g])
        hits = 0
        for o, p, _, _ in want:  # same pitch at (nearly) the same place in the bar
            k = next((k for k, h in enumerate(have) if h[1] == p and abs(h[0] - o) <= EXACT), None)
            if k is not None:
                have.pop(k); hits += 1
        exact += hits
        pitch_only += sum((Counter(n[1] for n in ref[r]) & Counter(n[1] for n in got[g])).values())
        for o, p, _, _ in have:  # struck again although the reference still holds that note: a missed tie
            t = ref_starts[r] + o
            missed_ties += any(p == hp and hs < t - EXACT and he > t + EXACT for hs, he, hp in held)
        per_bar.append((r, hits, len(ref[r])))
    total_ref, total_got = sum(map(len, ref)), sum(map(len, got))
    return {"reference notes": total_ref, "notes read": total_got, "placed right": exact,
            "pitches right (any rhythm)": pitch_only, "missed ties": missed_ties,
            "missing bars": missing_bars, "extra bars": extra_bars, "bars with wrong length": len(wrong_length),
            "recall": exact / total_ref if total_ref else 1, "precision": exact / total_got if total_got else 1,
            "per bar": per_bar}


def read_sheet(pdf, folder):
    """The sheet through the app's own path: Audiveris (+ grace fallback), fixes, symbols."""
    import piano
    from sheet_labels import tuplet_marks, music_symbols, place_symbols, recognize
    scores = recognize(Path(pdf), folder, lambda detail: print("  …", detail))
    books = sorted(scores[0].parent.glob("*.omr"))
    placed = place_symbols(music_symbols(pdf) + tuplet_marks(pdf), books[0]) if books else []
    return piano.sheet_musicxml(scores[0], folder / "score.musicxml", placed)


def report(result, label):
    r = result
    f1 = 2 * r["recall"] * r["precision"] / (r["recall"] + r["precision"]) if r["recall"] + r["precision"] else 0
    print(f"\n{label}")
    print(f"  notes placed right   {r['placed right']:5d} of {r['reference notes']}   ({r['recall']:.0%} found, "
          f"{r['precision']:.0%} of what was read is right, F1 {f1:.0%})")
    print(f"  pitches right        {r['pitches right (any rhythm)']:5d} of {r['reference notes']}   "
          f"({r['pitches right (any rhythm)'] / r['reference notes']:.0%}, rhythm ignored)")
    print(f"  notes read           {r['notes read']:5d}")
    print(f"  missed ties          {r['missed ties']:5d}   (a held note struck again)")
    print(f"  bars                 {r['missing bars']} missing, {r['extra bars']} extra, "
          f"{r['bars with wrong length']} with the wrong length")
    worst = sorted((hits / total, bar) for bar, hits, total in r["per bar"] if total)[:8]
    print("  weakest bars         " + ", ".join(f"{bar + 1} ({share:.0%})" for share, bar in worst))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sheet, reference = sys.argv[1], sys.argv[2]
    ref, starts = reference_bars(reference)
    with tempfile.TemporaryDirectory() as folder:
        print(f"Reading {Path(sheet).name} (about a minute)…")
        xml = read_sheet(sheet, Path(folder))
        got, wrong = musicxml_bars(xml)
    report(compare(ref, starts, got, wrong), f"{Path(sheet).name} vs {Path(reference).name}")
