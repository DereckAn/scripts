"""Follow a real recording with a score that was read from a sheet.

1. Transcribe the recording into struck notes (the app's piano transcription).
2. Rough alignment: chroma of the score's MIDI vs chroma of the transcription, matched with
   dynamic time warping.
3. Pin each bar's first struck chord to the moment most of its pitches are struck
   together near the rough guess. On Clair de Lune this lands within 0.05 s of an exact
   reference (median; 90% within 0.17 s), where plain DTW was off by > 0.3 s on 18 bars.
4. Keep bars where a first-chord note was really found; the Studio interpolates between
   the remaining [score s, recording s] pairs, as it does for converted recordings.
"""
import json
from pathlib import Path

import numpy as np

FS = 20  # alignment frames per second
TOGETHER = 0.08  # seconds: notes struck this close count as one chord
SEARCH = 1.2  # seconds around the rough guess to look for a bar's first chord


def recording_notes(audio, cache=None):
    """[(onset s, offset s, MIDI pitch)] of a piano recording; cached as JSON if asked."""
    if cache and Path(cache).is_file():
        return [tuple(n) for n in json.loads(Path(cache).read_text())]
    import librosa
    import torch
    from piano_transcription_inference import PianoTranscription, sample_rate
    import piano
    y, _ = librosa.load(str(audio), sr=sample_rate, mono=True)
    piano.MODEL = piano.MODEL or PianoTranscription(device=torch.device("cpu"))
    result = piano.MODEL.transcribe(y, None)
    notes = [(round(float(e["onset_time"]), 3), round(float(e["offset_time"]), 3), int(e["midi_note"]))
             for e in result["est_note_events"]]
    if cache:
        Path(cache).write_text(json.dumps(notes))
    return notes


def _chroma(pm):
    c = pm.get_chroma(fs=FS) + 1e-3  # silence stays comparable
    return c / np.linalg.norm(c, axis=0, keepdims=True)


def bar_pins(score_midi, bar_secs, notes):
    """One pin per bar: (score s, recording s, found) for the bar's first struck chord (the
    downbeat, or the first chord after a rest), where found = how many of its pitches were
    struck there together (0: nothing matched, the time is only the rough guess)."""
    import librosa
    import pretty_midi
    score = pretty_midi.PrettyMIDI(str(score_midi))
    struck = sorted((n.start, n.pitch) for inst in score.instruments for n in inst.notes)
    played = pretty_midi.PrettyMIDI()
    track = pretty_midi.Instrument(0)
    track.notes = [pretty_midi.Note(80, p, a, max(b, a + 0.05)) for a, b, p in notes]
    played.instruments.append(track)
    X, R = _chroma(score), _chroma(played)
    _, path = librosa.sequence.dtw(X=X, Y=R, metric="cosine")
    score_to_rec = {}
    for i, j in path[::-1]:
        score_to_rec.setdefault(i, []).append(j)
    onsets = np.array([a for a, _, _ in notes])
    pitches = np.array([p for _, _, p in notes])
    pins = []
    for start, end in zip(bar_secs, list(bar_secs[1:]) + [float("inf")]):
        inside = [t for t, _ in struck if start - 0.02 <= t < end - 0.02]
        if not inside:
            continue
        sec = inside[0]
        chord = {p for t, p in struck if abs(t - sec) < 0.02}
        guess = float(np.median(score_to_rec[min(int(round(sec * FS)), X.shape[1] - 1)])) / FS
        best = None  # most of the chord struck together, nearest the guess
        for t in onsets[(np.abs(onsets - guess) < SEARCH) & np.isin(pitches, list(chord))]:
            together = len(set(pitches[(np.abs(onsets - t) < TOGETHER) & np.isin(pitches, list(chord))]))
            rank = (together, -abs(t - guess))
            if best is None or rank > best[0]:
                best = (rank, float(t))
        if best:  # the chord starts with its first struck note (chords are often slightly rolled)
            t = best[1]
            start = float(onsets[(np.abs(onsets - t) < TOGETHER) & np.isin(pitches, list(chord))].min())
            pins.append((sec, start, best[0][0]))
        else:
            pins.append((sec, guess, 0))
    return pins


DOUBT = 2.0  # seconds: an unmatched pin this far from what its matched neighbours imply is dropped


def timing_map(pins, score_end, recording_end):
    """[[score s, recording s]] for the Studio from bar_pins. Pins where a chord note was really
    found are kept; an unmatched pin is only the rough guess, kept unless it lies more than DOUBT
    from the line between its matched neighbours (on Clair de Lune the one bad guess was 2.6 s
    off it, the good ones under 1.5 s). Kept strictly increasing, plus the end; the Studio
    interpolates between them."""
    matched = [(s, t) for s, t, found in pins if found]
    pairs = []
    for sec, t, found in pins:
        if not found and len(matched) >= 2:
            expected = float(np.interp(sec, [m[0] for m in matched], [m[1] for m in matched]))
            if abs(t - expected) > DOUBT:
                continue
        if not pairs or (sec > pairs[-1][0] and t > pairs[-1][1]):
            pairs.append((sec, t))
    if not pairs or score_end > pairs[-1][0] and recording_end > pairs[-1][1]:
        pairs.append((score_end, recording_end))
    return [[round(s, 3), round(r, 3)] for s, r in pairs]
