"""Run: .venv/bin/python test_piano.py"""
import numpy as np
from music21 import key, pitch

from piano import assign_hands, beat_pos, meter_from, spell

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
print("ok")
