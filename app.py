import os
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st

HERE = Path(__file__).parent.resolve()
RUNS = HERE / "runs"
RUNS.mkdir(exist_ok=True)

st.set_page_config(page_title="Faceless Video Maker", page_icon="🎬", layout="centered")
st.title("🎬 Faceless Video Maker")
st.caption("Script galchi → sagalee AI + suuraa + subtitle → video xumuramee")

SAMPLE = (HERE / "script.txt").read_text(encoding="utf-8") if (HERE / "script.txt").exists() else ""

script = st.text_area(
    "Script (sarara tokko = scene tokko; filannoo: `barreeffama | jecha suuraa`)",
    value=SAMPLE, height=260,
)

c1, c2 = st.columns(2)
fmt = c1.selectbox("Format", ["landscape", "vertical"],
                   format_func=lambda x: "YouTube (16:9)" if x == "landscape" else "TikTok / Shorts (9:16)")
voice = c2.selectbox("Sagalee", [
    "en-US-GuyNeural", "en-US-AriaNeural", "en-US-JennyNeural",
    "en-GB-RyanNeural", "en-GB-SoniaNeural", "am-ET-MekdesNeural",
])
rate = st.select_slider("Saffisa sagalee", ["-20%", "-10%", "+0%", "+10%", "+20%"], value="+0%")
key = st.text_input("Pexels API key (suuraaf, filannoo)",
                    value=os.environ.get("PEXELS_API_KEY", ""), type="password")
music = st.file_uploader("Muuziqa duubaa (filannoo, mp3)", type=["mp3"])

if st.button("🚀 Video uumi", type="primary", use_container_width=True):
    if not script.strip():
        st.error("Script duwwaadha.")
        st.stop()

    run_dir = RUNS / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir()
    (run_dir / "script.txt").write_text(script, encoding="utf-8")

    cmd = [sys.executable, str(HERE / "faceless.py"), "script.txt",
           "--format", fmt, "--voice", voice, "--rate", rate, "--out", "output.mp4"]
    if music is not None:
        (run_dir / "music.mp3").write_bytes(music.getvalue())
    env = {**os.environ, "PEXELS_API_KEY": key.strip()}

    with st.status("Video uumamaa jira... (daqiiqaa muraasa fudhata)", expanded=True) as status:
        log = st.empty()
        proc = subprocess.Popen(cmd, cwd=run_dir, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        lines = []
        for line in proc.stdout:
            lines.append(line.rstrip())
            log.code("\n".join(lines[-12:]))
        proc.wait()
        if proc.returncode == 0 and (run_dir / "output.mp4").exists():
            status.update(label="Xumurameera ✅", state="complete")
        else:
            status.update(label="Dogoggora uumame ❌", state="error")

    out = run_dir / "output.mp4"
    if out.exists():
        st.video(str(out))
        st.download_button("⬇️ Video buusi (MP4)", out.read_bytes(),
                           file_name="video.mp4", mime="video/mp4",
                           use_container_width=True)
    else:
        st.error("Video hin uumamne. Ergaa olii ilaali (ffmpeg install godhameeraa?).")
