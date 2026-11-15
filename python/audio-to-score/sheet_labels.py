"""Recognize note positions and overlay names on the original PDF pages."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import re
import contextlib
import importlib.util
import io

import numpy as np
import pymupdf


class SheetError(Exception):
    pass


NAMING = {"letters": dict(zip("cdefgab", "C D E F G A B".split())),
          "solfege": dict(zip("cdefgab", "Do Re Mi Fa Sol La Si".split()))}
FONT_DIR = Path(__file__).parent / "web/fonts"
# Built-in PDF fonts by name; others are Bold cuts of Google Fonts (OFL) in web/fonts,
# embedded and subset into the PDF. Adding a font = one entry here + one in the page's picker.
FONTS = {"sans": "hebo", "serif": "tibo", "mono": "cobo",
         "garamond": FONT_DIR / "eb-garamond-bold.ttf", "spartan": FONT_DIR / "league-spartan-bold.ttf",
         "newsreader": FONT_DIR / "newsreader-bold.ttf", "bodoni": FONT_DIR / "bodoni-moda-bold.ttf"}
NOTE_COLORS = dict(zip("cdefgab", ["#dc2626", "#ea580c", "#ca8a04", "#16a34a",
                                    "#0284c7", "#7c3aed", "#db2777"]))
# CSS families for SVG labels (rendered scores and the page preview). File fonts are
# declared as "Label <name>" with @font-face pointing at the same files the PDF embeds.
FONT_CSS = {"sans": "Arial, Helvetica, sans-serif", "serif": "'Times New Roman', Times, serif",
            "mono": "'Courier New', Courier, monospace", "garamond": "'Label EB Garamond', serif",
            "spartan": "'Label League Spartan', sans-serif", "newsreader": "'Label Newsreader', serif",
            "bodoni": "'Label Bodoni Moda', serif"}
SHEET_STAGES = ["Reading the PDF", "Recognizing the music", "Styling the notes", "Preparing downloads"]


def validate_style(show_names=True, color_notes=False, font="sans", label_color="auto", note_colors=None):
    if not show_names and not color_notes:
        raise SheetError("Turn on note names, note colors, or both.")
    if font not in FONTS:
        raise SheetError("Choose one of the listed fonts for the note names.")
    if label_color != "auto" and not re.fullmatch(r"#[0-9a-fA-F]{6}", label_color):
        raise SheetError("Choose a label color in #RRGGBB format, or automatic contrast.")
    palette = {**NOTE_COLORS, **(note_colors or {})}
    if set(palette) != set(NOTE_COLORS) or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in palette.values()):
        raise SheetError("Choose a #RRGGBB color for each note, C through B.")
    return {"show_names": show_names, "color_notes": color_notes, "font": font,
            "label_color": label_color, "note_colors": palette}


def rgb(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))


def contrast_color(background):
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in background]
    luminance = sum(c * w for c, w in zip(linear, (0.2126, 0.7152, 0.0722)))
    return (0, 0, 0) if (luminance + 0.05) / 0.05 >= 1.05 / (luminance + 0.05) else (1, 1, 1)


def glyph_ink(glyph, width, height):
    """The recognized head's actual ink, excluding its hole, staff and stem.

    Audiveris run lengths alternate foreground/background, beginning with a
    foreground length (possibly zero). Return normalized vector rectangles;
    no page or note image needs to be rasterized in the exported PDF.
    """
    if glyph is None:
        return []
    table = glyph.find("run-table")
    if table is None:
        return []
    left, top = float(glyph.get("left")), float(glyph.get("top"))
    vertical = table.get("orientation") == "VERTICAL"
    rectangles = []
    for index, column in enumerate(table.findall("runs")):
        offset = 0
        for i, length in enumerate(map(int, (column.text or "").split())):
            if i % 2 == 0 and length:
                if vertical:
                    box = (left + index, top + offset, left + index + 1, top + offset + length)
                else:
                    box = (left + offset, top + index, left + offset + length, top + index + 1)
                rectangles.append([box[0] / width, box[1] / height, box[2] / width, box[3] / height])
            offset += length
    return rectangles


def vector_head(drawings, box):
    """The PDF's own filled notehead path inside `box`, or None (scans, font glyphs, ambiguous art).

    Redrawing this exact path in color looks native: no original black edge shows
    around it. A lighter fill painted later over the head (a white hole) would be
    hidden by the redraw, so such heads use the ink fallback instead.
    """
    def fits(r):
        return (0.5 * box.width <= r.width <= 1.6 * box.width and 0.5 * box.height <= r.height <= 1.6 * box.height
                and (r & box).get_area() > 0.6 * r.get_area())

    dark = [d for d in drawings if d.get("fill") is not None and sum(d["fill"]) < 1.5 and fits(d["rect"])]
    if not dark:
        return None
    head = max(dark, key=lambda d: (d["rect"] & box).get_area())
    covered = any(d["seqno"] > head["seqno"] and d.get("fill") not in (None, head["fill"])
                  and d["rect"].intersects(head["rect"]) for d in drawings)
    return None if covered else head


def draw_path(shape, path):
    """Redraw a get_drawings() path; its points are already in unrotated page space."""
    for kind, *args in path["items"]:
        if kind == "l":
            shape.draw_line(*args)
        elif kind == "c":
            shape.draw_bezier(*args)
        elif kind == "re":
            shape.draw_rect(args[0])
        elif kind == "qu":
            shape.draw_quad(args[0])


AI_DPI = 300  # page render size for the AI mask; typical scan resolution


def ai_model():
    """oemer's notehead segmentation model, or None when it isn't installed."""
    spec = importlib.util.find_spec("oemer")
    if not spec:
        return None
    model = Path(spec.submodule_search_locations[0]) / "checkpoints/seg_net"
    return model if (model / "model.onnx").is_file() else None


def notehead_mask(image_path):
    """True where the AI sees notehead ink, at the image's own size."""
    import cv2
    from oemer.inference import inference
    with contextlib.redirect_stdout(io.StringIO()):  # oemer prints batch progress
        classes, _ = inference(str(ai_model()), str(image_path))
    height, width = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE).shape
    return cv2.resize((classes == 2).astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST) > 0


def ai_recolor(page, notes, palette, folder):
    """Recolor the page's own notehead pixels found by the AI; returns the indexes of notes it colored.

    Works on any page (scans, image-only PDFs, font noteheads). Pixels keep their
    original darkness, blended toward the note color, so edges stay soft and native.
    """
    import cv2
    pix = page.get_pixmap(dpi=AI_DPI, alpha=False)
    image = folder / f"page-{page.number + 1}.png"
    pix.save(image)
    pixels = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
    ink = 1 - pixels.min(axis=2) / 255
    # The mask comes from a downscaled page; grow it a pixel to cover anti-aliased edges.
    mask = cv2.dilate(notehead_mask(image).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    overlay, done = np.zeros((pix.h, pix.w, 4), np.uint8), set()
    for i, item in enumerate(notes):
        x0, y0 = int(item["box"][0] * pix.w) - 2, int(item["box"][1] * pix.h) - 2
        x1, y1 = int(item["box"][2] * pix.w) + 3, int(item["box"][3] * pix.h) + 3
        x0, y0 = max(x0, 0), max(y0, 0)
        heads = mask[y0:y1, x0:x1] & (ink[y0:y1, x0:x1] > 0.08)
        if heads.sum() < 0.15 * (x1 - x0) * (y1 - y0):  # the AI missed this head
            continue
        color = np.array([int(palette[item["step"]][k:k + 2], 16) for k in (1, 3, 5)])
        dark = ink[y0:y1, x0:x1][heads][:, None]
        region = overlay[y0:y1, x0:x1]
        region[heads, :3] = (dark * color + (1 - dark) * 255).round()
        region[heads, 3] = 255
        done.add(i)
    if done:
        layer = pymupdf.Pixmap(pymupdf.csRGB, pix.w, pix.h, overlay.tobytes(), True)
        # The render is upright as displayed; place it in unrotated space, turned with the page.
        page.insert_image(page.rect * page.derotation_matrix, stream=layer.tobytes("png"),
                          overlay=True, rotate=page.rotation)
    return done


TRACE_DPI = 600  # high enough that traced curves follow the scan's real shapes
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


def image_to_pdf(image, output):
    """A sheet photo or scan as a one-page PDF, A4 wide, keeping the picture's aspect.

    Images rarely carry a trustworthy DPI, and a 72-dpi guess makes pages meters
    wide, so the page size is fixed to sheet-music paper width instead.
    """
    try:
        with pymupdf.open(image) as picture, pymupdf.open() as pdf:
            width, height = picture[0].rect.width, picture[0].rect.height
            page = pdf.new_page(width=595, height=595 * height / width)
            page.insert_image(page.rect, filename=str(image))
            pdf.save(output, deflate=True)
    except Exception as exc:
        raise SheetError("That image could not be read. Try a PNG or JPG export.") from exc


def tracer_command():
    return shutil.which("potrace")


def is_vector_page(page):
    return not page.get_images() and bool(page.get_drawings() or page.get_text().strip())


def trace_page(page, folder):
    """Clean the page's ink and trace it into vector curves at the page's displayed size."""
    import cv2
    pix = page.get_pixmap(dpi=TRACE_DPI, colorspace=pymupdf.csGRAY, alpha=False)
    gray = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w)
    # Even out uneven lighting from phone photos, then pick the ink/paper cut automatically.
    # The paper estimate's window must be wider than any ink shape (heads are ~50 px
    # at 600 dpi), or the shape itself is taken for shadowed paper and erased.
    paper = cv2.GaussianBlur(cv2.dilate(gray, np.ones((121, 121), np.uint8)), (0, 0), 35)
    flat = cv2.divide(gray, paper, scale=255)
    # A light blur rounds off the scan's pixel steps (more, sigma 2.5+, erases thin staff
    # lines). Cut halfway between this page's ink and paper: 128 for a crisp black scan,
    # higher for a photo whose ink is dark gray, so faint thin lines survive.
    smooth = cv2.GaussianBlur(flat, (0, 0), 1.5)
    darkest = np.percentile(smooth, 0.5)
    ink = (smooth < (float(darkest) + 255) / 2).astype(np.uint8) * 255
    bitmap = folder / f"page-{page.number + 1}.pbm"
    cv2.imwrite(str(bitmap), 255 - ink)  # potrace traces black pixels
    traced = bitmap.with_suffix(".pdf")
    # -t drops dust specks; -O 0.05 keeps curves close to the ink where stems and staff
    # lines meet heads; -r keeps the page's physical size.
    done = subprocess.run([tracer_command(), "-b", "pdf", "-t", "12", "-a", "1", "-O", "0.05",
                           "-r", str(TRACE_DPI),
                           "-o", str(traced), str(bitmap)], capture_output=True, text=True, timeout=600)
    if done.returncode:
        raise SheetError("A page could not be converted to vector form. Try a clearer scan.")
    return traced


def clean_pdf(source, output, progress=lambda detail: None):
    """A vector PDF of the sheet: scanned pages traced into crisp curves, vector pages kept.

    Ink shapes, layout and page size stay as in the original; only paper tone,
    noise and blur are removed, so the sheet stays sharp at any zoom.
    """
    if not tracer_command():
        raise SheetError("Clean PDF needs potrace. Install it with Homebrew, then restart the app (see README.md).")
    traced_pages = 0
    with pymupdf.open(source) as pdf, pymupdf.open() as out, tempfile.TemporaryDirectory() as scratch:
        for page in pdf:
            if is_vector_page(page):
                out.insert_pdf(pdf, from_page=page.number, to_page=page.number)
                continue
            progress(f"Tracing page {page.number + 1} of {len(pdf)}")
            with pymupdf.open(trace_page(page, Path(scratch))) as traced:
                target = out.new_page(width=page.rect.width, height=page.rect.height)
                target.show_pdf_page(target.rect, traced, 0)
            traced_pages += 1
        out.set_metadata(pdf.metadata)
        out.save(output, garbage=3, deflate=True)
    return traced_pages


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


# Off by default in Audiveris: small noteheads and beams, i.e. grace notes (playable
# ornament notes). Bump RECOGNITION_VERSION when recognition settings change, so
# cached readings made without them are redone.
SMALL_NOTES = ("-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true",
               "-constant", "org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true")
RECOGNITION_VERSION = 2
AUDIVERIS_MAX_AREA = 20_000_000 * (72 / 300) ** 2  # its 20-megapixel page limit at 300 dpi, in pt²


def recognition_copy(path, folder):
    """The PDF Audiveris should read: the original, or an A4-sized copy when pages are oversized.

    Audiveris renders PDFs at 300 dpi and drops any page over 20 megapixels (about A3).
    Exports that map 1 px to 1 pt make pages meters wide. Positions it returns are
    page-relative, so labels from the copy still land on the original pages.
    """
    with pymupdf.open(path) as pdf:
        if all(p.rect.width * p.rect.height <= AUDIVERIS_MAX_AREA for p in pdf):
            return path
        with pymupdf.open() as copy:
            for page in pdf:
                k = min(1, 842 / max(page.rect.width, page.rect.height))
                target = copy.new_page(width=page.rect.width * k, height=page.rect.height * k)
                target.show_pdf_page(target.rect, pdf, page.number)
            copy.save(folder / "recognition-source.pdf", garbage=3, deflate=True)
    return folder / "recognition-source.pdf"


def recognize(path, folder, progress=lambda detail: None):
    command = audiveris_command()
    if not command:
        raise SheetError("PDF recognition needs Audiveris. Install it, then restart the app (see README.md).")
    readable = recognition_copy(path, folder)
    if readable != path:
        progress("Pages are oversized; reading an A4-sized copy")
    path = readable
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
        options = list(SMALL_NOTES) + (["-constant", "org.audiveris.omr.sheet.grid.LinesRetriever.minStaffLength=12"]
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
    if "Too large image" in log:
        raise SheetError("The pages are too large for music recognition, even at A4 size. "
                         "Try exporting the sheet at a normal paper size.")
    raise SheetError("Music recognition could not complete. Try a different PDF export or scan; "
                     "technical details are saved in recognition.log.")


def note_positions(book, page_count, skipped=None):
    """Read original raster coordinates and written pitch from Audiveris's .omr.

    Pitch is a diatonic staff position, positive downwards from the middle line.
    A clef's reference pitch makes this work for clef changes and ledger notes,
    including C clefs. Octave transpositions do not change the letter name.

    When a line's clef was not recognized, the clef that staff (same position in the
    line, e.g. the left hand) ended the previous line with still applies, as in printed
    music. Notes with no clef to go on are left unlabeled and counted in `skipped`.
    """
    pages, carried, missing = {}, {}, 0
    references = {"TREBLE": 4, "BASS": 3, "BARITONE": 3, "ALTO": 0,
                  "TENOR": 0, "MEZZO_SOPRANO": 0, "SOPRANO": 0}
    with zipfile.ZipFile(book) as archive:
        sheets = [m for m in map(lambda n: re.fullmatch(r"sheet#(\d+)/sheet#\1.xml", n), archive.namelist()) if m]
        for match in sorted(sheets, key=lambda m: int(m[1])):  # page order, so clefs carry forward
            filename, index = match[0], int(match[1]) - 1
            root = ET.fromstring(archive.read(filename))
            picture = root.find("picture")
            if picture is None:
                raise SheetError(f"Recognition did not save page {index + 1}'s dimensions.")
            width, height = int(picture.get("width")), int(picture.get("height"))
            if width <= 0 or height <= 0:
                raise SheetError("Recognition returned invalid page dimensions.")
            notes, seen = [], set()
            glyphs = {g.get("id"): g for g in root.iter("glyph")}
            for system in root.iter("system"):
                staves = list(dict.fromkeys(staff.get("id") for staff in system.iter("staff")))
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
                    position = staves.index(head.get("staff")) if head.get("staff") in staves else None
                    symbol = prior[-1] if prior else carried.get(position)
                    if symbol is None:
                        missing += 1
                        continue
                    step = "cdefgab"[(references[symbol.get("kind")] + round(float(symbol.get("pitch")))
                                      - round(float(head.get("pitch")))) % 7]
                    location = (x, y, w, h)
                    if location in seen:  # shared heads in multiple voices need only one label
                        continue
                    seen.add(location)
                    notes.append({"box": [x / width, y / height, (x + w) / width, (y + h) / height],
                                  "step": step, "filled": "BLACK" in head.get("shape", ""),
                                  "ink": glyph_ink(glyphs.get(head.get("glyph")), width, height)})
                for position, staff in enumerate(staves):
                    if clefs.get(staff):
                        carried[position] = clefs[staff][-1][1]
            pages[index] = notes
    if skipped is not None:
        skipped.append(missing)
    if set(pages) != set(range(page_count)):
        raise SheetError("Recognition did not return positions for every page. No partial PDF was created.")
    if not any(pages.values()):
        raise SheetError("No pitched notes were recognized in this sheet.")
    return [pages[i] for i in range(page_count)]


def annotate_pdf(source, output, positions, naming, *, show_names=True, color_notes=False,
                 font="sans", label_color="auto", note_colors=None, method="vector",
                 progress=lambda detail: None):
    """Overlay names and/or colored head ink without replacing original pages.

    method "vector" recolors the PDF's own head shapes; "ai" recolors the page's
    head pixels found by a local AI model (for scans and unusual PDFs).
    """
    if naming not in NAMING:
        raise SheetError("Choose letter names or fixed-Do solfège.")
    if method not in ("vector", "ai"):
        raise SheetError("Choose the standard or AI coloring method.")
    use_ai = method == "ai" and color_notes
    if use_ai and not ai_model():
        raise SheetError("AI coloring needs the oemer model. Install it, then restart the app (see README.md).")
    style = validate_style(show_names, color_notes, font, label_color, note_colors)
    font_file = str(FONTS[font]) if isinstance(FONTS[font], Path) else None
    fontname = font if font_file else FONTS[font]
    text_font = pymupdf.Font(fontfile=font_file) if font_file else pymupdf.Font(fontname)
    count = 0
    with pymupdf.open(source) as pdf, tempfile.TemporaryDirectory() as scratch:
        if len(pdf) != len(positions):
            raise SheetError("The recognized pages do not match the uploaded PDF.")
        for page, notes in zip(pdf, positions):
            drawings = page.get_drawings() if color_notes else []
            ai_done = set()
            if use_ai:
                progress(f"AI coloring page {page.number + 1} of {len(pdf)}")
                ai_done = ai_recolor(page, notes, style["note_colors"], Path(scratch))
            shape = page.new_shape()

            def page_box(normalized):
                a, b, c, d = normalized
                return pymupdf.Rect(a * page.rect.width, b * page.rect.height,
                                    c * page.rect.width, d * page.rect.height)

            for index, item in enumerate(notes):
                box = page_box(item["box"])
                head_color = rgb(style["note_colors"][item["step"]]) if color_notes else (0, 0, 0)
                head = vector_head(drawings, box * page.derotation_matrix) if color_notes else None
                if index in ai_done:
                    pass
                elif head:
                    draw_path(shape, head)
                    shape.finish(color=None, fill=head_color, width=0,
                                 even_odd=head.get("even_odd") or False, closePath=head.get("closePath") or False)
                elif color_notes:
                    if not item.get("ink"):
                        raise SheetError("The shape of a notehead is missing. Upload the sheet again to recognize it.")
                    for ink in item["ink"]:
                        clipped = page_box(ink) & box
                        if not clipped.is_empty:
                            shape.draw_rect(clipped * page.derotation_matrix)
                    shape.finish(color=None, fill=head_color, width=0)
                count += 1
                if not show_names:
                    continue
                name = NAMING[naming][item["step"]]
                # Font metrics center the visible letters inside the head. A small
                # horizontal stretch keeps two/three-letter names tall enough to read.
                size = box.height * (0.72 if item["filled"] else 0.55)
                text_width = text_font.text_length(name, fontsize=size)
                available = box.width * (0.76 if item["filled"] else 0.57)
                stretch = min(1.0, available / text_width)
                start = pymupdf.Point((box.x0 + box.x1 - text_width * stretch) / 2,
                                     (box.y0 + box.y1) / 2 + size * 0.36)
                start = start * page.derotation_matrix
                # The scale is applied in unrotated PDF coordinates.
                scale = pymupdf.Matrix(stretch, 1) if page.rotation in (0, 180) else pymupdf.Matrix(1, stretch)
                text_color = (contrast_color(head_color) if item["filled"] else (0, 0, 0)) if label_color == "auto" else rgb(label_color)
                shape.insert_text(start, name, fontsize=size, fontname=fontname, fontfile=font_file,
                                  color=text_color,
                                  rotate=page.rotation, morph=(start, scale))
            shape.commit(overlay=True)
        if font_file and show_names:
            pdf.subset_fonts()  # keep only the letters used (Do, Re, …), not the whole font
        # garbage=3 merges the per-page copies of an embedded font; built-in fonts need none.
        pdf.save(output, garbage=3 if font_file else 0, deflate=True)
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
