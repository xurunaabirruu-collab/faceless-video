import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import streamlit as st

import agent

HERE = Path(__file__).parent.resolve()
RUNS = HERE / "runs"
RUNS.mkdir(exist_ok=True)

st.set_page_config(page_title="Faceless Video Maker", page_icon="🎬", layout="centered")
st.title("🎬 Faceless Video Maker")
st.caption("Mata-duree ykn script galchi → AI Agent script barreessa → sagalee + suuraa + subtitle → video")


def secret(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except Exception:
        return os.environ.get(name, default)


_pw = secret("APP_PASSWORD")
if _pw and st.text_input("Password", type="password") != _pw:
    st.info("Password galchi.")
    st.stop()

SAMPLE = (HERE / "script.txt").read_text(encoding="utf-8") if (HERE / "script.txt").exists() else ""
PROVIDERS = agent.PROVIDERS

# ---------- state durtii ----------
ss = st.session_state
ss.setdefault("script", SAMPLE)
ss.setdefault("meta", "")
ss.setdefault("agent_err", "")
ss.setdefault("provider", list(PROVIDERS)[0])
ss.setdefault("model", PROVIDERS[ss["provider"]][0])
ss.setdefault("akey", str(secret(PROVIDERS[ss["provider"]][1])))


def on_provider_change():
    m, sec = PROVIDERS[ss["provider"]]
    ss["model"] = m
    ss["akey"] = str(secret(sec))


def gen_script_cb():
    """Script qofa uumi: barreeffama keessa jiru mata-duree godhee script barreessa."""
    try:
        text, meta = agent.generate_script(
            ss["script"], ss["lang"], int(ss["nscenes"]), ss["style"],
            ss["provider"], ss["akey"].strip(), ss["model"].strip())
        ss["script"], ss["meta"], ss["agent_err"] = text, meta, ""
    except Exception as e:
        ss["agent_err"] = str(e)


# ---------- 1. Script ykn mata-duree ----------
st.text_area(
    "1) Mata-duree / prompt (AI barreessa) ykn script guutuu (sarara tokko = scene tokko; `barreeffama | jecha suuraa`)",
    key="script", height=240,
)
st.caption("Fakkeenya prompt: *Dhimmoota 8 waa'ee Itoophiyaa beekumsa hin beekne, Afaan Oromootiin*")

with st.expander("🤖 AI Agent (script barreessuuf)", expanded=False):
    c1, c2 = st.columns(2)
    c1.selectbox("Afaan script", agent.LANGUAGES, key="lang")
    c2.selectbox("Gosa", list(agent.STYLES), key="style")
    st.slider("Lakkoofsa scene", 3, 15, 8, key="nscenes")
    st.selectbox("AI provider", list(PROVIDERS), key="provider", on_change=on_provider_change)
    st.text_input("Model", key="model")
    st.text_input("API key (AI)", key="akey", type="password",
                  help="Gemini: aistudio.google.com/apikey (bilisaan). Groq: console.groq.com (bilisaan).")

st.button("✨ Script qofa uumi (edit gochuuf)", on_click=gen_script_cb, use_container_width=True)
if ss["agent_err"]:
    st.error(ss["agent_err"])
if ss["meta"]:
    with st.expander("📋 Title / Description / Hashtags (upload gochuuf)", expanded=True):
        st.code(ss["meta"], language=None)

st.divider()

# ---------- 2. Video settings ----------
c1, c2 = st.columns(2)
fmt = c1.selectbox("Format", ["landscape", "vertical"],
                   format_func=lambda x: "YouTube (16:9)" if x == "landscape" else "TikTok / Shorts (9:16)")
voice = c2.selectbox("Sagalee AI", [
    "en-US-GuyNeural", "en-US-AriaNeural", "en-US-JennyNeural",
    "en-GB-RyanNeural", "en-GB-SoniaNeural", "am-ET-MekdesNeural",
])
rate = st.select_slider("Saffisa sagalee", ["-20%", "-10%", "+0%", "+10%", "+20%"], value="+0%")

MODE_AI = "Sagalee AI (Ingiliffaa/Amaariffaa; olitti filadhu)"
MODE_OWN = "Sagalee kiyya (Afaan Oromoo; ofiin galmeessee upload)"
MODE_SUB = "Subtitle qofa (sagalee hin qabu)"
mode = st.radio("Gosa sagalee", [MODE_AI, MODE_OWN, MODE_SUB])
audio_files = None
if mode == MODE_OWN:
    st.caption("Scene tokkoof faayilii sagalee tokko. Maqaan lakkoofsaan jalqabu: "
               "01.mp3, 02.mp3, 03.mp3 ... Lakkoofsi faayilii = lakkoofsa scene.")
    audio_files = st.file_uploader("Faayilota sagalee", accept_multiple_files=True,
                                   type=["mp3", "wav", "m4a", "ogg", "aac", "opus"])
if mode == MODE_AI and ss.get("lang") == "Afaan Oromoo":
    st.warning("Sagalee AI Afaan Oromoo hin qabu. 'Sagalee kiyya' ykn 'Subtitle qofa' filadhu.")
if mode != MODE_AI:
    st.info("Suuraaf, sarara tokko tokko irratti `|` booda jecha **Ingiliffaa** barreessi "
            "(fkn `... | farmer field`). AI Agent kana ofumaan godha.")

VIS_STOCK = "Suuraa stock (Pixabay; bilisaan)"
VIS_AIIMG = "Suuraa AI (scene hundaaf AI uuma)"
VIS_AIVID = "Video AI (clip sochii; credit fayyadama)"
visuals = st.radio("Visual (suuraa / video)", [VIS_STOCK, VIS_AIIMG, VIS_AIVID])
poll_key, video_model, clip_secs = "", "wan-fast", 5
if visuals != VIS_STOCK:
    poll_key = st.text_input("Pollinations API key", value=secret("POLLINATIONS_API_KEY"),
                             type="password", help="Bilisaan galmaa'i: enter.pollinations.ai")
    st.caption("Key argachuuf: **enter.pollinations.ai** galmaa'i. Credit (Pollen) dursa kennamu hanga "
               "xumuramutti qofa hojjeta; booda kaffaltii barbaada.")
if visuals == VIS_AIVID:
    video_model = st.text_input("Model video", value="wan-fast",
                                help="Filannoo: wan-fast, seedance, veo. Tarree: gen.pollinations.ai/video/models")
    clip_secs = st.slider("Dheerina clip (sekondii)", 3, 8, 5)
    st.warning("Video AI scene tokkoof daqiiqaa 0.5-2 fudhata. Scene 3-5 qofa fayyadami; "
               "scene baay'ee yoo ta'e yeroon dheeraa fi credit hedduu xumurama.")

STYLE_PRESETS = {
    "Cinematic realistic": "cinematic, realistic, high detail, no text",
    "3D explainer animation (science/medical)": "3D animated render, vibrant colors, macro shot, "
                                                "shallow depth of field, educational explainer style, no text",
    "Cartoon illustration": "colorful flat cartoon illustration, clean shapes, no text",
}
style_name = list(STYLE_PRESETS)[0]
if visuals != VIS_STOCK:
    style_name = st.selectbox("Bifa visual AI", list(STYLE_PRESETS))
cut_secs = st.slider("Suuraa sekondii meeqa keessatti jijjiiramu (cut)", 2.0, 8.0, 3.5, 0.5,
                     help="Xiqqaa ta'e = suuraan saffisaan jijjiirama (video explainer fakkaata). "
                          "Video AI irratti xiqqaa ta'e credit hedduu fayyadama.")
cap_words = st.slider("Subtitle tokko keessatti jechoota", 1, 4, 3)

pix_key = st.text_input("Pixabay API key (suuraaf, filannoo)",
                        value=secret("PIXABAY_API_KEY"), type="password")
music = st.file_uploader("Muuziqa duubaa (filannoo, mp3)", type=["mp3"])

# ---------- 3. Video uumi ----------
if st.button("🚀 Video uumi", type="primary", use_container_width=True):
    final_script = ss["script"]
    if not final_script.strip():
        st.error("Mata-duree ykn script barreessi.")
        st.stop()

    # Prompt yoo ta'e (script osoo hin taane), AI Agent ofumaan script barreessa
    if agent.looks_like_prompt(final_script):
        with st.status("🤖 AI Agent script barreessaa jira...", expanded=False) as s:
            try:
                final_script, meta = agent.generate_script(
                    final_script, ss["lang"], int(ss["nscenes"]), ss["style"],
                    ss["provider"], ss["akey"].strip(), ss["model"].strip())
                ss["meta"] = meta
                s.update(label="Script qophaa'eera ✅", state="complete")
            except Exception as e:
                s.update(label="AI Agent dogoggora ❌", state="error")
                st.error(str(e))
                st.stop()
        with st.expander("📝 Script AI uume", expanded=False):
            st.code(final_script, language=None)
        if meta:
            with st.expander("📋 Title / Description / Hashtags", expanded=True):
                st.code(meta, language=None)

    n_scenes = agent.count_scenes(final_script)
    if mode == MODE_OWN:
        if not audio_files:
            st.error("Faayilota sagalee upload godhi.")
            st.stop()
        if len(audio_files) != n_scenes:
            st.error(f"Scene {n_scenes} jira, garuu faayilii sagalee {len(audio_files)} upload goote.")
            st.stop()

    run_dir = RUNS / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "script.txt").write_text(final_script, encoding="utf-8")

    cmd = [sys.executable, str(HERE / "faceless.py"), "script.txt",
           "--format", fmt, "--voice", ("none" if mode == MODE_SUB else voice),
           "--rate", rate, "--out", "output.mp4"]
    cmd += ["--cut-seconds", str(cut_secs), "--caption-words", str(cap_words)]
    if visuals != VIS_STOCK:
        cmd += ["--style", STYLE_PRESETS[style_name]]
    if visuals == VIS_AIIMG:
        cmd += ["--visuals", "ai-image"]
    elif visuals == VIS_AIVID:
        cmd += ["--visuals", "ai-video", "--video-model", video_model.strip() or "wan-fast",
                "--clip-seconds", str(clip_secs)]
    if mode == MODE_OWN:
        adir = run_dir / "audio"
        adir.mkdir()
        for f in audio_files:
            (adir / Path(f.name).name).write_bytes(f.getvalue())
        cmd += ["--audio-dir", "audio"]
    if music is not None:
        (run_dir / "music.mp3").write_bytes(music.getvalue())
    env = {**os.environ, "PIXABAY_API_KEY": pix_key.strip(),
           "POLLINATIONS_API_KEY": poll_key.strip(),
           "PEXELS_API_KEY": str(secret("PEXELS_API_KEY"))}

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
        st.error("Video hin uumamne. Ergaa olii ilaali.")
