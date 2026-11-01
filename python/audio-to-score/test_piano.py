"""Run: .venv/bin/python test_piano.py"""
import numpy as np
from music21 import key, meter, note, pitch, stream

from piano import assign_hands, beat_grid, beat_pos, is_link, pedal_from_cc, meter_from, spell, split_voices

# Beats speed up (0.5 s -> 0.25 s apart): positions follow the beats, and extend past both ends.
beats = np.array([1.0, 1.5, 2.0, 2.25, 2.5])
assert np.allclose(beat_pos([1.0, 1.75, 2.375, 0.5, 2.75], beats), [0, 1.5, 3.5, -1, 5])

# Bass + chord split low/high; a lone high melody note goes right, a lone low note goes left.
assert assign_hands([[36, 43, 64, 67, 72]]) == [2]
assert assign_hands([[76], [38]]) == [0, 1]
# A right-hand line that dips below middle C stays in the right hand (old fixed split would move it).
assert assign_hands([[40, 67], [40, 64], [40, 62], [40, 59], [40, 57]]) == [1, 1, 1, 1, 1]
# A five-octave cluster can't fit one hand.
assert 0 < assign_hands([[30, 90]])[0] < 2

# Spelling: A# becomes Bb in F major; F# stays F# in G major.
assert spell(pitch.Pitch("A#4"), key.Key("F")).name == "B-"
assert spell(pitch.Pitch("G-4"), key.Key("G")).name == "F#"
# Meter: downbeats every 6 beats (one odd 5-beat bar) -> 6 per bar, first bar at beat 2.
b = np.arange(30) * 0.4
assert meter_from(b, b[[2, 8, 14, 19, 25]]) == (6, 2)
assert meter_from(b, []) == (4, 0)
# Voices: a held whole note on top while eighths move below -> two voices, nothing clipped.
up, low = split_voices([(0, [(72, 4), (64, 0.5)])] + [(i * 0.5, [(60 + i, 0.5)]) for i in range(1, 8)])
assert up == [(0, [72], 4)] and len(low) == 8 and low[0] == (0, [64], 0.5)
# Plain legato line (each note overlaps the next by a 16th) stays in one voice.
up, low = split_voices([(i, [(60 + i, 1.25)]) for i in range(4)])
assert low == [] and [l for _, _, l in up] == [1, 1, 1, 1.25]
# Links: only http(s) URLs pass; options and local paths never reach yt-dlp.
assert is_link(" https://www.youtube.com/watch?v=abc ") and is_link("https://youtu.be/abc")
assert not any(map(is_link, ["--exec rm", "/etc/passwd", "file:///etc/passwd", "youtube.com/watch?v=abc", ""]))
# Triplets: a beat played in threes gets a triplet grid; straight 16ths and slight jitter stay straight.
g = beat_grid([0, 1/3, 2/3, 1, 1.25, 1.5, 1.75, 2.0, 2.31, 2.5])
assert g == {0: 3, 1: 4, 2: 4}, g
# Pedal: down/up control changes -> spans; a pedal still down at the end runs to the end.
assert pedal_from_cc([(0.1, 127), (1.0, 0), (1.2, 100), (1.3, 90), (2.0, 10), (3.0, 127)]) == [(0.1, 1.0), (1.2, 2.0), (3.0, float("inf"))]
# A note made from a MIDI number must not keep its explicit natural (it printed stray ♮ signs).
assert spell(note.Note(77).pitch, key.Key("C")).accidental is None
# ...but a note that needs a natural still prints one: B natural in F major (B-flat in the key signature).
part = stream.Part([meter.TimeSignature("4/4"), key.KeySignature(-1)])
for i, m in enumerate([70, 71, 72, 69]):
    n = note.Note(m)
    n.pitch = spell(n.pitch, key.Key("F"))
    part.insert(i, n)
shown = [(n.name, n.pitch.accidental is not None and n.pitch.accidental.displayStatus)
         for n in stream.Score([part]).makeNotation().recurse().notes]
assert shown == [("B-", False), ("B", True), ("C", False), ("A", False)], shown
print("ok")
