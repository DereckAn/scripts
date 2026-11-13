"""Independent names/colors, font embedding, and hollow-note ink preservation."""
from pathlib import Path
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET

import pymupdf

from sheet_labels import SheetError, annotate_pdf, contrast_color, glyph_ink, rgb, validate_style


class NoteStyleTests(unittest.TestCase):
    def fixture(self, folder):
        source = folder / 'original.pdf'
        boxes = [pymupdf.Rect(40, 70, 80, 100), pymupdf.Rect(140, 70, 180, 100),
                 pymupdf.Rect(220, 130, 260, 160)]
        inner = pymupdf.Rect(146, 76, 174, 94)
        with pymupdf.open() as doc:
            page = doc.new_page(width=300, height=200)
            page.insert_text((20, 25), 'Original sheet')
            for box in boxes:
                page.draw_rect(box, color=None, fill=(0, 0, 0))
            page.draw_rect(inner, color=None, fill=(1, 1, 1))
            page.draw_line((20, 85), (280, 85), color=(0, 0, 0))
            doc.save(source)

        def normalized(rect):
            return [rect.x0 / 300, rect.y0 / 200, rect.x1 / 300, rect.y1 / 200]

        ring = [pymupdf.Rect(140, 70, 180, 76), pymupdf.Rect(140, 94, 180, 100),
                pymupdf.Rect(140, 76, 146, 94), pymupdf.Rect(174, 76, 180, 94)]
        notes = [{'step': step, 'filled': filled, 'box': normalized(box),
                  'ink': [normalized(r) for r in (ring if not filled else [box])]}
                 for box, step, filled in zip(boxes, ('c', 'd', 'c'), (True, False, True))]
        return source, [notes]

    def test_run_length_masks_keep_the_hole_and_both_orientations(self):
        vertical = ET.fromstring('''<glyph left="10" top="20"><run-table orientation="VERTICAL">
          <runs>4</runs><runs>1 2 1</runs><runs>1 2 1</runs><runs>4</runs>
        </run-table></glyph>''')
        horizontal = ET.fromstring('''<glyph left="10" top="20"><run-table orientation="HORIZONTAL">
          <runs>4</runs><runs>1 2 1</runs><runs>1 2 1</runs><runs>4</runs>
        </run-table></glyph>''')
        for glyph in (vertical, horizontal):
            ink = glyph_ink(glyph, 100, 100)
            self.assertTrue(any(pymupdf.Rect(r).contains(pymupdf.Point(.105, .225)) for r in ink))
            self.assertFalse(any(pymupdf.Rect(r).contains(pymupdf.Point(.12, .22)) for r in ink))

    def test_colors_only_keep_ring_center_staff_and_original_text(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, positions = self.fixture(folder)
            target = folder / 'colors.pdf'
            annotate_pdf(source, target, positions, 'letters', show_names=False, color_notes=True,
                         note_colors={'c': '#ff0000', 'd': '#00ff00'})
            with pymupdf.open(target) as pdf:
                self.assertEqual(pdf[0].get_text().strip(), 'Original sheet')
                pix = pdf[0].get_pixmap()
                with pymupdf.open(source) as original:
                    original_pixels = original[0].get_pixmap()
                self.assertEqual(pix.pixel(50, 80), (255, 0, 0))
                self.assertEqual(pix.pixel(230, 140), (255, 0, 0), 'Same pitch must share its color')
                self.assertEqual(pix.pixel(142, 80), (0, 255, 0))
                self.assertEqual(pix.pixel(160, 80), (255, 255, 255), 'Hollow center must remain hollow')
                self.assertEqual(pix.pixel(160, 85), original_pixels.pixel(160, 85),
                                 'Staff through the hole must remain unchanged')
                self.assertEqual(pix.pixel(100, 85), original_pixels.pixel(100, 85))
                self.assertFalse(pdf[0].get_images(), 'Recoloring must remain vector-based')

    def test_font_and_custom_text_color_with_and_without_note_colors(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, positions = self.fixture(folder)
            for font, expected in [('sans', 'Helvetica-Bold'), ('serif', 'Times-Bold'), ('mono', 'Courier-Bold'),
                                   ('garamond', 'EBGaramond-Bold'), ('spartan', 'LeagueSpartan-Bold'),
                                   ('newsreader', 'Newsreader16pt-Regular'), ('bodoni', 'BodoniModa-Regular')]:
                for colored in (False, True):
                    target = folder / f'{font}-{colored}.pdf'
                    annotate_pdf(source, target, positions, 'solfege', font=font, color_notes=colored,
                                 label_color='#123456')
                    with pymupdf.open(target) as pdf:
                        spans = [s for block in pdf[0].get_text('dict')['blocks'] if 'lines' in block
                                 for line in block['lines'] for s in line['spans'] if s['text'] in ('Do', 'Re')]
                        self.assertEqual(len(spans), 3)
                        self.assertEqual({s['font'] for s in spans}, {expected})
                        self.assertEqual({s['color'] for s in spans}, {0x123456})
                        if not colored:
                            with pymupdf.open(source) as original:
                                self.assertEqual(original[0].get_drawings(), pdf[0].get_drawings())

    def test_vector_heads_are_recolored_natively_on_rotated_pages(self):
        """No ink is given, so this passes only if the PDF's own head paths are redrawn in place."""
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, positions = folder / 'vector.pdf', []
            with pymupdf.open() as doc:
                for rotation in (0, 90, 180, 270):
                    page = doc.new_page(width=300, height=200)
                    page.set_rotation(rotation)
                    W, H = page.rect.width, page.rect.height
                    filled = pymupdf.Rect(0.2 * W, 0.4 * H, 0.3 * W, 0.55 * H)
                    hollow = pymupdf.Rect(0.6 * W, 0.4 * H, 0.7 * W, 0.55 * H)
                    page.draw_line(pymupdf.Point(0, 0.475 * H) * page.derotation_matrix,
                                   pymupdf.Point(W, 0.475 * H) * page.derotation_matrix)
                    page.draw_oval(filled * page.derotation_matrix, color=None, fill=(0, 0, 0))
                    ring = page.new_shape()
                    ring.draw_oval(hollow * page.derotation_matrix)
                    ring.draw_oval(pymupdf.Rect(hollow.x0 + 0.3 * hollow.width, hollow.y0 + 0.3 * hollow.height,
                                                hollow.x1 - 0.3 * hollow.width, hollow.y1 - 0.3 * hollow.height)
                                   * page.derotation_matrix)
                    ring.finish(color=None, fill=(0, 0, 0), even_odd=True)
                    ring.commit()
                    positions.append([{'step': 'c', 'filled': True, 'box': [.2, .4, .3, .55]},
                                      {'step': 'd', 'filled': False, 'box': [.6, .4, .7, .55]}])
                doc.save(source)
            target = folder / 'colored.pdf'
            annotate_pdf(source, target, positions, 'letters', show_names=False, color_notes=True,
                         note_colors={'c': '#ff0000', 'd': '#00ff00'})
            with pymupdf.open(source) as old, pymupdf.open(target) as new:
                for a, b in zip(old, new):
                    pa, pb = a.get_pixmap(), b.get_pixmap()
                    at = lambda x, y: pb.pixel(int(x * pb.width), int(y * pb.height))
                    self.assertEqual(at(.25, .45), (255, 0, 0), f'filled head, rotation {a.rotation}')
                    self.assertEqual(at(.61, .475), (0, 255, 0), f'ring, rotation {a.rotation}')
                    self.assertEqual(at(.65, .45), pa.pixel(int(.65 * pa.width), int(.45 * pa.height)),
                                     'Hollow center must stay as it was')
                    for x, y in [(.1, .2), (.45, .475), (.9, .8)]:
                        self.assertEqual(at(x, y), pa.pixel(int(x * pa.width), int(y * pa.height)))
                    self.assertFalse(b.get_images(), 'Recoloring must remain vector-based')

    def test_ai_method_recolors_masked_pixels_and_falls_back_per_note(self):
        """A fake mask stands in for the model: it 'sees' only dark pixels on the left half."""
        import numpy as np
        import sheet_labels

        def fake_mask(image_path):
            pix = pymupdf.Pixmap(str(image_path))
            dark = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n).min(axis=2) < 128
            dark[:, pix.w // 2:] = False
            return dark

        with tempfile.TemporaryDirectory() as folder, \
                unittest.mock.patch.object(sheet_labels, 'notehead_mask', fake_mask), \
                unittest.mock.patch.object(sheet_labels, 'ai_model', lambda: Path(folder)):
            folder = Path(folder)
            source, positions = folder / 'scan.pdf', []
            with pymupdf.open() as doc:
                for rotation in (0, 90, 180, 270):
                    page = doc.new_page(width=300, height=200)
                    page.set_rotation(rotation)
                    W, H = page.rect.width, page.rect.height
                    for x in (0.2, 0.6):
                        page.draw_oval(pymupdf.Rect(x * W, .4 * H, (x + .1) * W, .55 * H) * page.derotation_matrix,
                                       color=None, fill=(0, 0, 0))
                    positions.append([{'step': 'c', 'filled': True, 'box': [.2, .4, .3, .55]},
                                      {'step': 'd', 'filled': True, 'box': [.6, .4, .7, .55]}])
                doc.save(source)
            target = folder / 'ai.pdf'
            steps = []
            annotate_pdf(source, target, positions, 'letters', show_names=False, color_notes=True, method='ai',
                         note_colors={'c': '#ff0000', 'd': '#00ff00'}, progress=steps.append)
            self.assertEqual(steps, [f'AI coloring page {i} of 4' for i in range(1, 5)])
            with pymupdf.open(source) as old, pymupdf.open(target) as new:
                for a, b in zip(old, new):
                    pa, pb = a.get_pixmap(dpi=144), b.get_pixmap(dpi=144)
                    at = lambda p, x, y: p.pixel(int(x * p.width), int(y * p.height))
                    self.assertEqual(at(pb, .25, .475), (255, 0, 0), f'AI-colored head, rotation {a.rotation}')
                    self.assertEqual(at(pb, .65, .475), (0, 255, 0), 'Missed head falls back to its vector shape')
                    for x, y in [(.1, .2), (.45, .475), (.9, .8), (.25, .3)]:
                        self.assertEqual(at(pb, x, y), at(pa, x, y), 'Nothing outside the heads may change')
                    self.assertEqual(len(b.get_images()), 1, 'One transparent overlay per page')
            with self.assertRaises(SheetError):
                annotate_pdf(source, target, positions, 'letters', color_notes=True, method='magic')

    def test_automatic_contrast_and_invalid_settings(self):
        self.assertEqual(contrast_color(rgb('#000000')), (1, 1, 1))
        self.assertEqual(contrast_color(rgb('#ffff00')), (0, 0, 0))
        for options in [{'show_names': False, 'color_notes': False}, {'font': 'not-a-font'},
                        {'label_color': 'red'}, {'note_colors': {'c': '#xyzxyz'}},
                        {'note_colors': {'h': '#112233'}}]:
            with self.assertRaises(SheetError):
                validate_style(**options)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source, positions = self.fixture(folder)
            target = folder / 'contrast.pdf'
            annotate_pdf(source, target, positions, 'letters', color_notes=True,
                         note_colors={'c': '#ffff00'})
            with pymupdf.open(target) as pdf:
                spans = [s for block in pdf[0].get_text('dict')['blocks'] if 'lines' in block
                         for line in block['lines'] for s in line['spans'] if s['text'] in ('C', 'D')]
                self.assertEqual({s['color'] for s in spans}, {0})


if __name__ == '__main__':
    unittest.main()
