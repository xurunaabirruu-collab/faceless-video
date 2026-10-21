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

SIZES = {"landscape": (1920, 1080), "vertical": (1080, 1920)}
FPS = 30
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")


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
        if "|" in line:
            text, kw = [p.strip() for p in line.split("|", 1)]
        else:
            text, kw = line, ""
        if not kw:
            words = sorted(set(re.findall(r"[A-Za-z]{4,}", text)), key=len, reverse=True)
            kw = " ".join(words[:2])
        scenes.append((text, kw))
    return scenes


async def tts(text, voice, rate, out):
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def fetch_image(query, orientation, used, dest):
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


def ts(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def make_srt(text, dur, path):
    words = text.split()
    chunks = [" ".join(words[i:i + 4]) for i in range(0, len(words), 4)]
    total = sum(len(c) for c in chunks) or 1
    t, out = 0.0, []
    for i, c in enumerate(chunks, 1):
        d = dur * len(c) / total
        out.append(f"{i}\n{ts(t)} --> {ts(t + d)}\n{c}\n")
        t += d
    Path(path).write_text("\n".join(out), encoding="utf-8")


def render_scene(idx, img, audio, speech_dur, size, work):
    W, H = size
    total = speech_dur + 0.4
    frames = int(total * FPS)
    fs, mv = (16, 50) if W > H else (11, 160)
    style = (f"FontName=Arial,FontSize={fs},Bold=1,PrimaryColour=&H00FFFFFF,"
             f"OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
             f"Alignment=2,MarginV={mv}")
    sub = f"subtitles=s{idx:03}.srt:force_style='{style}'"
    out = f"s{idx:03}.mp4"

    if img:
        inp = ["-i", img.name]
        vf = (f"scale={2*W}:{2*H}:force_original_aspect_ratio=increase,crop={2*W}:{2*H},"
              f"zoompan=z='min(zoom+0.0007,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d={frames}:s={W}x{H}:fps={FPS},eq=brightness=-0.08,{sub}")
    else:
        inp = ["-f", "lavfi", "-i", f"color=c=0x16213e:s={W}x{H}:r={FPS}"]
        vf = sub

    cmd = ["ffmpeg", "-y", *inp, "-i", audio.name,
           "-vf", vf, "-af", "apad", "-map", "0:v", "-map", "1:a",
           "-t", f"{total:.3f}",
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
    ap.add_argument("--rate", default="+0%", help="saffisa sagalee, fkn -10% ykn +10%")
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
    if not PEXELS_KEY:
        print("! PEXELS_API_KEY hin kaa'amne: suuraa osoo hin taane duubbee halluu fayyadama.\n")

    used, clips = set(), []
    for i, (text, kw) in enumerate(scenes, 1):
        print(f"[{i}/{len(scenes)}] {text[:60]}...")
        audio = work / f"a{i:03}.mp3"
        asyncio.run(tts(text, args.voice, args.rate, audio))
        dur = audio_duration(audio)
        make_srt(text, dur, work / f"s{i:03}.srt")
        img = fetch_image(kw, orientation, used, work / f"i{i:03}.jpg")
        clips.append(render_scene(i, img, audio, dur, size, work))

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
