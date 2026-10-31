"""Solo piano recording -> two-hand (grand staff) score. Runs on port 7861."""
import base64
import html
import json
import subprocess
import sys
import tempfile
import urllib.parse
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
WORK = (Path(tempfile.gettempdir()) / "piano-to-score").resolve()  # results live here; the web server may serve only this folder
WORK.mkdir(exist_ok=True)


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


def split_voices(groups, slack=0.5):
    """One hand's onset groups [(start, [(pitch, length), ...])] -> (upper, lower) voices of (start, pitches, length).

    A held note keeps sounding in its own voice while other notes move in the second voice.
    Overlaps of <= `slack` beats are treated as legato and clipped instead of opening a voice.
    Within a voice nothing overlaps.
    """
    # ponytail: greedy, at most 2 voices per hand; three-voice textures get clipped.
    voices, end = ([], []), [0.0, 0.0]
    for start, notes in groups:
        lengths = sorted({l for _, l in notes})
        subsets = [notes] if len(lengths) == 1 else [
            [n for n in notes if n[1] == lengths[0]], [n for n in notes if n[1] != lengths[0]]]
        subsets.sort(key=lambda s: -max(p for p, _ in s))  # upper subset first
        def rank(v):  # lower is better: voice still in use and free > legato overlap > idle voice > busy
            overlap = end[v] - start
            in_use = voices[v] and end[v] > start - 1
            return (0 if overlap <= 0 and in_use else 1 if 0 < overlap <= slack else 2 if overlap <= 0 else 3,
                    end[v] if overlap > slack else v)
        for i, sub in enumerate(subsets):
            # mixed lengths at one onset: upper part -> voice 0, lower -> voice 1
            v = i if len(subsets) == 2 else min((0, 1), key=rank)
            if voices[v] and end[v] > start:  # cut the previous note so the voice doesn't overlap itself
                s0, ps, _ = voices[v][-1]
                voices[v][-1] = (s0, ps, start - s0)
            length = min(l for _, l in sub)
            voices[v].append((start, sorted(p for p, _ in sub), length))
            end[v] = start + length
    return voices


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
        upper, lower = split_voices(sorted(hands.get(name, {}).items()))
        for vid, items in (("1", upper), ("2", lower)):
            if not items:
                continue
            voice = stream.Voice(id=vid)
            for start, pitches, length in items:
                n = chord.Chord(pitches) if len(pitches) > 1 else note.Note(pitches[0])
                n.quarterLength = length
                voice.insert(start, n)
            part.insert(0, voice)
        score.insert(0, part)
    k = score.analyze("key")
    for part in score.parts:
        part.insert(0, key.KeySignature(k.sharps))
        for n in part.recurse().notes:
            if n.isChord:
                n.pitches = tuple(spell(p, k) for p in n.pitches)
            else:
                n.pitch = spell(n.pitch, k)
    score.insert(0, layout.StaffGroup(list(score.parts), symbol="brace"))
    score = score.makeNotation()
    for part in score.parts:  # makeNotation numbers voices from 0; MusicXML readers expect 1, 2
        for m in part.getElementsByClass(stream.Measure):
            for i, v in enumerate(m.voices):
                v.id = str(i + 1)
    return score, k, bpm


def render(xml_path, out_pdf, out_midi):
    """MusicXML -> (SVG pages, {note id: [start ms, end ms]}); also writes the PDF and a MIDI whose timing matches."""
    tk = verovio.toolkit(False)
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 40, "adjustPageHeight": False})
    tk.loadFile(str(xml_path))
    pages = [tk.renderToSVG(i + 1) for i in range(tk.getPageCount())]
    if not pages:
        raise gr.Error("Score rendering failed; the MusicXML download is still usable.")
    # Same toolkit -> SVG note ids, MIDI and timemap all agree, so playback and highlighting stay in sync.
    out_midi.write_bytes(base64.b64decode(tk.renderToMIDI()))
    notes = {}
    for ev in tk.renderToTimemap({"includeMeasures": False, "includeRests": False}):
        for i in ev.get("on", []):
            notes[i] = [ev["tstamp"], ev["tstamp"]]
        for i in ev.get("off", []):
            if i in notes:
                notes[i][1] = ev["tstamp"]
    printable = "".join(f'<div style="page-break-after:always">{s}</div>' for s in pages)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(f"<html><body style='margin:0'>{printable}</body></html>")
        page.pdf(path=str(out_pdf), format="A4")
        browser.close()
    return pages, notes


def player_html(pages, notes, audio_path):
    """Score pages + an audio player; the script in HEAD highlights notes as they play and seeks on click."""
    data = html.escape(json.dumps([[i, s, e] for i, (s, e) in notes.items()]))
    src = "/gradio_api/file=" + urllib.parse.quote(str(audio_path))
    sheets = "".join(f'<div class="follow-page">{s}</div>' for s in pages)
    return (f'<div class="follow" data-notes="{data}">'
            f'<audio class="follow-audio" controls preload="auto" src="{src}"></audio>{sheets}</div>')


def transkun(audio, midi_path):
    subprocess.run([str(Path(sys.executable).parent / "transkun"), audio, str(midi_path)],
                   check=True, capture_output=True, timeout=1800)
    return [{"onset_time": n.start, "offset_time": n.end, "midi_note": n.pitch, "velocity": n.velocity}
            for inst in pretty_midi.PrettyMIDI(str(midi_path)).instruments for n in inst.notes]


def transcribe(audio, engine="ByteDance", progress=gr.Progress()):
    if not audio:
        raise gr.Error("Upload a piano recording first.")
    out = Path(tempfile.mkdtemp(prefix="piano-", dir=WORK))
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
    progress(0.9, desc="Rendering pages")
    pdf, midi = out / "score.pdf", out / "score_two_hands.mid"
    pages, notes = render(xml, pdf, midi)
    progress(0.95, desc="Synthesizing piano audio")
    wav, mp3 = out / "score_piano.wav", out / "score_piano.mp3"
    subprocess.run(["fluidsynth", "-ni", "-q", "-g", "0.8", "-r", "44100", "-F", str(wav), SOUNDFONT, str(midi)],
                   check=True, capture_output=True, timeout=600)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav), "-q:a", "3", str(mp3)],
                   check=True, capture_output=True, timeout=600)
    wav.unlink()
    return (f"Done with {engine}: {len(events)} notes, ~{round(bpm)} beats/min, {meter_text} time, key {k.tonic.name} {k.mode}. "
            "Press play to follow along; click any note to jump there.",
            player_html(pages, notes, mp3), [str(pdf), str(xml), str(midi), str(mp3), str(raw_midi)])


FOLLOW_CSS = """
.follow-audio { width: 100%; position: sticky; top: 0; z-index: 5; margin-bottom: 8px; }
.follow-page { background: white; margin-bottom: 12px; }
.follow g.note { cursor: pointer; }
.follow g.note.playing, .follow g.note.playing * { fill: #0d9488; stroke: #0d9488; }
"""

FOLLOW_JS = """<script>
(() => {
  const setup = a => a._notes || (a._notes = JSON.parse(a.closest('.follow').dataset.notes)
    .map(([id, s, e]) => [a.closest('.follow').querySelector('[id="' + id + '"]'), s, e]).filter(n => n[0]));
  const show = a => {
    const t = a.currentTime * 1000;
    let first = null;
    for (const [el, s, e] of setup(a)) {
      const on = s <= t && t < e;
      el.classList.toggle('playing', on);
      if (on && !first) first = el;
    }
    if (first) {
      const r = first.getBoundingClientRect();
      if (r.top < 80 || r.bottom > innerHeight - 40) first.scrollIntoView({block: 'center', behavior: 'smooth'});
    }
  };
  const loop = a => { show(a); if (!a.paused) requestAnimationFrame(() => loop(a)); };
  const isPlayer = el => el && el.classList && el.classList.contains('follow-audio');
  document.addEventListener('play', e => isPlayer(e.target) && loop(e.target), true);
  document.addEventListener('seeked', e => isPlayer(e.target) && show(e.target), true);
  document.addEventListener('click', e => {
    const n = e.target.closest && e.target.closest('.follow g.note');
    if (!n) return;
    const a = n.closest('.follow').querySelector('.follow-audio');
    const hit = setup(a).find(([el]) => el === n);
    if (hit) { a.currentTime = hit[1] / 1000; a.play(); }
  });
})();
</script>"""


with gr.Blocks(title="Piano to Score", theme=gr.themes.Soft(primary_hue="teal"),
               css=FOLLOW_CSS, head=FOLLOW_JS) as demo:
    gr.Markdown("# Piano to Score\nSolo piano recording → two-hand sheet music (right hand treble, left hand bass).")
    audio = gr.Audio(sources=["upload"], type="filepath", label="Piano recording")
    engine = gr.Radio(["ByteDance", "Transkun"], value="ByteDance", label="Transcription engine",
                      info="Try both on the same song and compare.")
    run = gr.Button("Convert", variant="primary")
    status = gr.Textbox(label="Status", interactive=False)
    sheet = gr.HTML()
    files = gr.File(label="PDF · MusicXML (open in MuseScore to edit) · two-hand MIDI · piano audio (MP3) · raw performance MIDI",
                    file_count="multiple", interactive=False)
    gr.Markdown("Hands are separated by following where each hand plays; rhythm and barlines follow the detected beats and downbeats (beat_this); rhythm is snapped to 16th notes. "
                "For cleanup, open the MusicXML in MuseScore. The raw performance MIDI keeps the exact timing.")
    run.click(transcribe, [audio, engine], [status, sheet, files], concurrency_limit=1)

if __name__ == "__main__":
    demo.queue(max_size=5).launch(server_name="127.0.0.1", server_port=7861, max_file_size="100mb",
                                  allowed_paths=[str(WORK)])  # lets the player stream the generated MP3
