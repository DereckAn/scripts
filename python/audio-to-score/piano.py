"""Solo piano recording -> two-hand (grand staff) score. Web app on http://127.0.0.1:7861 (page: web/index.html)."""
import base64
import copy
import html
import json
from fractions import Fraction
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import uuid
from pathlib import Path

import librosa
import numpy as np
import mido
import pretty_midi
import torch
import verovio
from music21 import chord, clef, expressions, instrument, key, layout, metadata, meter, note, stream, tempo
from piano_transcription_inference import PianoTranscription, sample_rate
from beat_this.inference import File2Beats
from fastapi import FastAPI, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from playwright.sync_api import sync_playwright
from pydantic import BaseModel
import uvicorn

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
    out = p
    for cand in [p] + p.getAllCommonEnharmonics():
        if cand.name in names:
            out = cand
            break
    else:
        if p.accidental is not None and (p.accidental.alter > 0) != (k.sharps >= 0):
            out = p.getEnharmonic()
    if out.accidental is not None and out.accidental.alter == 0:
        out = copy.deepcopy(out)
        out.accidental = None  # notes made from MIDI numbers carry an explicit natural that would print as ♮
    return out


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


def beat_step(beats):
    """Typical beat length. When the tracker mixes levels (long, long, short, short...) the short one is the beat."""
    gaps = np.diff(beats)
    med, short = float(np.median(gaps)), float(np.percentile(gaps, 20))
    if short < 0.75 * med and np.mean(np.abs(gaps - short) <= 0.15 * short) >= 0.25:
        return short
    return med


def fill_bars(beats, downbeats):
    """Repair bars where the tracker missed, added or unevenly placed beats.

    A bar between two downbeats that is as long as the usual number of beats per bar but holds a different number
    of beats gets that many evenly spaced beats instead. Bars that are really shorter or longer stay as found.
    """
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 2 or len(downbeats) < 2:
        return beats
    step = beat_step(beats)
    sizes = [round((b - a) / step) for a, b in zip(downbeats[:-1], downbeats[1:])]
    per_bar = int(np.bincount(sizes).argmax())
    # Lead-in before the first downbeat and the tail after the last one: evenly spaced at the beat length.
    lead = round((downbeats[0] - beats[0]) / step)
    out = list(downbeats[0] - step * np.arange(lead, 0, -1))
    for a, b, size in zip(downbeats[:-1], downbeats[1:], sizes):
        inside = beats[(beats >= a - step / 4) & (beats < b - step / 4)]
        if len(inside) != per_bar and size == per_bar:
            inside = a + (b - a) * np.arange(per_bar) / per_bar
        out.extend(inside)
    out.extend(downbeats[-1] + step * np.arange(max(0, round((beats[-1] - downbeats[-1]) / step)) + 1))
    return np.array(out)


def beat_grid(onsets):
    """Onsets in beats -> {beat number: 3 or 4}: triplet eighths where they fit clearly better than 16ths."""
    by_beat = {}
    for x in onsets:
        by_beat.setdefault(int(np.floor(x)), []).append(x - np.floor(x))
    grid = {}
    for b, fracs in by_beat.items():
        err = lambda div: sum(abs(f - round(f * div) / div) for f in fracs)
        # Bias toward 16ths: beat-tracking jitter alone shouldn't turn a beat into triplets.
        grid[b] = 3 if err(3) < 0.5 * err(4) else 4
    return grid


def pedal_from_cc(changes):
    """Sustain-pedal control changes [(time, value)] -> [(down, up)] seconds."""
    spans, down = [], None
    for t, v in sorted(changes):
        if v >= 64 and down is None:
            down = t
        elif v < 64 and down is not None:
            spans.append((down, t))
            down = None
    return spans + ([(down, float("inf"))] if down is not None else [])


def to_score(events, beats, downbeats=(), pedals=()):
    """Note events (seconds) + beat/downbeat times + pedal spans -> (music21 grand-staff Score, key, bpm, hand per event,
    [[score seconds, recording seconds] per beat]).

    Each beat is a quarter note, split into 16ths, or into triplet eighths where the playing is in threes.
    """
    # ponytail: one meter for the whole piece, bars aligned to the first downbeat; meter changes need per-bar barlines.
    beats = fill_bars(beats, downbeats)
    per_bar, d0 = meter_from(beats, downbeats)
    on = beat_pos([e["onset_time"] for e in events], beats)
    off = beat_pos([e["offset_time"] for e in events], beats)
    origin = d0 - per_bar * np.ceil((d0 - on.min()) / per_bar)  # bar line at or before the first note
    grid = beat_grid(on - origin)

    def q(b):
        x = b - origin
        i = int(np.floor(x))
        div = grid.get(i, 4)
        return i + Fraction(round((x - i) * div), div)

    groups = {}
    for i, (e, a, b) in enumerate(zip(events, on, off)):
        start = q(a)
        shortest = Fraction(1, grid.get(int(np.floor(a - origin)), 4))
        groups.setdefault(start, []).append((e["midi_note"], max(shortest, q(b) - start), i))
    hands, hand_of = {"lh": {}, "rh": {}}, ["r"] * len(events)
    starts = sorted(groups)
    sorted_groups = [sorted(groups[s]) for s in starts]
    for start, notes, k in zip(starts, sorted_groups, assign_hands([[p for p, _, _ in g] for g in sorted_groups])):
        for _, _, i in notes[:k]:
            hand_of[i] = "l"
        if notes[:k]:
            hands["lh"][start] = [(p, l) for p, l, _ in notes[:k]]
        if notes[k:]:
            hands["rh"][start] = [(p, l) for p, l, _ in notes[k:]]
    bpm = 60.0 / beat_step(beats)

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
    # Pedal marks go under the left hand (the right hand if the left is silent), from the first to the last
    # note struck while the pedal is down.
    rh_part, lh_part = score.parts
    pedal_part = lh_part if lh_part.recurse().notes else rh_part
    struck = sorted(((n.offset, n) for n in pedal_part.recurse().notes), key=lambda x: x[0])
    for down, up in pedals:
        lo = q(beat_pos([down], beats)[0])
        hi = q(beat_pos([up], beats)[0]) if np.isfinite(up) else float("inf")
        held = [n for o, n in struck if lo <= o < hi]
        if held:
            pedal_part.insert(0, expressions.PedalMark(held[0], held[-1]) if len(held) > 1
                              else expressions.PedalMark(held[0]))
    score.insert(0, layout.StaffGroup(list(score.parts), symbol="brace"))
    score = score.makeNotation()
    for part in score.parts:  # makeNotation numbers voices from 0; MusicXML readers expect 1, 2
        for m in part.getElementsByClass(stream.Measure):
            for i, v in enumerate(m.voices):
                v.id = str(i + 1)
    beat_sec = 60.0 / round(bpm)  # the score plays at the rounded metronome mark
    timing = [[round((j - origin) * beat_sec, 3), round(float(t), 3)] for j, t in enumerate(beats)]
    return score, k, bpm, hand_of, timing


class UserError(Exception):
    """A problem the user can fix; the message is shown to them as is."""


def render(xml_path, out_pdf, out_midi):
    """MusicXML -> (SVG pages, {note id: [start ms, end ms]}, bar start ms); also writes the PDF and a MIDI
    whose timing matches."""
    tk = verovio.toolkit(False)
    tk.setResourcePath(str(Path(verovio.__file__).parent / "data"))
    tk.setOptions({"pageWidth": 2100, "pageHeight": 2970, "scale": 40, "adjustPageHeight": False})
    tk.loadFile(str(xml_path))
    pages = [tk.renderToSVG(i + 1) for i in range(tk.getPageCount())]
    if not pages:
        raise UserError("Score rendering failed; the MusicXML download is still usable.")
    # Same toolkit -> SVG note ids, MIDI and timemap all agree, so playback and highlighting stay in sync.
    out_midi.write_bytes(base64.b64decode(tk.renderToMIDI()))
    notes, bars = {}, []
    for ev in tk.renderToTimemap({"includeMeasures": True, "includeRests": False}):
        if "measureOn" in ev:
            bars.append(ev["tstamp"])
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
    return pages, notes, bars


def files_url(path):
    """URL under /files for a file in WORK (the only folder the server exposes)."""
    return "/files/" + urllib.parse.quote(Path(path).resolve().relative_to(WORK).as_posix())


def player_html(pages, notes):
    """Score pages + note timings; the page highlights notes as they play and seeks on click."""
    data = html.escape(json.dumps([[i, s, e] for i, (s, e) in notes.items()]))
    sheets = "".join(f'<div class="follow-page">{s}</div>' for s in pages)
    return f'<div class="follow" data-notes="{data}">{sheets}</div>'


def transkun(audio, midi_path):
    """-> (note events, pedal spans) in the same shape the ByteDance engine gives."""
    subprocess.run([str(Path(sys.executable).parent / "transkun"), audio, str(midi_path)],
                   check=True, capture_output=True, timeout=1800)
    insts = pretty_midi.PrettyMIDI(str(midi_path)).instruments
    events = [{"onset_time": n.start, "offset_time": n.end, "midi_note": n.pitch, "velocity": n.velocity}
              for inst in insts for n in inst.notes]
    return events, pedal_from_cc([(c.time, c.value) for inst in insts for c in inst.control_changes if c.number == 64])


MAX_MINUTES = 20
AUDIO_TYPES = {".mp3", ".wav", ".m4a", ".flac", ".aiff", ".aif", ".ogg", ".webm", ".mp4"}


def is_link(text):
    """Only plain http(s) links reach yt-dlp (no options, no local paths)."""
    u = urllib.parse.urlparse(text.strip())
    return u.scheme in ("http", "https") and bool(u.netloc) and not text.strip().startswith("-")


def download(link, out):
    """Fetch the audio of a YouTube (or other yt-dlp supported) link as MP3; returns its path, named after the title."""
    if not is_link(link):
        raise UserError("That doesn't look like a link. Paste the full address, e.g. https://www.youtube.com/watch?v=…")
    done = subprocess.run(
        ["yt-dlp", "--no-playlist", "--no-progress", "-x", "--audio-format", "mp3",
         "--match-filter", f"duration <= {MAX_MINUTES * 60}", "--max-filesize", "200M",
         "-o", str(out / "%(title).120B.%(ext)s"), "--print", "after_move:filepath", "--", link.strip()],
        capture_output=True, text=True, timeout=900)
    path = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    if done.returncode or not Path(path).is_file():
        reason = (done.stderr.strip().splitlines() or ["the video was skipped"])[-1]
        if not path and not done.returncode:
            reason = f"the video is longer than {MAX_MINUTES} minutes"
        raise UserError(f"Couldn't get the audio from that link: {reason}")
    return path


def probe(path):
    """Audio facts for the file chip; raises UserError when the file isn't audio or is too long."""
    done = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=channels,sample_rate:format=duration", "-of", "json", str(path)],
                          capture_output=True, text=True, timeout=60)
    info = json.loads(done.stdout or "{}")
    if done.returncode or not info.get("streams"):
        raise UserError("That file doesn't contain audio we can read.")
    duration = float(info.get("format", {}).get("duration") or 0)
    if duration > MAX_MINUTES * 60:
        raise UserError(f"That recording is longer than {MAX_MINUTES} minutes. Trim it first.")
    st = info["streams"][0]
    return {"duration": duration, "channels": st.get("channels"), "sample_rate": int(st.get("sample_rate") or 0)}


STAGES = ["Loading audio", "Hearing the notes", "Finding the beat", "Writing the score",
          "Rendering notation", "Making playback audio"]
STAGE_WEIGHT = [0.05, 0.5, 0.12, 0.1, 0.15, 0.08]  # rough share of the total time, for the overall bar


def transcribe(source, engine="ByteDance", start=0.0, end=None, title=None, progress=lambda stage, detail=None, **data: None):
    """Audio file (optionally just start..end seconds) -> score, player and downloads.

    progress(i) starts stage i of STAGES; progress(i, detail, **data) adds what that stage found
    (data: roll, hands, preview) for the processing page.
    """
    out = Path(tempfile.mkdtemp(prefix="piano-", dir=WORK))
    audio = str(source)
    progress(0)
    if start > 0 or end:
        audio = str(out / "section.wav")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", str(start)] + (["-to", str(end)] if end else [])
                       + ["-i", str(source), audio], check=True, capture_output=True, timeout=600)
    y, _ = librosa.load(audio, sr=sample_rate, mono=True)
    progress(0, f"{fmt_time(len(y) / sample_rate)} of audio" + (" (selected section)" if audio != str(source) else ""))
    progress(1)
    raw_midi = out / "performance.mid"
    if engine == "Transkun":
        events, pedals = transkun(audio, raw_midi)
    else:
        global MODEL
        MODEL = MODEL or PianoTranscription(device=torch.device("cpu"))
        result = MODEL.transcribe(y, str(raw_midi))
        events = result["est_note_events"]
        pedals = [(p["onset_time"], p["offset_time"]) for p in result["est_pedal_events"]]
    if not len(events):
        raise UserError("No piano notes were found in this recording.")
    roll = [[round(float(e["onset_time"]), 2), round(float(e["offset_time"]), 2), int(e["midi_note"])] for e in events]  # plain floats: numpy ones break JSON
    progress(1, f"{len(events)} notes found", roll=roll, length=round(len(y) / sample_rate, 2))
    progress(2)
    global BEATS
    if BEATS is None:
        BEATS = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
    beats, downbeats = BEATS(audio)
    if len(beats) < 2:
        beats, downbeats = np.arange(0, len(y) / sample_rate + 0.5, 0.5), []  # no beat found: 120 BPM, 4/4
    even = fill_bars(beats, downbeats)
    progress(2, f"{meter_from(even, downbeats)[0]}/4 time · ♩ = {round(60 / beat_step(even))} · {len(pedals)} pedal presses")
    progress(3)
    score, k, bpm, hand_of, timing = to_score(events, beats, downbeats, pedals)
    meter_text = score.parts[0].recurse().getElementsByClass(meter.TimeSignature).first().ratioString
    key_text = f"{k.tonic.name.replace('-', '♭')} {k.mode}"
    score.insert(0, metadata.Metadata(title=title or Path(source).stem))
    xml = Path(score.write("musicxml", fp=out / "score.musicxml"))
    progress(3, f"Right hand {hand_of.count('r')} notes · left hand {hand_of.count('l')} notes · {key_text}",
             hands="".join(hand_of), key=key_text, meter=meter_text)
    progress(4)
    pdf, midi = out / "score.pdf", out / "score_two_hands.mid"
    pages, notes, bars = render(xml, pdf, midi)
    progress(4, f"{len(pages)} page{'s' * (len(pages) != 1)}", preview=pages[0])
    progress(5)
    mp3 = out / "score_piano.mp3"
    synth(midi, mp3)
    hand_audio, waterfall = {}, []
    for hand, path in split_hands(midi, out).items():
        hand_audio[hand] = out / f"score_{hand}.mp3"
        synth(path, hand_audio[hand])
        waterfall += [[round(n.start, 3), round(n.end, 3), n.pitch, hand[0]]
                      for inst in pretty_midi.PrettyMIDI(str(path)).instruments for n in inst.notes]
    progress(5, f"{fmt_time(max((e for _, e in notes.values()), default=0) / 1000)} of score audio")
    downloads = [("PDF", pdf), ("MusicXML", xml), ("Two-hand MIDI", midi), ("Score audio (MP3)", mp3),
                 ("Performance MIDI", raw_midi)]
    return {"engine": engine, "notes": len(events), "bpm": round(bpm), "meter": meter_text,
            "key": key_text, "title": title or Path(source).stem,
            "player": player_html(pages, notes),
            "studio": {"rh": files_url(hand_audio["rh"]), "lh": files_url(hand_audio["lh"]), "original": files_url(audio),
                       "notes": sorted(waterfall), "bars": [b / 1000 for b in bars], "timing": timing,
                       "bpm": round(bpm), "per_bar": int(meter_text.split("/")[0]),
                       "duration": max([n[1] for n in waterfall] + [0])},
            "downloads": [{"label": label, "url": files_url(p), "name": p.name} for label, p in downloads]}


def synth(midi, mp3):
    """MIDI -> MP3 with the piano soundfont."""
    wav = mp3.with_suffix(".wav")
    subprocess.run(["fluidsynth", "-ni", "-q", "-g", "0.8", "-r", "44100", "-F", str(wav), SOUNDFONT, str(midi)],
                   check=True, capture_output=True, timeout=600)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(wav), "-q:a", "3", str(mp3)],
                   check=True, capture_output=True, timeout=600)
    wav.unlink()


def split_hands(midi, out):
    """Verovio's MIDI has a tempo track then one track per staff (right hand, left hand) -> one MIDI per hand."""
    full = mido.MidiFile(str(midi))
    paths = {}
    for hand, track in (("rh", 1), ("lh", 2)):
        one = mido.MidiFile(ticks_per_beat=full.ticks_per_beat)
        one.tracks = [full.tracks[0]] + ([full.tracks[track]] if track < len(full.tracks) else [])
        paths[hand] = out / f"score_{hand}.mid"
        one.save(str(paths[hand]))
    return paths


def fmt_time(seconds):
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


# ---------------------------------------------------------------- web app

app = FastAPI(title="Piano to Score")
app.mount("/files", StaticFiles(directory=WORK), name="files")
SOURCES = {}  # source id -> (audio path, title)
JOBS = {}  # job id -> {"state", "progress", "stage", "result" | "error"}
RUN_LOCK = threading.Lock()  # ponytail: one conversion at a time (CPU-bound); a queue view if several users share it


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "web" / "index.html")


@app.post("/api/source")
async def add_source(file: UploadFile | None = None, link: str = Form("")):
    """Upload a file or fetch a link -> source id plus facts for the file chip and waveform."""
    folder = Path(tempfile.mkdtemp(prefix="src-", dir=WORK))
    try:
        if link.strip():
            path = Path(await run_in_threadpool(download, link, folder))
            title = path.stem
        elif file is not None and file.filename:
            ext = Path(file.filename).suffix.lower()
            if ext not in AUDIO_TYPES:
                raise UserError("Choose an audio file (MP3, WAV, M4A, FLAC or AIFF).")
            path, title, size = folder / f"source{ext}", Path(file.filename).stem, 0
            with open(path, "wb") as f:
                while chunk := await file.read(1 << 20):
                    size += len(chunk)
                    if size > 200 << 20:
                        raise UserError("That file is larger than 200 MB.")
                    f.write(chunk)
        else:
            raise UserError("Choose a recording or paste a link first.")
        info = await run_in_threadpool(probe, path)
    except UserError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    SOURCES[folder.name] = (path, title)
    return {"id": folder.name, "title": title, "url": files_url(path), **info}


class ConvertRequest(BaseModel):
    source: str
    engine: str = "ByteDance"
    start: float = 0.0
    end: float | None = None


class Cancelled(Exception):
    pass


@app.post("/api/convert")
def convert(req: ConvertRequest):
    if req.source not in SOURCES:
        return JSONResponse({"error": "Load a recording first."}, status_code=400)
    if req.engine not in ("ByteDance", "Transkun"):
        return JSONResponse({"error": "Unknown engine."}, status_code=400)
    path, title = SOURCES[req.source]
    job_id = uuid.uuid4().hex
    job = JOBS[job_id] = {"state": "queued", "progress": 0, "stage": -1, "cancel": False,
                          "stages": [{"name": n, "state": "pending", "seconds": None, "detail": ""} for n in STAGES]}
    began = {}

    def step(i, detail=None, **data):
        if job["cancel"]:
            raise Cancelled()
        now = time.monotonic()
        for j in range(i):  # everything before stage i is finished
            st = job["stages"][j]
            if st["state"] != "done":
                st.update(state="done", seconds=round(now - began.get(j, now), 1))
        if i < len(STAGES) and job["stages"][i]["state"] == "pending":
            began[i] = now
            job["stages"][i]["state"] = "active"
        if detail and i < len(STAGES):
            job["stages"][i]["detail"] = detail
        job.update(state="running", stage=i, progress=round(sum(STAGE_WEIGHT[:i]), 3), **data)

    def run():
        with RUN_LOCK:
            if job["cancel"]:
                job.update(state="cancelled")
                return
            try:
                result = transcribe(path, req.engine, max(0.0, req.start), req.end, title, step)
                step(len(STAGES))
                job.update(state="done", progress=1, result=result)
            except Cancelled:
                job.update(state="cancelled")
            except UserError as e:
                job.update(state="error", error=str(e))
            except Exception:
                traceback.print_exc()
                job.update(state="error", error="Conversion failed. Try the other engine or a shorter section.")

    threading.Thread(target=run, daemon=True).start()
    return {"job": job_id, "stages": STAGES}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        return JSONResponse({"error": "Unknown job."}, status_code=404)
    return {k: v for k, v in job.items() if k != "cancel"}


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str):
    """Stops at the next stage boundary (a stage already running finishes first)."""
    job = JOBS.get(job_id)
    if job is None:
        return JSONResponse({"error": "Unknown job."}, status_code=404)
    job["cancel"] = True
    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7861)
