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
            # One retry without the grace-note switch (it can make Audiveris fail), then give up.
            self.assertEqual(run.call_count, 2)
            self.assertNotIn('org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true', run.call_args_list[1][0][0])

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

    def test_tempo_words_become_playback_speed(self):
        words = {1: 'Moderato e molto rubato', 3: 'rit.', 6: 'a tempo', 8: '138 Presto', 9: 'marcato'}
        bars = ''.join(f'<measure number="{i}">'
                       + (f'<direction><direction-type><words>{words[i]}</words></direction-type></direction>' if i in words else '')
                       + ('<sound tempo="70"/>' if i == 10 else '')
                       + '<note><rest/><duration>4</duration></note></measure>' for i in range(1, 11))
        with tempfile.TemporaryDirectory() as folder:
            xml = Path(folder) / 'score.musicxml'
            xml.write_text(f'<score-partwise><part id="P1">{bars}</part><part id="P2">{bars}</part></score-partwise>')
            tree = ET.parse(xml)
            steps = piano.tempo_from_words(tree.getroot())
            tree.write(xml)
            # Moderato; rit. slows over 3 bars and holds; a tempo restores; "138" is a bar number, not a tempo.
            self.assertEqual([(i + 1, bpm) for i, bpm in steps], [(1, 108), (3, 99), (4, 92), (5, 84), (6, 108), (8, 180)])
            root = ET.parse(xml).getroot()
            first = root.find('part').findall('measure')
            self.assertEqual(first[2][0].tag, 'sound', 'Tempo goes before the bar\'s notes')
            self.assertEqual(len(root.findall('part')[1].findall('.//sound')), 1, 'Only the first part gets new tempos')
            self.assertEqual(first[9].find('sound').get('tempo'), '70', 'A tempo already in the file is kept')

    def test_grace_note_reading_falls_back_when_it_breaks_rhythm(self):
        """On some sheets Audiveris takes normal chords for grace (small) chords and loses bars."""
        small = 'org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true'
        for log, expected_calls in [('WARN StackRhythm error processing MeasureStack#1 java.lang.IllegalStateException: '
                                     'Attempt to setVoice() on SmallChordInter#7960', 2), ('all good', 1)]:
            with tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                calls = []

                def run(args, **kwargs):
                    calls.append(args)
                    output = Path(args[args.index('-output') + 1])
                    (output / f'reading-{len(calls)}.mxl').write_bytes(b'x')
                    return subprocess.CompletedProcess(args, 0, log if small in args else 'fine', '')

                with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                        patch('sheet_labels.subprocess.run', side_effect=run):
                    scores = recognize(blank_pdf(folder / 'source.pdf'), folder)
                self.assertEqual(len(calls), expected_calls)
                self.assertIn(small, calls[0], 'Grace notes are tried first')
                if expected_calls == 2:
                    self.assertNotIn(small, calls[1])
                    self.assertEqual(scores[0].name, 'reading-2.mxl', 'The reading without grace notes is kept')
                    self.assertIn('without grace notes', (folder / 'recognition.log').read_text())

    def test_broken_readings_are_compared_with_a_plain_reading(self):
        """If many bars of the grace-note reading are broken, a plain reading is made too and
        kept only when it is clearly better after the app's fixes."""
        from sheet_labels import CLEARLY_FEWER, broken_bars

        def mxl(path, bad_bars, bars=4):
            note = '<note><pitch><step>C</step><octave>5</octave></pitch><duration>{}</duration><voice>1</voice><type>whole</type></note>'
            body = ''.join(f'<measure number="{i + 1}">' + ('<attributes><divisions>1</divisions><time><beats>4</beats>'
                           '<beat-type>4</beat-type></time></attributes>' if i == 0 else '')
                           + note.format(5 if 0 < i <= bad_bars else 4) + '</measure>' for i in range(bars))
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
                z.writestr('score.xml', f'<score-partwise><part id="P1">{body}</part></score-partwise>')
            return path

        small = 'org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true'
        for second_ok in (True, False):
            with tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                calls = []

                def run(args, **kwargs):
                    calls.append(args)
                    output = Path(args[args.index('-output') + 1])
                    if small in args:
                        mxl(output / 'grace.mxl', 2)  # 2 of 4 bars run past the bar line
                    elif second_ok:
                        mxl(output / 'plain.mxl', 0)
                    else:
                        return subprocess.CompletedProcess(args, 1, 'crashed', '')
                    return subprocess.CompletedProcess(args, 0, '', '')

                with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                        patch('sheet_labels.subprocess.run', side_effect=run):
                    scores = recognize(blank_pdf(folder / 'source.pdf'), folder)
                self.assertEqual(len(calls), 2)
                self.assertEqual(scores[0].name, 'grace.mxl', 'The grace-note reading stays the main result')
                self.assertEqual((folder / 'alternative.json').is_file(), second_ok)
                if second_ok:
                    self.assertEqual(broken_bars(scores[0]), (2, 4))
                    picked = piano.pick_reading(folder / 'source.pdf', scores, folder)
                    self.assertEqual(picked[0].name, 'plain.mxl', f'{CLEARLY_FEWER}+ fewer broken bars: plain is kept')

        with tempfile.TemporaryDirectory() as folder:  # only 1 fewer: keep the grace notes
            folder = Path(folder)
            grace, plain = mxl(folder / 'grace.mxl', 1), mxl(folder / 'plain.mxl', 0)
            (folder / 'alternative.json').write_text('["plain.mxl"]')
            self.assertEqual(piano.pick_reading(blank_pdf(folder / 's.pdf'), [grace], folder)[0].name, 'grace.mxl')

    def test_chord_beams_kept_on_the_first_note_only(self):
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1">'
                             '<note><pitch><step>B</step><octave>4</octave></pitch><beam number="1">begin</beam></note>'
                             '<note><chord/><pitch><step>D</step><octave>5</octave></pitch><beam number="1">begin</beam></note>'
                             '</measure></part></score-partwise>')
        piano.fix_chord_beams(root)
        first, second = root.iter('note')
        self.assertIsNotNone(first.find('beam'))
        self.assertIsNone(second.find('beam'), 'Verovio drops beamed chords that repeat the beam')

    def test_recognition_asks_for_grace_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            calls = []

            def run(args, **kwargs):
                calls.append(args)
                (Path(args[args.index('-output') + 1]) / 'done.mxl').write_bytes(b'x')
                return subprocess.CompletedProcess(args, 0, '', '')

            with patch('sheet_labels.audiveris_command', return_value='/fake/audiveris'), \
                    patch('sheet_labels.subprocess.run', side_effect=run):
                recognize(blank_pdf(folder / 'source.pdf'), folder)
            self.assertIn('org.audiveris.omr.sheet.ProcessingSwitches.smallHeads=true', calls[0])
            self.assertIn('org.audiveris.omr.sheet.ProcessingSwitches.smallBeams=true', calls[0])

    def test_music_font_symbols_are_found(self):
        """A fake music font: noteheads, a fermata, "tr" + horizontal wiggles, vertical wiggles."""
        from fontTools.ttLib import TTFont
        from sheet_labels import music_symbols
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            font = TTFont('web/fonts/league-spartan-bold.ttf')
            for table in font['cmap'].tables:
                if table.isUnicode():  # distinct shapes, so each code survives in the PDF's text layer
                    table.cmap.update({0xF0CF: 'o', 0xF055: 'u', 0xF0D9: 't', 0xF07E: 's'})
            font.save(folder / 'music.ttf')
            with pymupdf.open() as pdf:
                page, f = pdf.new_page(width=400, height=300), str(folder / 'music.ttf')
                for x in (60, 80, 100):
                    page.insert_text((x, 200), '\uf0cf', fontfile=f, fontname='M', fontsize=20)
                page.insert_text((100, 150), '\uf055', fontfile=f, fontname='M', fontsize=20)
                page.insert_text((200, 150), '\uf0d9\uf07e\uf07e', fontfile=f, fontname='M', fontsize=20)
                for y in (180, 186, 192):
                    page.insert_text((300, y), '\uf07e', fontfile=f, fontname='M', fontsize=20, rotate=90)
                page.insert_text((20, 40), 'U in a text font', fontsize=12)
                pdf.save(folder / 'sheet.pdf')
            found = music_symbols(folder / 'sheet.pdf')
            self.assertEqual([k for _, k, *_ in found], ['fermata', 'trill', 'arpeggio'],
                             'Trill wiggles are not an arpeggio; stacked pieces make one arpeggio')
            arpeggio = found[2]
            self.assertLess(arpeggio[3] * 300, 180)
            self.assertGreater(arpeggio[4] * 300, 190)

    def test_symbols_are_placed_marked_and_played(self):
        """Page positions -> bar/beat/staff (Audiveris grid) -> MusicXML -> what you hear."""
        from sheet_labels import place_symbols
        import mido
        staff = lambda i, y: (f'<staff id="{i}"><lines>' + ''.join(
            f'<line><point x="0" y="{y + k * 10}"/><point x="1000" y="{y + k * 10}"/></line>' for k in range(5)) + '</lines></staff>')
        sheet = ('<sheet><picture width="1000" height="1000"/><page><system><part>' + staff(1, 100) + staff(2, 300)
                 + '</part><stack id="1" left="100" right="900"><slot x-offset="100" time-offset="0"/>'
                 '<slot x-offset="300" time-offset="1/4"/><slot x-offset="500" time-offset="1/2"/></stack></system></page></sheet>')
        folder = Path(tempfile.mkdtemp(dir=piano.WORK))
        with zipfile.ZipFile(folder / 'book.omr', 'w') as archive:
            archive.writestr('sheet#1/sheet#1.xml', sheet)
        symbols = [(0, 'fermata', 0.40, 0.07, 0.09), (0, 'trill', 0.60, 0.07, 0.09), (0, 'arpeggio', 0.18, 0.29, 0.35)]
        placed = place_symbols(symbols, folder / 'book.omr')
        self.assertEqual([(p['kind'], p['bar'], p['quarter'], p['staves']) for p in placed],
                         [('fermata', 0, 1.0, [0]), ('trill', 0, 2.0, [0]), ('arpeggio', 0, 0.0, [1])])
        note = lambda step, octave, chord=False, staff=1, duration=1, voice=1: (
            f'<note>{"<chord/>" if chord else ""}<pitch><step>{step}</step><octave>{octave}</octave></pitch>'
            f'<duration>{duration}</duration><voice>{voice}</voice><type>{"quarter" if duration == 1 else "half"}</type>'
            + ('<dot/>' if duration == 3 else '') + f'<staff>{staff}</staff></note>')
        bar = (note('C', 5) + note('D', 5) + note('E', 5) + '<backup><duration>3</duration></backup>'
               + note('C', 3, staff=2, duration=3, voice=2) + note('E', 3, True, 2, 3, 2) + note('G', 3, True, 2, 3, 2))
        xml = ('<score-partwise version="3.1"><part-list><score-part id="P1"><part-name>P</part-name></score-part></part-list>'
               '<part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths></key>'
               '<time><beats>3</beats><beat-type>4</beat-type></time><staves>2</staves><clef number="1"><sign>G</sign><line>2</line></clef>'
               f'<clef number="2"><sign>F</sign><line>4</line></clef></attributes>{bar}</measure></part></score-partwise>')
        root = ET.fromstring(xml)
        self.assertEqual(piano.mark_symbols(root, placed), 3)
        notes = list(root.iter('note'))
        self.assertIsNotNone(notes[1].find('notations/fermata'), 'Fermata on D (beat 2)')
        self.assertIsNotNone(notes[2].find('notations/ornaments/trill-mark'), 'Trill on E (beat 3)')
        self.assertEqual(sum(n.find('notations/arpeggiate') is not None for n in notes), 3, 'Whole left-hand chord rolls')
        path = folder / 'score.musicxml'
        ET.ElementTree(root).write(path)
        pages, timed, bars = piano.render(path, folder / 'score.pdf', folder / 'two.mid')
        midi = mido.MidiFile(str(folder / 'two.mid'))
        t, tempo, starts = 0, 500000, []
        for msg in mido.merge_tracks(midi.tracks):
            t += mido.tick2second(msg.time, midi.ticks_per_beat, tempo)
            if msg.type == 'set_tempo':
                tempo = msg.tempo
            if msg.type == 'note_on' and msg.velocity:
                starts.append((round(t, 2), msg.note))
        # D (beat 2) is held twice as long, so E starts at 1.5 s instead of 1.0 s, then trills with F.
        self.assertEqual([n for s, n in starts if s >= 1.49], [76, 77, 76, 77])
        self.assertEqual(min(s for s, n in starts if n == 76), 1.5)
        rolled = sorted(s for s, n in starts if n in (48, 52, 55))
        self.assertTrue(rolled[0] < rolled[1] < rolled[2] < 0.2, f'Left-hand chord rolls: {rolled}')
        self.assertAlmostEqual(max(e for _, e in timed.values()) / 1000, midi.length, delta=0.02,
                               msg='Score highlighting stays in step with the held note')

    def test_tuplet_marks_fix_duplets_and_sixes(self):
        """9/8: a "2" over two eighths (two in the time of three) that Audiveris read as plain eighths."""
        from sheet_labels import tuplet_marks
        with tempfile.TemporaryDirectory() as folder:
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=400, height=300)
                page.insert_text((10, 60), '2', fontsize=9)    # bar number at the line start
                page.insert_text((150, 90), '2', fontsize=8)   # duplet mark
                page.insert_text((200, 90), '12', fontsize=8)  # not a lone 2
                page.insert_text((250, 90), '6', fontsize=8)   # a six group
                pdf.save(Path(folder) / 'sheet.pdf')
            marks = tuplet_marks(Path(folder) / 'sheet.pdf')
            self.assertEqual([k for _, k, *_ in marks], ['tuplet2', 'tuplet2', 'tuplet6'],
                             'Lone 2s and 6s are candidates; placement drops the bar number')
        # Two eighths read plainly, then six eighths: 8 eighths = 4.0 quarters in a 4.5-quarter bar.
        eighth = lambda step, chord=False: (f'<note>{"<chord/>" if chord else ""}<pitch><step>{step}</step><octave>5</octave></pitch>'
                                            '<duration>1</duration><voice>1</voice><type>eighth</type><staff>1</staff></note>')
        rest = '<note><rest/><duration>1</duration><voice>1</voice><type>eighth</type><staff>1</staff></note>'
        bass = '<note><pitch><step>D</step><octave>3</octave></pitch><duration>9</duration><voice>5</voice><type>half</type><dot/><dot/><staff>2</staff></note>'
        bar = rest + eighth('F') + eighth('A', True) + ''.join(eighth(n) for n in 'GFEFED') + '<backup><duration>8</duration></backup>' + bass
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>2</divisions>'
                             '<time><beats>9</beats><beat-type>8</beat-type></time><staves>2</staves></attributes>'
                             f'{bar}</measure></part></score-partwise>')
        slots = [(100 + 50 * i, i / 2) for i in range(8)]  # x of each recognized eighth
        bar_number = {'kind': 'tuplet', 'count': 2, 'bar': 0, 'x': 400, 'slots': slots, 'staves': [0]}  # far from any pair
        mark = {'kind': 'tuplet', 'count': 2, 'bar': 0, 'x': 125, 'slots': slots, 'staves': [0]}  # over the rest + chord
        self.assertEqual(piano.apply_tuplets(root, [mark, bar_number]), 1)
        notes = list(root.iter('note'))
        self.assertEqual([n.findtext('duration') for n in notes[:3]], ['3', '3', '3'], 'Stretched 3/2 (divisions doubled)')
        self.assertEqual(root.findtext('.//divisions'), '4')
        self.assertEqual([n.findtext('time-modification/actual-notes') for n in notes[:3]], ['2', '2', '2'])
        self.assertEqual(notes[0].find('notations/tuplet').get('type'), 'start')
        self.assertEqual(notes[1].find('notations/tuplet').get('type'), 'stop')
        self.assertEqual(root.findtext('.//backup/duration'), '18', 'The left hand still starts at the bar line')
        voice = sum(int(n.findtext('duration')) for n in notes if n.findtext('voice') == '1' and n.find('chord') is None)
        self.assertEqual(voice, 18, 'The right hand now fills 9/8 exactly')
        self.assertEqual(piano.apply_tuplets(root, [mark]), 0, 'Applied once: the bar is no longer short')

    def test_six_groups_read_as_6_4_become_6_9_in_compound_meter(self):
        """Audiveris reads a "6" in 9/8 as six in the time of four; here it is six in the time of nine."""
        six = lambda step: (f'<note><pitch><step>{step}</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice>'
                            '<type>eighth</type><time-modification><actual-notes>6</actual-notes><normal-notes>4</normal-notes>'
                            '</time-modification><staff>1</staff></note>')
        for beats, unit, fixed in [(9, 8, 1), (3, 4, 0)]:  # only compound meters mean 6:9
            root = ET.fromstring(f'<score-partwise><part id="P1"><measure number="1"><attributes><divisions>12</divisions>'
                                 f'<time><beats>{beats}</beats><beat-type>{unit}</beat-type></time></attributes>'
                                 + ''.join(six(n) for n in 'GABAGF') + '</measure></part></score-partwise>')
            self.assertEqual(piano.apply_tuplets(root, []), fixed, 'No printed mark needed (scans)')
            if fixed:
                notes = list(root.iter('note'))
                self.assertEqual({n.findtext('duration') for n in notes}, {'9'}, 'Each eighth lasts 0.75 quarter')
                self.assertEqual({n.findtext('time-modification/normal-notes') for n in notes}, {'9'})
                self.assertEqual(sum(int(n.findtext('duration')) for n in notes), 54, 'Fills the 9/8 bar')

    def test_mistimed_voice_is_retimed_from_the_notes_above_it(self):
        """9/8: the right hand's "6" group is right; the left-hand notes stacked under it were
        read as plain eighths starting at the wrong time. Stacked notes are played together."""
        def note(step, x, staff, voice, duration, ratio=None, octave=5):
            tm = (f'<time-modification><actual-notes>{ratio[0]}</actual-notes><normal-notes>{ratio[1]}</normal-notes>'
                  '</time-modification>') if ratio else ''
            return (f'<note default-x="{x}"><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>{duration}</duration>'
                    f'<voice>{voice}</voice><type>eighth</type>{tm}<staff>{staff}</staff></note>')
        right = ''.join(note(n, x, 1, 1, 9, (6, 9)) for n, x in zip('GABCBG', (10, 40, 70, 100, 130, 160)))
        left = '<forward><duration>4</duration></forward>' + ''.join(
            note(n, x, 2, 5, 6, octave=3) for n, x in zip('GACBG', (40, 70, 100, 130, 160)))
        between = note('D', 55, 2, 6, 6, octave=2)  # sits between trusted notes: no safe time
        root = ET.fromstring('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>12</divisions>'
                             '<time><beats>9</beats><beat-type>8</beat-type></time><staves>2</staves></attributes>'
                             f'{right}<backup><duration>54</duration></backup>{left}<backup><duration>34</duration></backup>'
                             f'{between}</measure></part></score-partwise>')
        self.assertEqual(piano.retime_voices(root), 1)
        events = piano.voice_events(root.find('part/measure'), 2, 12)
        self.assertEqual([(o, l) for o, l, _ in events['5']], [(0.75, 0.75), (1.5, 0.75), (2.25, 0.75), (3.0, 0.75), (3.75, 0.75)])
        self.assertEqual({n.findtext('time-modification/normal-notes') for _, _, g in events['5'] for n in g}, {'3'})
        self.assertEqual([(o, l) for o, l, _ in events['6']], [(0.0, 0.5)], 'Not lined up with anything: left alone')
        self.assertEqual([el.findtext('duration') for el in root.iter('backup')], ['54', '54'], 'Backups rewind to the bar line')

    def test_unmarked_triplets_and_the_grid_after_them(self):
        """4/4: the left hand's two triplet groups have no "3", so they read as plain eighths and
        the right hand, which enters after the first group, is placed too late."""
        def eighth(step, staff, voice, beam, octave=4):
            return (f'<note><pitch><step>{step}</step><octave>{octave}</octave></pitch><duration>2</duration>'
                    f'<voice>{voice}</voice><type>eighth</type><staff>{staff}</staff><beam number="1">{beam}</beam></note>')
        def bar(time):
            left = ''.join(eighth(n, 2, 5, b, 3) for n, b in zip('ACFEBG', ('begin', 'continue', 'end') * 2))
            right = ('<forward><duration>6</duration></forward>'  # after the first group, timed as 3 plain eighths
                     '<note><pitch><step>A</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice>'
                     '<type>half</type><staff>1</staff></note>')
            return ('<score-partwise><part id="P1"><measure number="1"><attributes><divisions>4</divisions>'
                    f'{time}<staves>2</staves></attributes>{left}<backup><duration>12</duration></backup>{right}'
                    '<backup><duration>14</duration></backup></measure></part></score-partwise>')
        def staves(root):
            m = root.find('part/measure')
            return {k: [(o, l) for o, l, _ in piano.voice_events(m, staff, int(root.findtext('.//divisions')))[v]]
                    for k, staff, v in (('left', 2, '5'), ('right', 1, '1'))}

        root = ET.fromstring(bar('<time><beats>4</beats><beat-type>4</beat-type></time>'))
        self.assertEqual(piano.unmarked_triplets(root), 0, 'Not past the bar line, no marked triplets: leave it')
        root = ET.fromstring(bar('<time><beats>2</beats><beat-type>4</beat-type></time>'))  # now 3.0 > 2.0
        self.assertEqual(piano.unmarked_triplets(root), 2)
        third = 1 / 3
        self.assertEqual([round(o, 6) for o, _ in staves(root)['left']], [round(k * third, 6) for k in range(6)])
        self.assertEqual(staves(root)['right'][0][0], 1.0, 'Moved onto the corrected grid: enters after one beat')
        for time in ('<time><beats>12</beats><beat-type>8</beat-type></time>', ''):  # compound time, unknown meter
            self.assertEqual(piano.unmarked_triplets(ET.fromstring(bar(time))), 0)

        marked = ('<note><pitch><step>C</step><octave>5</octave></pitch><duration>2</duration><voice>2</voice><type>eighth</type>'
                  '<time-modification><actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>'
                  '<staff>1</staff><notations><tuplet type="start"/></notations></note>')
        root = ET.fromstring(bar('<time><beats>4</beats><beat-type>4</beat-type></time>').replace(
            '<backup><duration>14</duration></backup>', '<backup><duration>14</duration></backup>' + marked * piano.SIMILE_MARKS))
        self.assertEqual(piano.unmarked_triplets(root), 2, 'A sheet that marks triplets writes the rest the same way')

    def test_musicxml_plays_without_recognition_and_bars_are_checked(self):
        from music21 import key, meter, note, stream
        from sheet_labels import broken_bar_list
        folder = Path(tempfile.mkdtemp(dir=piano.WORK))
        part = stream.Part([key.KeySignature(2), meter.TimeSignature('3/4')] + [note.Note(p) for p in ('D4', 'F#4', 'A4', 'D5', 'A4', 'F#4')])
        (folder / 'packed').mkdir()  # music21 removes a same-named .musicxml when it writes the .mxl
        plain, packed = Path(part.write('musicxml', fp=folder / 'Minuet.musicxml')), Path(part.write('mxl', fp=folder / 'packed' / 'Minuet.mxl'))
        client = TestClient(piano.app)
        bad = client.post('/api/sheets/source', files={'file': ('broken.musicxml', b'<not xml', 'application/xml')})
        self.assertEqual(bad.status_code, 400)
        timewise = client.post('/api/sheets/source', files={'file': ('t.xml', b'<score-timewise><note/></score-timewise>', 'application/xml')})
        self.assertIn('part-wise', timewise.json()['error'])
        for upload in (plain, packed):
            source = client.post('/api/sheets/source', files={'file': (upload.name, upload.read_bytes(), 'application/xml')}).json()
            self.assertEqual((source['kind'], source['title']), ('musicxml', 'Minuet'))
            for endpoint in ('/api/sheets/label', '/api/sheets/clean'):
                self.assertEqual(client.post(endpoint, json={'source': source['id']}).status_code, 400, 'Needs a PDF page')
        with patch.object(piano, 'audiveris_command', return_value=None):  # not needed for exact notes
            job = client.post('/api/sheets/play', json={'source': source['id']}).json()['job']
            for _ in range(300):
                status = client.get(f'/api/jobs/{job}').json()
                if status['state'] not in ('queued', 'running'):
                    break
                time.sleep(0.2)
        self.assertEqual(status['state'], 'done', status.get('error'))
        r = status['result']
        self.assertEqual((r['key'], r['meter'], r['suspect'], r['checked']), ('D major', '3/4', [], True))
        self.assertEqual(sorted(n[2] for n in r['studio']['notes']), [62, 66, 66, 69, 69, 74])
        # A bar that runs past the bar line is named.
        broken = plain.read_text().replace('<duration>10080</duration>', '<duration>20160</duration>', 1)
        (folder / 'broken.musicxml').write_text(broken)
        self.assertEqual(broken_bar_list(folder / 'broken.musicxml'), ([0], 2))

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
