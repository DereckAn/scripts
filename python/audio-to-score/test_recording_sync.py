"""Run: .venv/bin/python -m unittest test_recording_sync"""
import tempfile
import unittest
from pathlib import Path

import pretty_midi
from fastapi.testclient import TestClient

import piano
from recording_sync import bar_pins, timing_map

CHORDS = [(60, 64, 67), (62, 65, 69), (64, 67, 71), (65, 69, 72)]  # one chord per bar


class RecordingSyncTests(unittest.TestCase):
    def test_bars_are_pinned_to_the_chords_struck_in_the_recording(self):
        """Score: a chord every second. Recording: the same, half as fast, after a 1 s pause,
        with a stray wrong note near bar 2."""
        with tempfile.TemporaryDirectory() as folder:
            score = pretty_midi.PrettyMIDI()
            track = pretty_midi.Instrument(0)
            for bar, chord in enumerate(CHORDS):
                track.notes += [pretty_midi.Note(80, p, bar, bar + 1) for p in chord]
            score.instruments.append(track)
            score.write(str(Path(folder) / "score.mid"))
            played = [(1 + 2 * bar + 0.01 * i, 1 + 2 * bar + 1.9, p) for bar, chord in enumerate(CHORDS)
                      for i, p in enumerate(chord)] + [(3.4, 3.6, 66)]
            pins = bar_pins(Path(folder) / "score.mid", [0, 1, 2, 3], played)
            self.assertEqual([round(t, 2) for _, t, _ in pins], [1.0, 3.0, 5.0, 7.0])
            self.assertEqual([found for _, _, found in pins], [3, 3, 3, 3], "Every chord found struck together")

    def test_timing_map_keeps_confirmed_and_plausible_pins(self):
        pins = [(0, 1.0, 3), (1, 3.0, 2), (2, 5.2, 0), (3, 12.0, 0), (4, 9.0, 3), (5, 8.0, 2)]
        # (2, 5.2) is a plausible guess (5.0 expected); (3, 12.0) a wild one (7.0 expected);
        # (5, 8.0) goes back in time.
        self.assertEqual(timing_map(pins, 6, 11.0), [[0, 1.0], [1, 3.0], [2, 5.2], [4, 9.0], [6, 11.0]])

    def test_recording_endpoint_validation(self):
        client = TestClient(piano.app)
        self.assertEqual(client.post("/api/scores/recording", json={"score": "../x", "source": "y"}).status_code, 400)
        folder = Path(tempfile.mkdtemp(prefix="piano-test-", dir=piano.WORK))
        (folder / "score.musicxml").write_text("<score-partwise/>")
        response = client.post("/api/scores/recording", json={"score": folder.name, "source": "missing"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("recording", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
