# Improvement ideas

Backlog for Piano to Score, roughly in order of value for effort. Pick one, build it, tick it off.

## Measuring progress

`accuracy.py` scores a sheet reading against an exact reference MIDI (same path as
"Play in Practice Studio"; tied notes joined; bars lined up by content):

```sh
.venv/bin/python accuracy.py SHEET.pdf REFERENCE.mid
```

Baseline, Clair de Lune vs Mutopia's MIDI (1,468 notes, 72 bars), 2026-11-15:

| Sheet | Notes placed right | Pitches right | Missed ties | Bars wrong length |
|---|---|---|---|---|
| Mutopia PDF (LilyPond, same edition) | 72% | 88% | 97 | 28 |
| `clarodelunaletras.pdf` (note names printed inside the heads) | 23% | 54% | 159 | 66 |
| Mutopia PDF, after duplet repair | 75% | 88% | 90 | 26 |
| Mutopia PDF, after "2" and "6" repair | 77% | 88% | 87 | 23 |
| Mutopia PDF, after voice re-timing | 79% | 88% | 78 | 23 |

Labeled sheets read badly: letters inside noteheads stop them looking like noteheads.
Read the clean sheet, then label it.

### Benchmark (9 pieces, 8,121 notes): `.venv/bin/python benchmark.py`

Sheets + exact MIDIs from the Mutopia Project in `~/Downloads/benchmark` (readings cached,
each run saved and compared with the previous). Baseline 2026-11-15:

| Piece | Notes | Placed right | Pitches right | Missed ties | Bad bars |
|---|---|---|---|---|---|
| Bach, Prelude in C | 549 | 66% | 88% | 14 | 13 |
| Beethoven, Für Elise | 905 | 89% | 93% | 0 | 7 |
| Chopin, Nocturne Op. 9 No. 2 | 1,242 | 87% | 91% | 7 | 38 |
| Chopin, Prelude Op. 28 No. 4 | 600 | 98% | 100% | 7 | 2 |
| Debussy, Arabesque No. 1 | 1,448 | 54% | 79% | 171 | 50 |
| Debussy, Clair de lune | 1,468 | 79% | 88% | 78 | 23 |
| Mozart, K. 545 mvt 1 | 1,288 | 91% | 93% | 0 | 2 |
| Satie, Gymnopédie No. 1 | 282 | 87% | 90% | 5 | 1 |
| Schumann, Träumerei | 339 | 78% | 93% | 38 | 6 |
| **Total** | **8,121** | **79%** | **89%** | | |

Most notes lost: Arabesque (665), Clair de lune (308), Bach Prelude (189: overlapping voices,
a held bass + tied second voice + 16ths, split into 5 voices with notes dropped), Nocturne (163).
Rule for changes: the total goes up and no piece drops noticeably.

**Unmarked triplets (2026-11-15):** Arabesque 54% → 64% (missed ties 171 → 74), total 79% → 81%,
no other piece changed. Engravers print "3" on the first triplet groups only (simile); a beam
group of exactly three eighths in simple time is a triplet when its voice runs past the bar line,
or anywhere in a sheet that marks at least 5 triplet groups; later voices in that bar move onto the
corrected grid. Inside the Arabesque: 33 bars better (+100 notes), 12 slightly worse (−30; bar 49
8 → 0) where Debussy does beam plain eighths in threes. Caught by the benchmark on the way: with
no recognized time signature (the Nocturne's 12/8 is missed by Audiveris) the rule had assumed 4/4
and made 114 false triplets (Nocturne 87% → 36%); it now needs a known simple meter.

**Grace-note detection vs plain reading (2026-11-15):** total 81% → 83%. Bach 66% → 71%,
Arabesque 64% → 70% (pitches 79% → 87%), nothing else changed. Audiveris's grace-note switch
quietly breaks the rhythm of some dense textures, yet the Nocturne needs it (−4.8% without).
Now: if more than 5% of bars come out broken, a second reading without it is made, and
`pick_reading` keeps it only if it has ≥2 fewer broken bars after the app's own fixes (raw
counts were too close: Arabesque 47 vs 46 raw, 24 vs 22 after fixes). 4 of 9 sheets are read
twice (about a minute more each). A bar with no recognized time signature isn't judged.
- [ ] **Bach Prelude's texture is still at 71%**: Audiveris sees every notehead (18 of 18 in
      bar 2) but its rhythm analysis of a held bass + tied inner voice + 16ths builds a broken
      time grid and silently drops notes. Fixing it means rebuilding bar rhythm from the
      noteheads ourselves (stems, beams, flags, voices): a big project.

## 1. Trustworthy results (biggest impact)

- [x] **Duplets ("2" in 6/8, 9/8, 12/8).** Audiveris ignores them; the "2" is read from the
      PDF's text layer and the pair it sits over is stretched 3/2 (`apply_duplets`). Clair de
      Lune: 13 duplets fixed, 72% → 75% placed right. Only printed "2"s are found.
- [x] **"6" groups in compound meters** (six in the time of nine). Audiveris misses them or
      reads 6:4; printed "6"s and Audiveris's short 6:4 eighth groups are fixed by
      `apply_tuplets` (bars 19, 21, 23 improved a lot). The rest (left hand of 19–26, 49–50, 71)
      sit in wrongly split voices, see below.
- [ ] **Mid-bar clef changes** (bar 17: left hand switches to treble clef; Audiveris drops the
      small clef, so those chords come out a sixth too low). Readable from Finale/SMuFL fonts;
      LilyPond's Emmentaler glyphs have no usable codes.
- [x] **Mistimed voices** (`retime_voices`). Notes stacked vertically are played together:
      voices that fill their bar give a page-position → time map, and a voice whose every
      note lines up with them is re-timed from it. Clair de Lune: 11 voices, bar 23 now
      perfect, 21 and 19 close. Conservative: a voice with a note between trusted notes is
      left alone.
- [ ] **Voices that run past the bar line** (23 bars still). Re-timing needs a trusted voice
      in the bar; bars where every voice is broken (e.g. 49, 50, 71) need another anchor.
      In those bars Audiveris also misreads staves, voices and octaves (bar 49: a flowing
      arpeggio crossing between the hands): 80% of pitches right but only 54% placed right.
- [ ] **Using a recording to fix broken bars: tried 2026-11-15, not adopted.** Method and results:
      - Transcribe the recording (ByteDance: 1,472 notes vs 1,468 in the score, 70 s).
      - Align it to the sheet: chroma DTW (20 fps, pretty_midi chroma of both + 1e-3, cosine),
        then pin each bar start to the moment most of the bar's first-chord pitches are struck
        within 80 ms (search ±1.2 s around the DTW guess). Works well: bar starts within
        0.05 s of the answer key's (median), 90% within 0.17 s. Plain DTW bar mapping (0.09 s
        median but 18 bars > 0.3 s off) and note pins from clean bars were worse.
      - Re-time broken voices: match voice events to the recording's chords by note names
        (Needleman-Wunsch), map times into the bar linearly, snap to 1.5/0.75/0.5/0.25 grids,
        rebuild with standard tuplet ratios. Result: 79% -> 78% placed right; only bars
        where a voice runs past the bar line can be touched (others got broken), and there
        the staff/voice/octave errors dominate.
      - Reused for **Add recording** in the Studio (done): the pianist's recording plays in step
        with a sheet's score (`recording_sync.py`).
- [ ] **Warn when a sheet already has note names inside the heads** (it reads far worse).

Recognition is the weak point: a misread bar just sounds wrong and you have to notice it.

- [ ] **Flag suspicious bars.** Bars whose notes don't add up to the time signature are
      almost always misread (e.g. "Merry Go Round of Life" bars 28, 45, 154, 155). Mark them on
      the score: "these 4 bars may be misread". Cheap, high trust value.
- [ ] **Side-by-side check.** Original page next to the re-engraved score, scrolling together.
- [ ] **Small corrections in the app.** Change a note's pitch or length in a flagged bar and
      replay. Bigger fixes: the MusicXML download already opens in MuseScore.

## 2. Active practice

- [ ] **Play along with a MIDI keyboard** (Web MIDI API, built into browsers). A *wait mode*
      where the waterfall pauses until you play the right notes; then scoring
      ("92% correct, left hand rushed in bar 12").
- [ ] **Gradual speed-up loops.** Loop a passage from 60% speed, +5% per pass.
- [ ] **Fingering numbers.** Audiveris has a `fingerings` switch; show them on the score.

## 3. Reliable day to day

- [ ] **Keep your work (Library).** Results live in a temp folder and server memory; a
      restart loses them. Save each piece (score, audio, settings) to a real folder.
- [ ] **Detect an outdated server.** The page is read fresh from disk but the Python server
      isn't, which caused the misleading "Could not start labeling". Compare versions and say
      "restart the server", or auto-reload during development.
- [ ] **Use it at the piano.** Open the app from an iPad/phone on the same Wi-Fi; a layout
      that fits a music stand.

## 4. Closer to the printed sheet

- [ ] **Pedal markings and dynamics from sheets** (audio conversions already have pedaling).
- [ ] **Trills, fermatas and arpeggios on scans.** Today they're read from the music font of
      PDFs exported by notation software; scans need image recognition of those symbols.
- [ ] **Metronome marks** like "♩ = 50", and words the text reader misses ("rit.").
- [x] **Grace-note setting can break other sheets (done).** Audiveris's `smallHeads`
      switch finds grace notes, but on Clair de Lune it mistakes normal chords for small ones:
      3 bars fail rhythm analysis ("StackRhythm error … SmallChordInter"), 70 notes and 7
      ties are lost. Fix: read with the switch, and if the log shows those errors, read again
      without it and keep that result.
- [ ] **Ties on dense chords (Clair de Lune).** Even at best, Audiveris misreads some tied
      two-note chords and cross-staff beams (85 tie starts vs 95 ends; bar 1's La/Fa chord
      comes out as a G♭ half note). Higher resolution doesn't help (420 dpi was worse). Ideas:
      flag those bars (see 1), and repair unmatched ties where the next note has the same pitch.
- [ ] **Upload MusicXML directly.** For well-known pieces a MusicXML/.mxl file (e.g. exported
      from MuseScore) skips recognition entirely: exact notes, ties, rhythms and symbols.
      The engraving/playback path already exists, so this is small.
- [ ] **Read notes from the PDF's music font.** PDFs exported from notation software draw
      every notehead as a font character (as we already do for trills/fermatas). Reading the
      notes that way would be exact for those PDFs. Big project.

## 5. Housekeeping

- [ ] **Commit the work in logical pieces** (PDF labeling, AI coloring, clean PDF, fonts,
      Studio names, sheet playback, ornaments, tempo words).
- [ ] **Split large files.** `piano.py` and `web/index.html` have grown large; split by area
      (sheet playback, labeling, Studio UI) to make changes safer.
