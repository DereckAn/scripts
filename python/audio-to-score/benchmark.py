"""Score the app's sheet reading on a set of pieces, so every change has a before and after.

Run: .venv/bin/python benchmark.py [FOLDER]   (default ~/Downloads/benchmark)

FOLDER holds pairs "Name.pdf" + "Name.mid" (an exact MIDI of the same edition, e.g. from the
Mutopia Project). Audiveris's readings are cached in FOLDER/.cache (first run: about a minute
per piece; later runs: seconds). Each run is saved in FOLDER/results and compared with the
previous one. Rule of thumb for a change: the total goes up and no piece drops noticeably.
"""
import json
import sys
import time
import traceback
from pathlib import Path

import accuracy as A


def run(folder):
    folder = Path(folder).expanduser()
    rows = []
    for pdf in sorted(folder.glob("*.pdf")):
        midi = pdf.with_suffix(".mid")
        if not midi.is_file():
            continue
        print(f"{pdf.stem} …", flush=True)
        try:
            got, wrong = A.musicxml_bars(A.read_sheet(pdf, folder / ".cache" / pdf.stem))
            pickup, _, _, r = A.best_pickup(midi, got, wrong)
            rows.append({"piece": pdf.stem, "notes": r["reference notes"], "placed": r["placed right"],
                         "pitches": r["pitches right (any rhythm)"], "read": r["notes read"],
                         "missed ties": r["missed ties"], "wrong bars": r["bars with wrong length"],
                         "missing bars": r["missing bars"], "extra bars": r["extra bars"], "pickup": pickup})
        except Exception as exc:  # one unreadable sheet must not stop the others
            rows.append({"piece": pdf.stem, "error": f"{type(exc).__name__}: {exc}"})
            traceback.print_exc(limit=1)
    return rows


def show(rows, previous=None):
    before = {r["piece"]: r for r in (previous or []) if "error" not in r}
    print(f"\n{'piece':32s} {'notes':>6s} {'placed':>7s} {'pitches':>8s} {'ties':>5s} {'bad bars':>8s}  change")
    total = {"notes": 0, "placed": 0, "pitches": 0}
    for r in rows:
        if "error" in r:
            print(f"{r['piece']:32s} FAILED  {r['error'][:80]}")
            continue
        for k in total:
            total[k] += r[k]
        change = ""
        if r["piece"] in before:
            delta = r["placed"] / r["notes"] - before[r["piece"]]["placed"] / before[r["piece"]]["notes"]
            change = f"{delta:+.1%}" if abs(delta) >= 0.0005 else "="
        bad = r["wrong bars"] + r["missing bars"] + r["extra bars"]
        print(f"{r['piece']:32s} {r['notes']:6d} {r['placed'] / r['notes']:7.0%} {r['pitches'] / r['notes']:8.0%} "
              f"{r['missed ties']:5d} {bad:8d}  {change}")
    if total["notes"]:
        prev_total = sum(r["placed"] for r in before.values()), sum(r["notes"] for r in before.values())
        change = f"{total['placed'] / total['notes'] - prev_total[0] / prev_total[1]:+.1%}" if prev_total[1] else ""
        print(f"{'TOTAL':32s} {total['notes']:6d} {total['placed'] / total['notes']:7.0%} "
              f"{total['pitches'] / total['notes']:8.0%} {'':5s} {'':8s}  {change}")


if __name__ == "__main__":
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "~/Downloads/benchmark").expanduser()
    results = folder / "results"
    results.mkdir(parents=True, exist_ok=True)
    earlier = sorted(results.glob("*.json"))
    rows = run(folder)
    (results / f"{time.strftime('%Y-%m-%d_%H%M%S')}.json").write_text(json.dumps(rows, indent=1))
    show(rows, json.loads(earlier[-1].read_text()) if earlier else None)
