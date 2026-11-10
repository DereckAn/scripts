# Piano to Score

Run `.venv/bin/python piano.py` and open http://127.0.0.1:7861.
The **Convert** view transcribes piano recordings. **Label sheet** recognizes
printed piano scores and puts letter names or fixed-Do solfège inside noteheads.
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
- Filled heads use white text; half and whole notes use dark text in the hollow.
- Labels are appended to the **original PDF** using notehead positions from the
  Audiveris `.omr` book. Page count, dimensions, crop, rotation, artwork, metadata,
  spacing, titles and markings remain in place. The uploaded file is never overwritten.
- The PDF remains vector-based when the original is vector-based. Only the browser
  preview uses PNG images. Download one annotated PDF containing every original page.
- Recognition still can misidentify or miss notes. Check labels against the original.
  Missing page-position data stops the job instead of creating a partial result.
- Changing the naming system reuses recognition. Jobs and cached sources are
  tracked in memory for the current server session; files live in the temporary
  `piano-to-score` folder. Recognition diagnostics are in `recognized/recognition.log`
  below the upload's temporary folder.
- Cancellation takes effect at the next stage boundary.

## Checks

```sh
.venv/bin/python test_piano.py
.venv/bin/python -m unittest test_sheet_labels test_svg_import
```

The PDF tests cover upload validation, the short-staff retry, note position and clef
changes, shared chord heads, both naming systems, cache reuse, and original page
preservation. Pixel comparisons check that all changes stay inside notehead bounds,
including cropped pages and 0/90/180/270-degree rotations.

SVG tests run the bundled shared converter in Chromium and check natural filename
order, intrinsic page sizes, vector output, local references and input validation.
