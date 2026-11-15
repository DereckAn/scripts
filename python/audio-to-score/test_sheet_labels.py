"""Run: .venv/bin/python -m unittest test_sheet_labels"""
import hashlib
import subprocess
import tempfile
import time
import unittest
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pymupdf
from fastapi.testclient import TestClient

import piano
from sheet_labels import SheetError, annotate_pdf, note_positions, pdf_info, recognize


def blank_pdf(path, pages=1, width=595, height=842):
    with pymupdf.open() as pdf:
        for _ in range(pages):
            pdf.new_page(width=width, height=height)
        pdf.save(path)
    return path


class SheetLabelsTests(unittest.TestCase):
    def make_book(self, folder):
        book = folder / 'source.omr'
        xml = '''<sheet><picture width="1000" height="800"/><system>
          <clef kind="TREBLE" pitch="2" staff="1" id="1"><bounds x="0"/></clef>
          <clef kind="BASS" pitch="-2" staff="2" id="2"><bounds x="0"/></clef>
          <clef kind="BASS" pitch="-2" staff="1" id="3"><bounds x="500"/></clef>
          <head pitch="6" shape="NOTEHEAD_BLACK" staff="1"><bounds x="100" y="200" w="30" h="20"/></head>
          <head pitch="4" shape="NOTEHEAD_BLACK" staff="1"><bounds x="100" y="180" w="30" h="20"/></head>
          <head pitch="6" shape="NOTEHEAD_BLACK" staff="1"><bounds x="100" y="200" w="30" h="20"/></head>
          <head pitch="0" shape="WHOLE_NOTE" staff="2"><bounds x="200" y="500" w="40" h="20"/></head>
          <head pitch="0" shape="NOTEHEAD_VOID" staff="1"><bounds x="600" y="200" w="30" h="20"/></head>
        </system></sheet>'''
        root = ET.fromstring(xml)
        glyphs = ET.SubElement(root, 'glyph-index')
        for i, head in enumerate(root.iter('head')):
            bounds = head.find('bounds')
            head.set('glyph', str(i))
            glyph = ET.SubElement(glyphs, 'glyph', id=str(i), left=bounds.get('x'), top=bounds.get('y'))
            table = ET.SubElement(glyph, 'run-table', orientation='VERTICAL',
                                 width=bounds.get('w'), height=bounds.get('h'))
            for x in range(int(bounds.get('w'))):
                hollow = 'BLACK' not in head.get('shape') and 3 <= x < int(bounds.get('w')) - 3
                ET.SubElement(table, 'runs').text = '3 14 3' if hollow else '20'
        with zipfile.ZipFile(book, 'w') as archive:
            archive.writestr('sheet#1/sheet#1.xml', ET.tostring(root))
        return book

    def test_short_ending_staff_retries_the_whole_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = blank_pdf(folder / 'four-pages.pdf', 4)
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(args, 1, 'Sheet #4: No system found', '')
                output = Path(args[args.index('-output') + 1])
                (output / 'complete.mxl').write_bytes(b'fixture')
                return subprocess.CompletedProcess(args, 0, '4 sheets exported', '')

            with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                    patch('sheet_labels.subprocess.run', side_effect=run):
                scores = recognize(source, folder)
            self.assertEqual(len(scores), 1)
            self.assertEqual(len(calls), 2)
            self.assertTrue(all(args[-2:] == ['--', str(source)] for args in calls))
            self.assertTrue(all('-sheets' not in args for args in calls))
            self.assertIn('org.audiveris.omr.sheet.grid.LinesRetriever.minStaffLength=12', calls[1])
            self.assertIn('Short-staff retry', (folder / 'recognition.log').read_text())

    def test_failed_export_never_returns_stale_partial_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'stale.mxl').write_bytes(b'partial')
            with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                    patch('sheet_labels.subprocess.run', return_value=subprocess.CompletedProcess([], 1, 'Export failed', '')) as run:
                with self.assertRaisesRegex(SheetError, 'could not complete'):
                    recognize(blank_pdf(folder / 'source.pdf'), folder)
            self.assertEqual(run.call_count, 1)

    def test_small_svg_pages_retry_at_higher_recognition_resolution(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(args, 1, 'With a too low interline value of 10 pixels', '')
                output = Path(args[args.index('-output') + 1])
                (output / 'source.mxl').write_bytes(b'fixture')
                return subprocess.CompletedProcess(args, 0, 'exported', '')

            with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                    patch('sheet_labels.subprocess.run', side_effect=run):
                recognize(blank_pdf(folder / 'source.pdf'), folder)
            self.assertEqual(len(calls), 2)
            self.assertIn('org.audiveris.omr.image.ImageLoading.pdfResolution=600', calls[1])
            self.assertTrue(all('-sheets' not in args for args in calls))

    def test_pitch_positions_chords_and_clef_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            book = self.make_book(Path(folder))
            pages = note_positions(book, 1)
            self.assertEqual([n['step'] for n in pages[0]], ['c', 'e', 'd', 'd'])
            self.assertEqual([n['filled'] for n in pages[0]], [True, True, False, False])
            self.assertEqual(pages[0][0]['box'], [0.1, 0.25, 0.13, 0.275])
            with self.assertRaisesRegex(SheetError, 'every page'):
                note_positions(book, 2)

    def test_missed_clefs_carry_over_from_the_previous_line(self):
        """Audiveris can miss a line's clef (e.g. an octave bass clef); the staff keeps its clef."""
        def sheet(systems):
            body = ''.join('<system>' + ''.join(f'<staff id="{i}"/>' for i in staves) + clefs + heads + '</system>'
                           for staves, clefs, heads in systems)
            return f'<sheet><picture width="1000" height="800"/>{body}</sheet>'.encode()
        head = '<head pitch="0" shape="NOTEHEAD_BLACK" staff="{}"><bounds x="{}" y="{}" w="30" h="20"/></head>'
        treble, bass = '<clef kind="TREBLE" pitch="2" staff="{}"><bounds x="0"/></clef>', '<clef kind="BASS" pitch="-2" staff="{}"><bounds x="0"/></clef>'
        with tempfile.TemporaryDirectory() as folder:
            book = Path(folder) / 'source.omr'
            with zipfile.ZipFile(book, 'w') as archive:  # page 2 stored first: pages must still be read in order
                archive.writestr('sheet#2/sheet#2.xml', sheet([(('1', '2'), '', head.format(1, 100, 100) + head.format(2, 100, 300))]))
                archive.writestr('sheet#1/sheet#1.xml', sheet([
                    (('1', '2'), treble.format(1) + bass.format(2), head.format(1, 100, 100) + head.format(2, 100, 300)),
                    (('3', '4'), treble.format(3), head.format(3, 200, 500) + head.format(4, 200, 700))]))
            skipped = []
            pages = note_positions(book, 2, skipped)
            # Middle line: B in treble, D in bass; line 2 and page 2 keep each staff's clef.
            self.assertEqual([n['step'] for n in pages[0]], ['b', 'd', 'b', 'd'])
            self.assertEqual([n['step'] for n in pages[1]], ['b', 'd'])
            self.assertEqual(skipped, [0])

            with zipfile.ZipFile(book, 'w') as archive:  # no clef anywhere for the lower staff
                archive.writestr('sheet#1/sheet#1.xml', sheet([
                    (('1', '2'), treble.format(1), head.format(1, 100, 100) + head.format(2, 100, 300))]))
            skipped = []
            pages = note_positions(book, 1, skipped)
            self.assertEqual([n['step'] for n in pages[0]], ['b'], 'Unknown-clef notes are skipped, not fatal')
            self.assertEqual(skipped, [1])

    def test_oversized_pages_are_read_from_an_a4_copy(self):
        from sheet_labels import recognition_copy
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            normal = blank_pdf(folder / 'normal.pdf', 2)
            self.assertEqual(recognition_copy(normal, folder), normal)
            huge = folder / 'huge.pdf'
            with pymupdf.open() as pdf:
                for _ in range(2):  # 1 px = 1 pt exports: ~31 x 44 in, 122 MP at 300 dpi
                    page = pdf.new_page(width=2233, height=3156)
                    page.draw_rect(pymupdf.Rect(1000, 1500, 1200, 1600), color=None, fill=(0, 0, 0))
                pdf.save(huge)
            copy = recognition_copy(huge, folder)
            self.assertNotEqual(copy, huge)
            with pymupdf.open(copy) as pdf:
                self.assertEqual(len(pdf), 2)
                self.assertAlmostEqual(max(pdf[0].rect.width, pdf[0].rect.height), 842, places=1)
                ink = pdf[0].get_drawings()[0]['rect']
                k = 842 / 3156
                self.assertAlmostEqual(ink.x0 / pdf[0].rect.width, 1000 / 2233, places=3, msg='Same relative position')
                self.assertAlmostEqual(ink.y0, 1500 * k, places=1)
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 1, 'Too large image: 122,343,753 pixels', '')

            with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                    patch('sheet_labels.subprocess.run', side_effect=run):
                with self.assertRaisesRegex(SheetError, 'too large'):
                    recognize(huge, folder)
            self.assertEqual(calls[0][-1], str(copy), 'Audiveris reads the A4 copy, not the original')

    def test_invalid_and_encrypted_pdfs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sheet.pdf'
            path.write_bytes(b'not a PDF')
            with self.assertRaises(SheetError):
                pdf_info(path)
            with pymupdf.open() as pdf:
                pdf.new_page()
                pdf.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw='secret', owner_pw='owner')
            with self.assertRaisesRegex(SheetError, 'password'):
                pdf_info(path)

    def test_upload_and_request_validation(self):
        client = TestClient(piano.app)
        invalid = client.post('/api/sheets/source', files={'file': ('bad.pdf', b'invalid', 'application/pdf')})
        self.assertEqual(invalid.status_code, 400)
        with pymupdf.open() as pdf:
            pdf.new_page()
            data = pdf.tobytes()
        upload = client.post('/api/sheets/source', files={'file': ('Practice.pdf', data, 'application/pdf')})
        self.assertEqual(upload.status_code, 200)
        source = upload.json()
        self.assertEqual((source['title'], source['pages']), ('Practice', 1))
        self.assertEqual(client.post('/api/sheets/label', json={'source': source['id'], 'naming': 'invalid'}).status_code, 400)
        self.assertEqual(client.post('/api/sheets/label', json={'source': 'missing'}).status_code, 400)
        for options in [{'show_names': False, 'color_notes': False}, {'font': 'missing'},
                        {'label_color': 'invalid'}, {'note_colors': {'c': 'bad'}}]:
            self.assertEqual(client.post('/api/sheets/label', json={'source': source['id'], **options}).status_code, 400)
        with patch.object(piano, 'audiveris_command', return_value=None):
            self.assertEqual(client.post('/api/sheets/label', json={'source': source['id']}).status_code, 503)

    def test_image_upload_and_clean_pdf_job(self):
        """A photo uploads as a PDF; the clean job traces it to vector and keeps the page."""
        if not piano.tracer_command():
            self.skipTest('potrace is not installed')
        with pymupdf.open() as doc:
            page = doc.new_page(width=300, height=200)
            page.draw_line((20, 100), (280, 100), width=1.2)
            page.draw_oval(pymupdf.Rect(100, 92, 116, 104), color=None, fill=(0, 0, 0))
            png = page.get_pixmap(dpi=300, alpha=False).tobytes('png')
        client = TestClient(piano.app)
        self.assertEqual(client.post('/api/sheets/source', files={'file': ('a.gif', png, 'image/gif')}).status_code, 400)
        upload = client.post('/api/sheets/source', files={'file': ('Phone photo.png', png, 'image/png')})
        self.assertEqual(upload.status_code, 200)
        source = upload.json()
        self.assertEqual((source['title'], source['pages']), ('Phone photo', 1))
        self.assertTrue(source['url'].endswith('.pdf'))
        self.assertEqual(client.post('/api/sheets/clean', json={'source': 'missing'}).status_code, 400)
        with patch.object(piano, 'tracer_command', return_value=None):
            self.assertEqual(client.post('/api/sheets/clean', json={'source': source['id']}).status_code, 503)
        job = client.post('/api/sheets/clean', json={'source': source['id']}).json()['job']
        for _ in range(100):
            status = client.get(f'/api/jobs/{job}').json()
            if status['state'] not in ('queued', 'running'):
                break
            time.sleep(0.1)
        self.assertEqual(status['state'], 'done', status.get('error'))
        self.assertIn('1 scanned page traced', status['result']['info'])
        clean = piano.WORK / urllib.parse.unquote(status['result']['downloads'][0]['url'].split('/files/', 1)[1])
        with pymupdf.open(clean) as pdf:
            self.assertEqual(pdf[0].rect.width, 595)
            self.assertAlmostEqual(pdf[0].rect.height, 595 * 200 / 300, delta=1)
            self.assertFalse(pdf[0].get_images(), 'Clean PDF must be vector only')
            pix = pdf[0].get_pixmap(dpi=72, alpha=False)
            dark = lambda x, y: pix.pixel(int(x * pix.width), int(y * pix.height))[0] < 100
            self.assertTrue(dark(108 / 300, 98 / 200), 'Notehead kept')
            self.assertTrue(dark(60 / 300, 100 / 200), 'Staff line kept')
            self.assertFalse(dark(200 / 300, 60 / 200), 'Paper stays white')

    def test_converted_score_gets_names_and_colors(self):
        """The audio path: a rendered score is restyled from its own MusicXML, screen and PDF alike."""
        from music21 import note, stream
        folder = Path(tempfile.mkdtemp(prefix='piano-test-', dir=piano.WORK))
        part = stream.Part([note.Note('C4', quarterLength=1), note.Note('D4', quarterLength=2), note.Note('F#4', quarterLength=1)])
        part.write('musicxml', fp=folder / 'score.musicxml')
        client = TestClient(piano.app)
        for bad in ('../x', 'piano-missing'):
            self.assertEqual(client.post('/api/scores/style', json={'score': bad}).status_code, 400)
        self.assertEqual(client.post('/api/scores/style', json={'score': folder.name, 'show_names': True,
                                                               'font': 'nope'}).status_code, 400)
        d = client.post('/api/scores/style', json={'score': folder.name, 'naming': 'solfege', 'show_names': True,
                                                    'color_notes': True, 'font': 'spartan',
                                                    'note_colors': {'c': '#ff0000'}}).json()
        self.assertEqual(d['player'].count('class="note-name"'), 3)
        self.assertIn('fill="#ff0000"', d['player'])
        self.assertIn('>Fa</text>', d['player'], 'F-sharp is labeled by its written letter')
        with pymupdf.open(piano.WORK / urllib.parse.unquote(d['pdf']['url'].split('/files/', 1)[1])) as pdf:
            self.assertEqual([w for w in pdf[0].get_text().split() if w in ('Do', 'Re', 'Fa')], ['Do', 'Re', 'Fa'])
            self.assertTrue(any('LeagueSpartan' in f[3] for f in pdf[0].get_fonts()), 'Chosen font is embedded')
        plain = client.post('/api/scores/style', json={'score': folder.name}).json()
        self.assertNotIn('note-name', plain['player'])
        self.assertEqual(plain['pdf']['name'], 'score.pdf')
        self.assertFalse(list(folder.glob('score-*.mid')), 'Restyling leaves no stray MIDI files')

    def test_uploaded_sheet_opens_in_the_studio_without_audio(self):
        """Recognition is faked with a small two-staff piece; engraving and audio are real."""
        from music21 import clef, key, layout, meter, note, stream
        folder = Path(tempfile.mkdtemp(dir=piano.WORK))
        rh, lh = stream.PartStaff(), stream.PartStaff()
        rh.append([clef.TrebleClef(), key.KeySignature(-1), meter.TimeSignature('3/4')] + [note.Note(p) for p in ('F4', 'A4', 'C5')])
        lh.append([clef.BassClef(), key.KeySignature(-1), meter.TimeSignature('3/4'), note.Note('F2', quarterLength=3)])
        piece = stream.Score([rh, lh]); piece.insert(0, layout.StaffGroup([rh, lh], symbol='brace'))
        mxl = Path(piece.write('mxl', fp=folder / 'recognized.mxl'))
        client = TestClient(piano.app)
        self.assertEqual(client.post('/api/sheets/play', json={'source': 'missing'}).status_code, 400)
        source = client.post('/api/sheets/source', files={'file': ('Waltz.pdf', open(blank_pdf(folder / 'w.pdf'), 'rb'), 'application/pdf')}).json()
        with patch.object(piano, 'sheet_recognition', return_value=(folder, [mxl])), \
                patch.object(piano, 'audiveris_command', return_value='/fake/audiveris'):
            job = client.post('/api/sheets/play', json={'source': source['id']}).json()['job']
            for _ in range(300):
                status = client.get(f'/api/jobs/{job}').json()
                if status['state'] not in ('queued', 'running'):
                    break
                time.sleep(0.2)
        self.assertEqual(status['state'], 'done', status.get('error'))
        r = status['result']
        self.assertEqual((r['engine'], r['title'], r['meter'], r['key']), ('Sheet', 'Waltz', '3/4', 'F major'))
        self.assertIsNone(r['studio']['original'], 'No recording to compare with')
        self.assertEqual(sorted((n[2], n[3]) for n in r['studio']['notes']), [(41, 'l'), (65, 'r'), (69, 'r'), (72, 'r')])
        self.assertEqual([d['label'] for d in r['downloads']], ['PDF', 'MusicXML', 'Two-hand MIDI', 'Score audio (MP3)'])
        self.assertTrue(r['score'].startswith('piano-'), 'Note names and colors can restyle it')
        self.assertEqual(client.post('/api/scores/style', json={'score': r['score'], 'show_names': True}).status_code, 200)

    def test_clean_pdf_keeps_vector_pages_untouched(self):
        if not piano.tracer_command():
            self.skipTest('potrace is not installed')
        from sheet_labels import clean_pdf
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'mixed.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page(width=300, height=200)
                page.insert_text((20, 40), 'Engraved title')
                page.draw_line((20, 100), (280, 100))
                doc.save(source)
            self.assertEqual(clean_pdf(source, folder / 'out.pdf'), 0)
            with pymupdf.open(source) as a, pymupdf.open(folder / 'out.pdf') as b:
                self.assertEqual(b[0].get_text(), a[0].get_text())
                self.assertEqual(b[0].get_drawings(), a[0].get_drawings())

    def test_overlay_preserves_original_pages_and_only_changes_noteheads(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'original.pdf'
            positions = []
            with pymupdf.open() as original:
                original.set_metadata({'title': 'Original score', 'author': 'Pianist'})
                for rotation in (0, 90, 180, 270):
                    page = original.new_page(width=320, height=260)
                    page.insert_text((25, 40), 'Original title and markings')
                    page.draw_line((30, 80), (280, 80))
                    page.set_cropbox(pymupdf.Rect(10, 20, 310, 240))
                    page.set_rotation(rotation)
                    items = [
                        {'box': [0.3, 0.4, 0.38, 0.46], 'step': 'c', 'filled': True},
                        {'box': [0.6, 0.4, 0.68, 0.46], 'step': 'g', 'filled': False},
                    ]
                    for item in items:
                        a, b, c, d = item['box']
                        box = pymupdf.Rect(a*page.rect.width, b*page.rect.height, c*page.rect.width, d*page.rect.height)
                        page.draw_oval(box * page.derotation_matrix, fill=(0, 0, 0) if item['filled'] else None)
                    positions.append(items)
                original.save(source)
            before = hashlib.sha256(source.read_bytes()).digest()
            for naming, labels in [('letters', ['C', 'G']), ('solfege', ['Do', 'Sol'])]:
                target = folder / f'{naming}.pdf'
                self.assertEqual(annotate_pdf(source, target, positions, naming), 8)
                with pymupdf.open(source) as old, pymupdf.open(target) as new:
                    self.assertEqual(len(old), len(new))
                    self.assertEqual(old.metadata, new.metadata)
                    for i, (a, b) in enumerate(zip(old, new)):
                        for attr in ('rect', 'cropbox', 'mediabox', 'rotation'):
                            self.assertEqual(getattr(a, attr), getattr(b, attr))
                        for label in labels:
                            self.assertIn(label, b.get_text())
                        self.assertIn('Original title and markings', b.get_text())
                        pa, pb = a.get_pixmap(dpi=144), b.get_pixmap(dpi=144)
                        diff = np.any(np.frombuffer(pa.samples, dtype=np.uint8).reshape(pa.height, pa.width, 3)
                                      != np.frombuffer(pb.samples, dtype=np.uint8).reshape(pb.height, pb.width, 3), axis=2)
                        allowed = np.zeros_like(diff)
                        for item in positions[i]:
                            x0, y0, x1, y1 = item['box']
                            allowed[int(y0*pa.height)-2:int(y1*pa.height)+3,
                                    int(x0*pa.width)-2:int(x1*pa.width)+3] = True
                        self.assertGreater(int(diff.sum()), 0)
                        self.assertFalse(np.any(diff & ~allowed), f'Artwork changed outside heads at rotation {a.rotation}')
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())

    def test_label_api_annotates_without_score_reconstruction(self):
        client = TestClient(piano.app)
        with pymupdf.open() as doc:
            doc.new_page(width=300, height=240).insert_text((20, 30), 'Original score')
            data = doc.tobytes()
        upload = client.post('/api/sheets/source', files={'file': ('Score.pdf', data, 'application/pdf')}).json()

        def recognized(path, folder, progress):
            self.make_book(folder)
            score = folder / 'source.mxl'
            score.write_bytes(b'not used for rendering')
            return [score]

        with patch.object(piano, 'audiveris_command', return_value='/fake/audiveris'), \
                patch.object(piano, 'recognize', side_effect=recognized) as recognize_call, \
                patch.object(piano, 'render', side_effect=AssertionError('Must not reconstruct a PDF')):
            for options in [{'naming': 'letters'}, {'naming': 'solfege', 'font': 'mono', 'label_color': '#0088ff'},
                            {'show_names': False, 'color_notes': True},
                            {'naming': 'solfege', 'show_names': True, 'color_notes': True, 'font': 'serif'}]:
                jobid = client.post('/api/sheets/label', json={'source': upload['id'], **options}).json()['job']
                for _ in range(100):
                    job = client.get('/api/jobs/'+jobid).json()
                    if job['state'] not in ('queued', 'running'):
                        break
                    time.sleep(0.02)
                self.assertEqual(job['state'], 'done', job)
                result = job['result']
                self.assertEqual((result['pages'], result['notes']), (1, 4))
                self.assertIn('<img', result['player'])
                output = client.get(result['downloads'][0]['url'])
                with pymupdf.open(stream=output.content, filetype='pdf') as pdf:
                    self.assertEqual(pdf[0].rect, pymupdf.Rect(0, 0, 300, 240))
                    self.assertIn('Original score', pdf[0].get_text())
            self.assertEqual(recognize_call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
