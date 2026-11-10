"""Recognize note positions and overlay names on the original PDF pages."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import re

import pymupdf


class SheetError(Exception):
    pass


NAMING = {"letters": dict(zip("cdefgab", "C D E F G A B".split())),
          "solfege": dict(zip("cdefgab", "Do Re Mi Fa Sol La Si".split()))}
SHEET_STAGES = ["Reading the PDF", "Recognizing the music", "Adding note names", "Preparing downloads"]


def audiveris_command():
    """An explicit executable, a PATH installation, or the bundled macOS launcher."""
    candidates = [os.environ.get("AUDIVERIS_BIN"), shutil.which("audiveris"),
                  str(Path(__file__).parent / ".tools/Audiveris.app/Contents/MacOS/Audiveris"),
                  "/Applications/Audiveris.app/Contents/MacOS/Audiveris"]
    return next((p for p in candidates if p and Path(p).is_file() and os.access(p, os.X_OK)), None)


def pdf_info(path):
    try:
        with pymupdf.open(path) as pdf:
            if pdf.needs_pass:
                raise SheetError("This PDF is password protected. Upload an unlocked copy.")
            if not pdf.is_pdf or not 1 <= len(pdf) <= 30:
                raise SheetError("Choose a PDF with 1–30 pages of sheet music.")
            return {"pages": len(pdf)}
    except SheetError:
        raise
    except Exception as exc:
        raise SheetError("That PDF could not be read. Try exporting it again.") from exc


def recognize(path, folder, progress=lambda detail: None):
    command = audiveris_command()
    if not command:
        raise SheetError("PDF recognition needs Audiveris. Install it, then restart the app (see README.md).")
    logs = []
    short_staves, high_resolution = False, False
    for _ in range(3):
        label = "Standard recognition"
        if short_staves:
            label = "Short-staff retry"
        if high_resolution:
            label += " at higher resolution"
        if logs:
            progress(label + "; keeping every page")
        # Each attempt has a fresh output directory: failed/partial exports from a
        # previous run must never be mistaken for a complete score.
        attempt = Path(tempfile.mkdtemp(prefix="retry-" if logs else "standard-", dir=folder))
        options = (["-constant", "org.audiveris.omr.sheet.grid.LinesRetriever.minStaffLength=12"]
                   if short_staves else [])
        if high_resolution:
            options += ["-constant", "org.audiveris.omr.image.ImageLoading.pdfResolution=600"]
        try:
            done = subprocess.run([command, "-batch", "-export", *options, "-output", str(attempt), "--", str(path)],
                                  capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired as exc:
            raise SheetError("Music recognition took longer than 30 minutes. Try fewer pages or a clearer PDF.") from exc
        except OSError as exc:
            raise SheetError("Audiveris could not start. Check its installation (see README.md).") from exc
        log = done.stdout + "\n" + done.stderr
        logs.append(label + "\n" + log)
        (folder / "recognition.log").write_text("\n\n".join(logs))
        scores = sorted(attempt.rglob("*.mxl"))
        if not done.returncode and scores:
            return scores
        # A short ending staff can fall below Audiveris's default minimum width
        # (30 staff spaces). Retry the whole PDF; never omit the failed page.
        if "No system found" in log and not short_staves:
            short_staves = True
        elif "too low interline value" in log and not high_resolution:
            high_resolution = True
        else:
            break
    if "No system found" in log:
        raise SheetError("A page's music staves could not be detected, even after retrying short staves. "
                         "The whole PDF was kept; try a different export of the score.")
    raise SheetError("Music recognition could not complete. Try a different PDF export or scan; "
                     "technical details are saved in recognition.log.")


def note_positions(book, page_count):
    """Read original raster coordinates and written pitch from Audiveris's .omr.

    Pitch is a diatonic staff position, positive downwards from the middle line.
    A clef's reference pitch makes this work for clef changes and ledger notes,
    including C clefs. Octave transpositions do not change the letter name.
    """
    pages = {}
    references = {"TREBLE": 4, "BASS": 3, "BARITONE": 3, "ALTO": 0,
                  "TENOR": 0, "MEZZO_SOPRANO": 0, "SOPRANO": 0}
    with zipfile.ZipFile(book) as archive:
        for filename in archive.namelist():
            match = re.fullmatch(r"sheet#(\d+)/sheet#\1.xml", filename)
            if not match:
                continue
            index = int(match[1]) - 1
            root = ET.fromstring(archive.read(filename))
            picture = root.find("picture")
            if picture is None:
                raise SheetError(f"Recognition did not save page {index + 1}'s dimensions.")
            width, height = int(picture.get("width")), int(picture.get("height"))
            if width <= 0 or height <= 0:
                raise SheetError("Recognition returned invalid page dimensions.")
            notes, seen = [], set()
            for system in root.iter("system"):
                clefs = {}
                for symbol in system.iter("clef"):
                    bounds = symbol.find("bounds")
                    if symbol.get("kind") not in references or bounds is None:
                        continue
                    staff = symbol.get("staff")
                    clefs.setdefault(staff, []).append((float(bounds.get("x")), symbol))
                for staff in clefs:
                    clefs[staff].sort(key=lambda c: c[0])
                for head in system.iter("head"):
                    bounds = head.find("bounds")
                    if bounds is None or head.get("pitch") is None:
                        continue
                    x, y, w, h = [float(bounds.get(k)) for k in ("x", "y", "w", "h")]
                    if w <= 0 or h <= 0:
                        continue
                    available = clefs.get(head.get("staff"), [])
                    # The header clef can extend slightly into the first note's x.
                    prior = [symbol for cx, symbol in available if cx <= x + w / 2]
                    if not prior:
                        raise SheetError(f"Could not resolve a note's clef on page {index + 1}. "
                                         "Try a clearer export of the sheet.")
                    symbol = prior[-1]
                    step = "cdefgab"[(references[symbol.get("kind")] + round(float(symbol.get("pitch")))
                                      - round(float(head.get("pitch")))) % 7]
                    location = (x, y, w, h)
                    if location in seen:  # shared heads in multiple voices need only one label
                        continue
                    seen.add(location)
                    notes.append({"box": [x / width, y / height, (x + w) / width, (y + h) / height],
                                  "step": step, "filled": "BLACK" in head.get("shape", "")})
            pages[index] = notes
    if set(pages) != set(range(page_count)):
        raise SheetError("Recognition did not return positions for every page. No partial PDF was created.")
    if not any(pages.values()):
        raise SheetError("No pitched notes were recognized in this sheet.")
    return [pages[i] for i in range(page_count)]


def annotate_pdf(source, output, positions, naming):
    """Append text to the original PDF; keep its pages, artwork, metadata and boxes."""
    if naming not in NAMING:
        raise SheetError("Choose letter names or fixed-Do solfège.")
    font = pymupdf.Font("hebo")
    count = 0
    with pymupdf.open(source) as pdf:
        if len(pdf) != len(positions):
            raise SheetError("The recognized pages do not match the uploaded PDF.")
        for page, notes in zip(pdf, positions):
            shape = page.new_shape()
            for item in notes:
                box = pymupdf.Rect(item["box"])
                box = pymupdf.Rect(box.x0 * page.rect.width, box.y0 * page.rect.height,
                                   box.x1 * page.rect.width, box.y1 * page.rect.height)
                name = NAMING[naming][item["step"]]
                # Font metrics center the visible letters inside the head. A small
                # horizontal stretch keeps two/three-letter names tall enough to read.
                size = box.height * (0.72 if item["filled"] else 0.55)
                text_width = font.text_length(name, fontsize=size)
                available = box.width * (0.76 if item["filled"] else 0.57)
                stretch = min(1.0, available / text_width)
                start = pymupdf.Point((box.x0 + box.x1 - text_width * stretch) / 2,
                                     (box.y0 + box.y1) / 2 + size * 0.36)
                start = start * page.derotation_matrix
                # The scale is applied in unrotated PDF coordinates.
                scale = pymupdf.Matrix(stretch, 1) if page.rotation in (0, 180) else pymupdf.Matrix(1, stretch)
                shape.insert_text(start, name, fontsize=size, fontname="hebo",
                                  color=(1, 1, 1) if item["filled"] else (0, 0, 0),
                                  rotate=page.rotation, morph=(start, scale))
                count += 1
            shape.commit(overlay=True)
        pdf.save(output, deflate=True)
    return count


def pdf_previews(path, folder):
    """Only previews are rasterized. The downloadable PDF retains original vectors."""
    paths = []
    with pymupdf.open(path) as pdf:
        for i, page in enumerate(pdf, 1):
            image = folder / f"page-{i}.png"
            page.get_pixmap(dpi=144, alpha=False).save(image)
            paths.append(image)
    return paths
