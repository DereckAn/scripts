"""Run: .venv/bin/python -m unittest test_accuracy"""
import tempfile
import unittest
from pathlib import Path

import mido

import accuracy as A


class AccuracyTests(unittest.TestCase):
    def test_extra_bar_missed_tie_and_wrong_pitch_are_counted(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            # Reference, 3/4: bar 1 = C5 quarter, E5 half tied into bar 2 (one long note), then G5 half.
            midi = mido.MidiFile(ticks_per_beat=4)
            meta, track = mido.MidiTrack(), mido.MidiTrack()
            meta.append(mido.MetaMessage("time_signature", numerator=3, denominator=4))
            for note, start, length in [(72, 0, 4), (76, 4, 12), (79, 16, 8)]:
                track.append(mido.Message("note_on", note=note, velocity=80, time=start - sum(m.time for m in track)))
                track.append(mido.Message("note_off", note=note, velocity=0, time=length))
            midi.tracks += [meta, track]
            midi.save(folder / "ref.mid")
            ref, starts = A.reference_bars(folder / "ref.mid")
            self.assertEqual([[(o, p, l) for o, p, l, _ in bar] for bar in ref], [[(0, 72, 1), (1, 76, 3)], [(1, 79, 2)]])

            # The reading: an extra empty bar first, the tie missed (E5 struck again), G5 read as A5.
            note = lambda step, dur, tie="": (f'<note><pitch><step>{step}</step><octave>5</octave></pitch>'
                                             f'<duration>{dur}</duration>{tie}<voice>1</voice></note>')
            rest = '<note><rest/><duration>3</duration><voice>1</voice></note>'
            measures = [rest, note("C", 1) + note("E", 2, '<tie type="start"/>'), note("E", 1) + note("A", 2)]
            body = "".join(f'<measure number="{i}">' + ('<attributes><divisions>1</divisions><time><beats>3</beats>'
                                                        '<beat-type>4</beat-type></time></attributes>' if i == 0 else '')
                           + m + '</measure>' for i, m in enumerate(measures))
            (folder / "read.musicxml").write_text(f'<score-partwise><part id="P1">{body}</part></score-partwise>')
            got, wrong = A.musicxml_bars(folder / "read.musicxml")
            result = A.compare(ref, starts, got, wrong)
            self.assertEqual(result["extra bars"], 1, "The empty bar is skipped, not shifting everything after it")
            self.assertEqual(result["placed right"], 2)  # C5 and E5
            self.assertEqual(result["missed ties"], 1)  # E5 struck again in bar 2
            self.assertEqual(result["pitches right (any rhythm)"], 2)
            self.assertEqual(result["notes read"], 4)

    def test_tied_notes_are_joined(self):
        with tempfile.TemporaryDirectory() as folder:
            xml = Path(folder) / "tie.musicxml"
            xml.write_text('<score-partwise><part id="P1">'
                           '<measure number="1"><attributes><divisions>1</divisions><time><beats>2</beats><beat-type>4</beat-type></time></attributes>'
                           '<note><pitch><step>D</step><alter>-1</alter><octave>5</octave></pitch><duration>2</duration><tie type="start"/></note></measure>'
                           '<measure number="2"><note><pitch><step>D</step><alter>-1</alter><octave>5</octave></pitch><duration>1</duration><tie type="stop"/></note>'
                           '<note><rest/><duration>1</duration></note></measure></part></score-partwise>')
            bars, wrong = A.musicxml_bars(xml)
            self.assertEqual(bars, [[(0, 73, 3, 1)], []], "One D-flat held over the bar line")
            self.assertEqual(wrong, set())


if __name__ == "__main__":
    unittest.main()
