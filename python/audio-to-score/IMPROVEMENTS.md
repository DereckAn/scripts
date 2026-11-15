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

Labeled sheets read badly: letters inside noteheads stop them looking like noteheads.
Read the clean sheet, then label it.

## 1. Trustworthy results (biggest impact)

- [x] **Duplets ("2" in 6/8, 9/8, 12/8).** Audiveris ignores them; the "2" is read from the
      PDF's text layer and the pair it sits over is stretched 3/2 (`apply_duplets`). Clair de
      Lune: 13 duplets fixed, 72% → 75% placed right. Only printed "2"s are found.
- [ ] **Sextuplets and other "6" groups** (Clair de Lune bars 19–26, 49–50, 71: the weakest bars).
- [ ] **Mid-bar clef changes** (bar 17: left hand switches to treble clef; Audiveris drops the
      small clef, so those chords come out a sixth too low). Readable from Finale/SMuFL fonts;
      LilyPond's Emmentaler glyphs have no usable codes.
- [ ] **Voices split wrongly** (a hand's notes spread over voices that overrun the bar).
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
