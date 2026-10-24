#!/usr/bin/env python3
"""
Faceless Video Generator
script.txt (sceneen tokkoon tokko sarara) -> sagalee AI -> suuraa Pexels -> subtitle -> video.mp4

Sararri tokko = scene tokko.  Format:
    Barreeffama sagaleessuu | jecha barbaaddachuu (filannoo)

Fakkeenya:
    Did you know honey never spoils? | honey jar
"""
import argparse
import asyncio
import os
import random
import re
import subprocess
import sys
from pathlib import Path

import edge_tts
import requests
from urllib.parse import quote

SIZES = {"landscape": (1920, 1080), "vertical": (1080, 1920)}
FPS = 30
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
POLL_KEY = os.environ.get("POLLINATIONS_API_KEY", "")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit("\nHim'anni uumame (ffmpeg). Ergaa olii dubbisi.")
    return r.stdout


def audio_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def parse_script(path):
    scenes = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        text = parts[0]
        kw = parts[1] if len(parts) > 1 else ""
        vp = parts[2] if len(parts) > 2 else ""
        if not kw:
            words = sorted(set(re.findall(r"[A-Za-z]{4,}", text)), key=len, reverse=True)
            kw = " ".join(words[:2])
        scenes.append((text, kw, vp or kw))
    return scenes


async def tts(text, voice, rate, out):
    """Sagalee uuma; yeroo jecha tokkoo tokkoo (boundaries) deebisa."""
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    except TypeError:  # edge-tts durii
        comm = edge_tts.Communicate(text, voice, rate=rate)
    bounds = []
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            kind = chunk.get("type")
            if kind == "audio":
                f.write(chunk["data"])
            elif kind in ("WordBoundary", "SentenceBoundary"):
                start = chunk["offset"] / 1e7
                bounds.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return bounds


def words_from_boundaries(bounds, text):
    """(start, end, text) -> jecha tokkoo tokkoo. Yoo sarara guutuu ta'e, jechootatti qooda."""
    words = []
    for s0, e0, t in bounds:
        ws = t.split()
        if len(ws) <= 1:
            words.append((s0, e0, t))
            continue
        total = sum(len(w) for w in ws) or 1
        pos = s0
        for w in ws:
            d = (e0 - s0) * len(w) / total
            words.append((pos, pos + d, w))
            pos += d
    script_words = text.split()
    if words and len(words) == len(script_words):  # mallattoo (? , .) deebisi
        words = [(a, b, w) for (a, b, _), w in zip(words, script_words)]
    return words or None


def make_audio(text, args, src, dest):
    """src = faayilii sagalee kee (yoo jiraate); voice 'none' = sagalee malee, subtitle qofa."""
    if src:
        run(["ffmpeg", "-y", "-i", str(src), "-ar", "44100", "-ac", "2",
             "-c:a", "libmp3lame", str(dest)])
    elif args.voice.lower() == "none":
        secs = max(2.0, len(text.split()) / 2.3)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", f"{secs:.2f}", "-c:a", "libmp3lame", str(dest)])
    else:
        bounds = asyncio.run(tts(text, args.voice, args.rate, dest))
        return words_from_boundaries(bounds, text)
    return None


def fetch_pixabay(query, orientation, used, dest):
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={"key": PIXABAY_KEY, "q": query, "image_type": "photo",
                    "orientation": "horizontal" if orientation == "landscape" else "vertical",
                    "per_page": 10, "safesearch": "true"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        hits = [h for h in r.json().get("hits", []) if h["id"] not in used]
        if not hits:
            return None
        h = random.choice(hits[:6])
        used.add(h["id"])
        dest.write_bytes(requests.get(h["largeImageURL"],
                                      headers={"User-Agent": "Mozilla/5.0"},
                                      timeout=60).content)
        return dest
    except Exception as e:
        print(f"   (Pixabay: suuraan hin argamne: {e})")
        return None


def fetch_image(query, orientation, used, dest):
    if PIXABAY_KEY and query:
        img = fetch_pixabay(query, orientation, used, dest)
        if img:
            return img
    if not PEXELS_KEY or not query:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_KEY},
            params={"query": query, "orientation": orientation, "per_page": 8},
            timeout=30,
        )
        photos = [p for p in r.json().get("photos", []) if p["id"] not in used]
        if not photos:
            return None
        p = random.choice(photos[:5])
        used.add(p["id"])
        dest.write_bytes(requests.get(p["src"]["large2x"], timeout=60).content)
        return dest
    except Exception as e:
        print(f"   (suuraan hin argamne: {e})")
        return None


def _poll_headers():
    h = {"User-Agent": "Mozilla/5.0"}
    if POLL_KEY:
        h["Authorization"] = f"Bearer {POLL_KEY}"
    return h


def ai_image(prompt, size, dest):
    """Suuraa AI (Pollinations, model flux)."""
    W, H = size
    w, h = (1280, 720) if W > H else (720, 1280)
    try:
        r = requests.get(f"https://gen.pollinations.ai/image/{quote(prompt)}",
                         params={"model": "flux", "width": w, "height": h,
                                 "nologo": "true", "seed": random.randint(1, 10**6)},
                         headers=_poll_headers(), timeout=180)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image") \
                and len(r.content) > 1000:
            dest.write_bytes(r.content)
            return dest
        print(f"   (AI suuraa: {r.status_code} {r.text[:120]})")
    except Exception as e:
        print(f"   (AI suuraa dogoggora: {e})")
    return None


def ai_video(prompt, size, dest, model, seconds):
    """Clip video AI (Pollinations). Credit fayyadama."""
    W, H = size
    ar = "16:9" if W > H else "9:16"
    for params in ({"model": model, "duration": seconds, "aspectRatio": ar},
                   {"model": model, "aspectRatio": ar}):
        try:
            r = requests.get(f"https://gen.pollinations.ai/video/{quote(prompt)}",
                             params=params, headers=_poll_headers(), timeout=420)
        except Exception as e:
            print(f"   (AI video dogoggora: {e})")
            return None
        if r.status_code == 200 and (r.headers.get("content-type", "").startswith("video")
                                     or r.content[4:8] == b"ftyp"):
            dest.write_bytes(r.content)
            return dest
        print(f"   (AI video: {r.status_code} {r.text[:120]})")
    return None


def ts(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


TAIL = 0.35  # callee dhuma scene


def make_srt(text, dur, path, words=None, per=3):
    """Subtitle: jecha 1-3 tokkoon tokkoon; yeroo jecha sagalee waliin wal-simata."""
    if not words:  # yeroo jecha hin jiru: dheerina jecha irratti hundaa'ee qoodi
        ws = text.split()
        total = sum(len(w) for w in ws) or 1
        t, words = 0.0, []
        for w in ws:
            d = dur * len(w) / total
            words.append((t, t + d, w))
            t += d
    chunks, cur = [], []
    for s0, e0, w in words:
        cur.append((s0, e0, w))
        if len(cur) >= per or re.search(r"[.,!?;:]$", w):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        start = c[0][0]
        end = chunks[i + 1][0][0] if i + 1 < len(chunks) else max(c[-1][1], dur)
        if end <= start:
            end = start + 0.3
        out.append(f"{i + 1}\n{ts(start)} --> {ts(end)}\n{' '.join(w for _, _, w in c)}\n")
    Path(path).write_text("\n".join(out), encoding="utf-8")


def pick_media(args, size, orientation, work, i, k, kw, vp, used):
    """Segment tokkoof (gosa, faayilii) deebisa: clip AI, suuraa AI, suuraa stock, ykn halluu."""
    full = f"{vp}, {args.style}" if args.style else vp
    if args.visuals == "ai-video":
        p = ai_video(full, size, work / f"m{i:03}_{k}.mp4", args.video_model, args.clip_seconds)
        if p:
            return ("clip", p)
    if args.visuals in ("ai-video", "ai-image"):
        p = ai_image(full, size, work / f"m{i:03}_{k}.jpg")
        if p:
            return ("img", p)
    p = fetch_image(kw, orientation, used, work / f"m{i:03}_{k}.jpg")
    if p:
        return ("img", p)
    return ("color", None)


def render_scene(idx, segments, audio, speech_dur, size, work):
    """Scene tokko: segment baay'ee (cut saffisaa) + sagalee + subtitle."""
    W, H = size
    total = speech_dur + TAIL
    n = len(segments)
    seg = total / n
    frames = max(2, int(round(seg * FPS)))
    fs, mv = (14, 25) if W > H else (10, 62)
    style = (f"FontName=Arial,FontSize={fs},Bold=1,PrimaryColour=&H00FFFFFF,"
             f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
             f"Alignment=2,MarginV={mv}")
    sub = f"subtitles=s{idx:03}.srt:force_style='{style}'"
    out = f"s{idx:03}.mp4"

    inputs, chains = [], []
    for k, (kind, path) in enumerate(segments):
        if kind == "clip":
            inputs += ["-stream_loop", "-1", "-i", path.name]
            chains.append(f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                          f"crop={W}:{H},setsar=1,fps={FPS},trim=duration={seg:.3f},"
                          f"setpts=PTS-STARTPTS[v{k}]")
        elif kind == "img":
            z = "min(1.3,1+0.0012*on)" if k % 2 == 0 else "max(1.0,1.3-0.0012*on)"
            inputs += ["-i", path.name]
            chains.append(f"[{k}:v]scale={2*W}:{2*H}:force_original_aspect_ratio=increase,"
                          f"crop={2*W}:{2*H},zoompan=z='{z}':x='iw/2-(iw/zoom/2)'"
                          f":y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1[v{k}]")
        else:
            inputs += ["-f", "lavfi", "-i", f"color=c=0x16213e:s={W}x{H}:r={FPS}:d={seg:.3f}"]
            chains.append(f"[{k}:v]setsar=1[v{k}]")
    labels = "".join(f"[v{k}]" for k in range(n))
    chains.append(f"{labels}concat=n={n}:v=1:a=0[cv]")
    chains.append(f"[cv]tpad=stop_mode=clone:stop_duration=0.5,eq=brightness=-0.05,{sub}[vout]")

    cmd = ["ffmpeg", "-y", *inputs, "-i", audio.name,
           "-filter_complex", ";".join(chains), "-af", "apad",
           "-map", "[vout]", "-map", f"{n}:a", "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", out]
    run(cmd, cwd=work)
    return out


def main():
    ap = argparse.ArgumentParser(description="Faceless video generator")
    ap.add_argument("script", help="faayilii script.txt")
    ap.add_argument("--format", choices=SIZES, default="landscape",
                    help="landscape = YouTube, vertical = TikTok/Shorts")
    ap.add_argument("--voice", default="en-US-GuyNeural")
    ap.add_argument("--rate", default="+0%", help="saffisa sagalee, fkn -10%% ykn +10%%")
    ap.add_argument("--visuals", choices=["stock", "ai-image", "ai-video"], default="stock",
                    help="stock = Pixabay, ai-image = suuraa AI, ai-video = clip video AI")
    ap.add_argument("--video-model", default="wan-fast")
    ap.add_argument("--clip-seconds", type=int, default=5)
    ap.add_argument("--style", default="cinematic, realistic, high detail, no text",
                    help="halluu/bifa walfakkaataa scene hundaaf (AI visuals)")
    ap.add_argument("--cut-seconds", type=float, default=3.5,
                    help="suuraa/clip sekondii meeqa keessatti jijjiiramu (0 = scene tokkoof suuraa tokko)")
    ap.add_argument("--caption-words", type=int, default=3,
                    help="subtitle tokko keessatti jechoota hamma meeqa (1-4)")
    ap.add_argument("--audio-dir", default=None,
                    help="folder sagalee kee (01.mp3, 02.mp3 ... scene tokkoon tokko)")
    ap.add_argument("--music", default="music.mp3", help="muuziqa duubaa (filannoo)")
    ap.add_argument("--out", default="output.mp4")
    args = ap.parse_args()

    size = SIZES[args.format]
    orientation = "landscape" if args.format == "landscape" else "portrait"
    work = Path("work")
    work.mkdir(exist_ok=True)

    scenes = parse_script(args.script)
    if not scenes:
        sys.exit("Script duwwaadha.")
    if not (PIXABAY_KEY or PEXELS_KEY):
        print("! PIXABAY_API_KEY hin kaa'amne: suuraa osoo hin taane duubbee halluu fayyadama.\n")

    audio_files = []
    if args.audio_dir:
        exts = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".opus", ".webm", ".mp4"}
        audio_files = sorted(
            (p for p in Path(args.audio_dir).iterdir() if p.suffix.lower() in exts),
            key=lambda p: [int(t) if t.isdigit() else t.lower()
                           for t in re.split(r"(\d+)", p.name)])
        if len(audio_files) != len(scenes):
            sys.exit(f"Scene {len(scenes)} jira, garuu faayilii sagalee {len(audio_files)} qofa. "
                     "Lakkoofsi isaanii wal gita qaba.")

    if args.visuals != "stock" and not POLL_KEY:
        print("! POLLINATIONS_API_KEY hin kaa'amne: AI visual hin hojjetu ta'a; suuraa stock fayyadama.\n")

    used, clips = set(), []
    for i, (text, kw, vp) in enumerate(scenes, 1):
        print(f"[{i}/{len(scenes)}] {text[:60]}...")
        audio = work / f"a{i:03}.mp3"
        words = make_audio(text, args, audio_files[i - 1] if audio_files else None, audio)
        dur = audio_duration(audio)
        make_srt(text, dur, work / f"s{i:03}.srt", words, max(1, args.caption_words))
        total = dur + TAIL
        n_seg = 1 if args.cut_seconds <= 0 else max(1, min(8, round(total / args.cut_seconds)))
        kws = [x.strip() for x in kw.split(";") if x.strip()] or [kw]
        vps = [x.strip() for x in vp.split(";") if x.strip()] or [vp]
        segments = [pick_media(args, size, orientation, work, i, k,
                               kws[k % len(kws)], vps[k % len(vps)], used)
                    for k in range(n_seg)]
        clips.append(render_scene(i, segments, audio, dur, size, work))

    (work / "list.txt").write_text("".join(f"file '{c}'\n" for c in clips))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
         "-c", "copy", "joined.mp4"], cwd=work)

    out = Path(args.out).resolve()
    music = Path(args.music)
    if music.exists():
        print("Muuziqa duubaa dabalaa jira...")
        run(["ffmpeg", "-y", "-i", str(work / "joined.mp4"), "-stream_loop", "-1",
             "-i", str(music), "-filter_complex",
             "[1:a]volume=0.08[m];[0:a][m]amix=inputs=2:duration=first[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
             "-shortest", str(out)])
    else:
        (work / "joined.mp4").replace(out)

    print(f"\nXumurameera: {out}")


if __name__ == "__main__":
    main()
