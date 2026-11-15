# Piano to Score

Run `.venv/bin/python piano.py` and open http://127.0.0.1:7861.
The **Convert** view transcribes piano recordings. **Label sheet** recognizes
printed piano scores and adds note names, pitch colors, or both to the original noteheads.
Both tools run locally and share the same queue and download storage.
Uploaded sheets are annotated directly; Verovio remains the renderer for audio transcriptions.

## PDF recognition setup

Install Python dependencies from `requirements.txt`, including PyMuPDF, and the
Chromium renderer:

```sh
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m playwright install --only-shell chromium
```

Install [Audiveris](https://github.com/Audiveris/audiveris/releases) for your platform.
On macOS, place `Audiveris.app` in `/Applications` or this project's `.tools` folder.
The macOS application includes its Java runtime. Alternatively, put `audiveris` on
PATH or set `AUDIVERIS_BIN` to its executable path before starting the server:

```sh
export AUDIVERIS_BIN="/path/to/audiveris"
.venv/bin/python piano.py
```

The server uses Audiveris's [batch MusicXML export](https://audiveris.github.io/audiveris/_pages/guides/advanced/cli/).
Recognition can take several minutes. PDFs are limited to 50 MB and 30 pages;
password-protected PDFs must be unlocked first. Clear, straight scans of printed
notation work best. Handwriting and poor scans may not be recognized accurately.
If staff detection fails (for example, a single short final measure on its own
page), recognition automatically retries with a smaller minimum staff width.
Small pages with insufficient recognition resolution also retry at 600 DPI.
All attempts include every page; failed pages are never silently dropped.

### AI coloring setup (optional)

```sh
uv pip install -p .venv oemer==0.1.5 numpy==1.24.3 opencv-python==4.11.0.86
curl -L -o .venv/lib/python3.10/site-packages/oemer/checkpoints/seg_net/model.onnx \
  https://github.com/BreezeWhite/oemer/releases/download/checkpoints/2nd_model.onnx
```

Only the 38 MB notehead model is needed. Newer oemer releases require `onnxruntime-gpu`,
which has no macOS build. Restart the app; the AI option is enabled when the model exists.

## Play a sheet in the Practice Studio

On **Label sheet**, upload a PDF or image and press **Play in Practice Studio**: no
recording needed. Audiveris's MusicXML (the same recognition labeling uses, cached per
upload) is engraved by Verovio and voiced per hand exactly like a converted recording, so
the waterfall, sheet view, loops, speed, metronome, note names/colors and downloads all
work. Differences: the score is re-engraved from what was recognized (check it against the
original), there is no "Original audio", and tempo marks are rarely recognized, so playback
starts at ♩ = 120 (use Speed). The key comes from the key signature.

What playback picks up from the sheet:
- **Grace notes** (small notes before a main note): Audiveris's small-notehead switches are
  on, so they are recognized and played quickly before their main note. On some sheets
  (Clair de Lune) the switch makes Audiveris take normal chords for small ones and lose those
  bars ("StackRhythm error … SmallChord" in the log); the sheet is then read again without it.
- **Tempo words**, once Audiveris can read text: tempo terms set the speed (Moderato ≈ 108,
  Allegretto ≈ 112, Presto ≈ 180, …, see `TEMPO_TERMS` in `piano.py`), rit./rall. slow down
  over the next three bars, accel. speeds up, and "a tempo" / "Tempo I" go back. The
  metronome, count-in and ♩ display follow these changes bar by bar.
- **Duplets and "6" groups** in 6/8, 9/8, 12/8 (notes played 1.5x their written length):
  the printed "2"/"6" is read from the PDF's text layer and matched to the notes it is
  centered on, only where that voice is short by exactly the missing time; Audiveris's own
  6:4 readings of such groups are corrected too.
- **Mistimed voices**: notes stacked vertically are played together. In a bar where some
  voices fill the bar exactly, a voice whose notes all line up under/over theirs but whose
  timing disagrees is re-timed from those positions (standard tuplet ratios only).
- **Chords with beams**: Audiveris repeats a chord's beam on each note, which made Verovio
  drop those notes and shorten bars; the beam is kept on the chord's first note only.
- **Fermatas, trills and arpeggios** (Audiveris doesn't detect them): read from the PDF's
  music font when the sheet was exported from notation software (Finale's Maestro font, or
  SMuFL fonts from MuseScore, Dorico and newer Finale). The trill's "tr" and the arpeggio
  use the same wavy glyph, horizontal vs vertical. Each symbol is placed on its bar, beat
  and staff with Audiveris's measure grid, written into the MusicXML (so the score shows it)
  and played: arpeggios roll (Verovio), trills alternate with the next note up in the key at
  8 notes/s, fermatas hold their note about twice as long (up to 2 s extra). Holds are added
  to the MIDI tempo and the score's note/bar times are shifted to match, so highlighting,
  waterfall and audio stay in step. Scans and PDFs drawn only as shapes have no font
  glyphs, so these symbols aren't found there.
- Not yet: metronome marks like "♩ = 50" (the note symbol can't be read as text).

Text reading needs Tesseract's English data in Audiveris's folder (one time, 23 MB):

```sh
curl -L -o ~/Library/Application\ Support/AudiverisLtd/audiveris/tessdata/eng.traineddata \
  https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata
```

Sheets read before these settings are read again once (the cache is versioned).

### Add a recording to a sheet

In the Studio, a score opened from a sheet shows **Add recording**: upload a recording of
the same piece and arrangement, and **Original audio** plays it with the waterfall, score
highlighting, bar jumps and loops following the pianist (`recording_sync.py`). The
recording is transcribed (about 70 s for 5 minutes), roughly aligned to the score
(chroma + dynamic time warping), then each bar's first chord is pinned to the moment its
notes are struck together. Bars with no chord found keep the rough guess unless it is far
from their neighbours; the Studio interpolates between the rest. Clair de Lune (Mutopia
sheet + a Wikimedia Commons recording): 67 of 72 bars matched, bar starts within 0.06 s
of a reference alignment (median), 90% within 0.44 s. Too few matched bars means the
recording is probably a different piece or arrangement, and is refused.

## Clean PDF (scans and photos)

Upload a PDF or an image (PNG, JPG, WEBP, TIFF; images become a one-page, A4-wide PDF,
so labeling works on them too) and press **Make clean PDF**. Each scanned page is
rendered at 600 dpi; uneven lighting and paper tone are flattened, the ink is cut
halfway between the page's own ink and paper levels, and potrace traces it into vector
curves at the original page size. The result is a small, vector-only PDF that stays
sharp at any zoom, with the original layout and symbol shapes. Pages that are already
vector are copied unchanged. Needs `brew install potrace`.

Limits: very faint or broken lines in blurry photos can show small gaps, and strokes
can come out slightly bolder than a gray photo. Pages are not straightened or cropped.

## SVG input

The same upload area accepts one PDF or up to 30 SVG pages. SVG pages are sorted
naturally by filename (`page-2.svg` before `page-10.svg`) and automatically converted
to a vector PDF at their intrinsic dimensions, without added margins or re-engraving.
They then use the same original-page annotation flow. SVG input still needs music
recognition; a drawing does not necessarily contain pitch metadata.

This reuses `my-scripts-ui/src/utils/svg-to-pdf.ts` through the small browser entry
`my-scripts-ui/src/utils/score-pdf-bridge.ts`. Its bundled dependencies are served
locally, so the Next.js app does not need to run. To rebuild after converter changes:

```sh
cd ../../my-scripts-ui
bun install
bun run build:score-pdf
```

Each SVG is limited to 25 MB and the set to 50 MB. Files should contain self-contained
vector artwork; external fonts/images must be embedded or converted to paths.

## Naming and output

- Letters: C, D, E, F, G, A, B.
- Fixed Do: Do, Re, Mi, Fa, Sol, La, Si. C is always Do, regardless of key.
- Labels follow written pitch spelling. Sharps, flats, naturals and key signatures
  remain in the notation; the label inside a C-sharp head is C (or Do).
- Note names and note colors are independent toggles. Enable either one or both.
- Name fonts: Sans serif (Helvetica Bold), Serif (Times Bold), Monospace (Courier Bold),
  plus EB Garamond, League Spartan, Newsreader and Bodoni Moda (Google Fonts, SIL Open
  Font License, see `web/fonts/OFL-*.txt`). Those are Bold static cuts made from the
  variable fonts with fontTools (`wght` 700, `opsz` 12 for small text), embedded and
  subset into the PDF; the style preview loads the same files. To add another font,
  put its `.ttf` in `web/fonts` and add one entry to `FONTS` in `sheet_labels.py`, one
  `<option>` and one `@font-face` in `web/index.html`. Labels fit inside the heads.
- Label color can be custom, or automatic contrast: light/dark text based on the
  filled head's color and dark text in hollow heads. The style sample updates live.
- Each written pitch C through B has a customizable color shared by every octave;
  C/Do defaults to red. Reset colors restores the original seven-color palette.
- Coloring method **Standard**: when the PDF draws each head as its own vector shape
  (exports from notation apps), that exact shape is redrawn in color, so it looks
  native. Otherwise it overlays the notehead ink saved in the Audiveris glyph run
  table, as vector shapes. Hollow ring centers and staff lines through them are kept.
- Coloring method **AI · scans**: each page is rendered at 300 dpi and oemer's local
  segmentation model finds the notehead pixels (no stems or staff lines). Only those
  pixels inside each recognized note are recolored, keeping their original darkness,
  and laid over the page as a transparent image. Notes the AI misses use Standard.
  Runs on CPU, roughly a minute per page.
- Labels are appended to the **original PDF** using notehead positions from the
  Audiveris `.omr` book. Page count, dimensions, crop, rotation, artwork, metadata,
  spacing, titles and markings remain in place. The uploaded file is never overwritten.
- The PDF remains vector-based when the original is vector-based. Only the browser
  preview uses PNG images. Download one annotated PDF containing every original page.
- Oversized pages (over Audiveris's 20-megapixel limit at 300 dpi, about A3, e.g. PDFs
  exported at 1 px = 1 pt) are read from an A4-sized copy, and the labeled PDF is returned
  at that A4 size. Normal-sized PDFs are labeled exactly as uploaded.
- If a line's clef is not recognized (octave clefs are sometimes missed), each staff keeps
  the clef it ended the previous line with. Notes with no clef to go on are left
  unlabeled and counted in the result instead of failing the whole job.
- Recognition still can misidentify or miss notes. Check labels against the original.
  Missing page-position data stops the job instead of creating a partial result.
- Changing names, fonts, label colors or the note palette reuses recognition.
  Jobs and cached sources are
  tracked in memory for the current server session; files live in the temporary
  `piano-to-score` folder. Recognition diagnostics are in `recognized/recognition.log`
  below the upload's temporary folder.
- Cancellation takes effect at the next stage boundary.

## Checks

```sh
.venv/bin/python test_piano.py
.venv/bin/python -m unittest test_sheet_labels test_svg_import test_note_styles test_accuracy test_recording_sync
.venv/bin/python accuracy.py SHEET.pdf REFERENCE.mid   # sheet reading vs an exact MIDI
```

The PDF tests cover upload validation, the short-staff retry, note position and clef
changes, shared chord heads, both naming systems, cache reuse, and original page
preservation. Pixel comparisons check that all changes stay inside notehead bounds,
including cropped pages and 0/90/180/270-degree rotations.

SVG tests run the bundled shared converter in Chromium and check natural filename
order, intrinsic page sizes, vector output, local references and input validation.

Style tests cover names-only, colors-only, combined output, actual PDF fonts and
text colors, automatic contrast, shared pitch colors, hollow centers, staff lines,
vector recoloring, validation and cached recognition across style changes.
