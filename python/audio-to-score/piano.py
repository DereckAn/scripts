"""Solo piano recording -> two-hand (grand staff) score. Runs on port 7861."""
import subprocess
import sys
import tempfile
from pathlib import Path

import gradio as gr
import librosa
import numpy as np
import pretty_midi
import torch
import verovio
from music21 import chord, clef, instrument, key, layout, metadata, meter, note, stream, tempo
from piano_transcription_inference import PianoTranscription, sample_rate
from beat_this.inference import File2Beats
from playwright.sync_api import sync_playwright

MODEL = None  # loaded on first ByteDance run
BEATS = None  # beat_this tracker, loaded on first run
SOUNDFONT = str(Path(__file__).parent / "soundfonts" / "GeneralUser-GS.sf2")


def beat_pos(t, beats):
    """Seconds -> position in beats, following the tracked beats (linear beyond the ends)."""
    t = np.asarray(t, dtype=float)
    p = np.diff(beats)
    inside = np.interp(t, beats, np.arange(len(beats)))
    before = (t - beats[0]) / p[0]
    after = len(beats) - 1 + (t - beats[-1]) / p[-1]
    return np.where(t < beats[0], before, np.where(t > beats[-1], after, inside))


def assign_hands(groups, lh=48.0, rh=72.0):
    """For each onset group (sorted pitches), how many of the lowest notes go to the left hand.

    Picks the split that keeps each hand near where it has been playing,
    within a reachable span (<= 14 semitones, <= 5 notes).
    """
    # ponytail: greedy per-onset choice; hand crossings and wide arpeggios need a lookahead/HMM.
    splits = []
    for ps in groups:
        def cost(k):
            total = 0.0
            for hand, centre in ((ps[:k], lh), (ps[k:], rh)):
                if hand:
                    total += abs(sum(hand) / len(hand) - centre)
                    total += 100 * (hand[-1] - hand[0] > 14) + 100 * (len(hand) > 5)
            return total
        k = min(range(len(ps) + 1), key=cost)
        if k:
            lh = 0.7 * lh + 0.3 * sum(ps[:k]) / k
        if k < len(ps):
            rh = 0.7 * rh + 0.3 * sum(ps[k:]) / (len(ps) - k)
        lh = min(lh, rh - 7)  # keep the hands from swapping places
        splits.append(k)
    return splits


def spell(p, k):
    """Respell a pitch to fit key k: scale notes as in the key, others sharp in sharp keys, flat in flat keys."""
    names = {s.name for s in k.getPitches()}
    for cand in [p] + p.getAllCommonEnharmonics():
        if cand.name in names:
            return cand
    if p.accidental is not None and (p.accidental.alter > 0) != (k.sharps >= 0):
        return p.getEnharmonic()
    return p


def meter_from(beats, downbeats):
    """(beats per bar, beat index of the first downbeat); 4 and the first beat when there are no downbeats."""
    idx = np.searchsorted(beats, downbeats)
    counts = np.diff(idx)
    n = int(np.bincount(counts).argmax()) if len(counts) else 4
    return (n if 2 <= n <= 7 else 4), (int(idx[0]) if len(idx) else 0)


def to_score(events, beats, downbeats=()):
    """Note events (seconds) + beat/downbeat times -> music21 grand-staff Score, quantized to 16ths."""
    # ponytail: one meter for the whole piece, bars aligned to the first downbeat; meter changes need per-bar barlines.
    per_bar, d0 = meter_from(beats, downbeats)
    on = beat_pos([e["onset_time"] for e in events], beats)
    off = beat_pos([e["offset_time"] for e in events], beats)
    origin = d0 - per_bar * np.ceil((d0 - on.min()) / per_bar)  # bar line at or before the first note
    q = lambda b: round((b - origin) * 4) / 4  # one beat = one quarter note, grid = 16ths
    groups = {}
    for e, a, b in zip(events, on, off):
        start = q(a)
        groups.setdefault(start, []).append((e["midi_note"], max(0.25, q(b) - start)))
    hands = {"lh": {}, "rh": {}}
    starts = sorted(groups)
    sorted_groups = [sorted(groups[s]) for s in starts]
    for start, notes, k in zip(starts, sorted_groups, assign_hands([[p for p, _ in g] for g in sorted_groups])):
        if notes[:k]:
            hands["lh"][start] = notes[:k]
        if notes[k:]:
            hands["rh"][start] = notes[k:]
    bpm = 60.0 / float(np.median(np.diff(beats)))

    score = stream.Score()
    for name, cl in (("rh", clef.TrebleClef()), ("lh", clef.BassClef())):
        part = stream.PartStaff()
        part.insert(0, instrument.Piano())
        part.insert(0, cl)
        part.insert(0, meter.TimeSignature(f"{per_bar}/4"))
        if name == "rh":
            part.insert(0, tempo.MetronomeMark(number=round(bpm)))
        for start, notes in sorted(hands.get(name, {}).items()):
            length = min(l for _, l in notes)  # one duration per chord keeps a single voice
            n = chord.Chord([p for p, _ in notes]) if len(notes) > 1 else note.Note(notes[0][0])
            n.quarterLength = length
            part.insert(start, n)
        # Clip overlaps so each hand reads as one voice.
        items = list(part.notes)
        for a, b in zip(items, items[1:]):
            if a.offset + a.quarterLength > b.offset:
                a.quarterLength = max(0.25, b.offset - a.offset)
        score.insert(0, part)
    k = score.analyze("key")
    for part in score.parts:
        part.insert(0, key.KeySignature(k.sharps))
        for n in part.notes:
            if n.isChord:
                n.pitches = tuple(spell(p, k) for p in n.pitches)
            else:
                n.pitch = spell(n.pitch, k)
    score.insert(0, layout.StaffGroup(list(score.parts), symbol="brace"))
    return score.makeNotation(), k, bpm


def render(xml_path, out_pdf):
    tk = verovio.toolkit(False)
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 40, "adjustPageHeight": False})
    tk.loadFile(str(xml_path))
    pages = [tk.renderToSVG(i + 1) for i in range(tk.getPageCount())]
    if not pages:
        raise gr.Error("Score rendering failed; the MusicXML and MIDI downloads are still usable.")
    html = "".join(f'<div style="page-break-after:always">{s}</div>' for s in pages)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(f"<html><body style='margin:0'>{html}</body></html>")
        page.pdf(path=str(out_pdf), format="A4")
        browser.close()
    return "".join(f'<div style="background:white;margin-bottom:12px">{s}</div>' for s in pages)


def transkun(audio, midi_path):
    subprocess.run([str(Path(sys.executable).parent / "transkun"), audio, str(midi_path)],
                   check=True, capture_output=True, timeout=1800)
    return [{"onset_time": n.start, "offset_time": n.end, "midi_note": n.pitch, "velocity": n.velocity}
            for inst in pretty_midi.PrettyMIDI(str(midi_path)).instruments for n in inst.notes]


def transcribe(audio, engine="ByteDance", progress=gr.Progress()):
    if not audio:
        raise gr.Error("Upload a piano recording first.")
    out = Path(tempfile.mkdtemp(prefix="piano-"))
    progress(0.05, desc="Loading audio")
    y, _ = librosa.load(audio, sr=sample_rate, mono=True)
    progress(0.1, desc="Transcribing notes (slow on CPU)")
    raw_midi = out / "performance.mid"
    if engine == "Transkun":
        events = transkun(audio, raw_midi)
    else:
        global MODEL
        MODEL = MODEL or PianoTranscription(device=torch.device("cpu"))
        events = MODEL.transcribe(y, str(raw_midi))["est_note_events"]
    if not len(events):
        raise gr.Error("No piano notes detected.")
    progress(0.8, desc="Estimating tempo and writing score")
    global BEATS
    if BEATS is None:
        BEATS = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    beats, downbeats = BEATS(audio)
    if len(beats) < 2:
        beats, downbeats = np.arange(0, len(y) / sample_rate + 0.5, 0.5), []  # no beat found: 120 BPM, 4/4
    score, k, bpm = to_score(events, beats, downbeats)
    meter_text = score.parts[0].recurse().getElementsByClass(meter.TimeSignature).first().ratioString
    score.insert(0, metadata.Metadata(title=Path(audio).stem))
    xml = Path(score.write("musicxml", fp=out / "score.musicxml"))
    midi = Path(score.write("midi", fp=out / "score_two_hands.mid"))
    progress(0.9, desc="Rendering pages")
    pdf = out / "score.pdf"
    html = render(xml, pdf)
    progress(0.95, desc="Synthesizing piano audio")
    wav = out / "score_piano.wav"
    subprocess.run(["fluidsynth", "-ni", "-q", "-g", "0.8", "-r", "44100", "-F", str(wav), SOUNDFONT, str(midi)],
                   check=True, capture_output=True, timeout=600)
    return (f"Done with {engine}: {len(events)} notes, ~{round(bpm)} beats/min, {meter_text} time, key {k.tonic.name} {k.mode}.", str(wav), html,
            [str(pdf), str(xml), str(midi), str(wav), str(raw_midi)])


with gr.Blocks(title="Piano to Score", theme=gr.themes.Soft(primary_hue="teal")) as demo:
    gr.Markdown("# Piano to Score\nSolo piano recording → two-hand sheet music (right hand treble, left hand bass).")
    audio = gr.Audio(sources=["upload"], type="filepath", label="Piano recording")
    engine = gr.Radio(["ByteDance", "Transkun"], value="ByteDance", label="Transcription engine",
                      info="Try both on the same song and compare.")
    run = gr.Button("Convert", variant="primary")
    status = gr.Textbox(label="Status", interactive=False)
    files = gr.File(label="PDF · MusicXML (open in MuseScore to edit) · two-hand MIDI · raw performance MIDI",
                    file_count="multiple", interactive=False)
    listen = gr.Audio(label="Listen to the sheet music (played from the score, not the original recording)",
                      interactive=False)
    sheet = gr.HTML()
    gr.Markdown("Hands are separated by following where each hand plays; rhythm and barlines follow the detected beats and downbeats (beat_this); rhythm is snapped to 16th notes. "
                "For cleanup, open the MusicXML in MuseScore. The raw performance MIDI keeps the exact timing.")
    run.click(transcribe, [audio, engine], [status, listen, sheet, files], concurrency_limit=1)

if __name__ == "__main__":
    demo.queue(max_size=5).launch(server_name="127.0.0.1", server_port=7861, max_file_size="100mb")
