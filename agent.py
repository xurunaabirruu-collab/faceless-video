"""
AI Agent: mata-duree (prompt) -> script scene-scene + jecha suuraa + Title/Description/Hashtags.
Provider sadii: Gemini (bilisaan), Groq (bilisaan), Claude (kaffaltii).
"""
import re

import requests

# provider: (model durtii, maqaa secret)
PROVIDERS = {
    "Gemini (bilisaan)": ("gemini-3.8-flash", "GEMINI_API_KEY"),
    "Groq (bilisaan)": ("llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "Claude (kaffaltii)": ("claude-haiku-5-5", "ANTHROPIC_API_KEY"),
}

STYLES = {
    "Did You Know / Facts": "Surprising, TRUE facts. Open with a hook question. One fact per scene.",
    "Motivational": "Short, powerful motivational talk. Emotional, direct, builds to a strong ending.",
    "Story": "A short story with a clear beginning, middle and end. Each scene moves the story forward.",
    "Educational explainer": "Clear step-by-step explanation of the topic for beginners, with simple examples.",
}

LANGUAGES = ["English", "Afaan Oromoo"]


def count_scenes(text):
    return len([l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")])


def looks_like_prompt(text):
    """True yoo barreeffamni script osoo hin taane mata-duree/prompt gabaabaa ta'e."""
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return False
    if any("|" in l for l in lines):
        return False
    return len(lines) < 4


def build_prompts(topic, language, scenes, style):
    if language == "Afaan Oromoo":
        lang_rule = ("Write the NARRATION in Afaan Oromoo, using Latin script (Qubee). "
                     "Use simple, natural spoken sentences. If you are unsure of a word, use a simpler one.")
    else:
        lang_rule = "Write the NARRATION in clear, natural spoken English."

    system = f"""You are an expert scriptwriter for short faceless videos (YouTube, TikTok) and a careful fact-checker.
The user's request may be written in any language (Afaan Oromoo, Amharic, English). Understand it fully.

OUTPUT FORMAT (follow exactly, no commentary before or after):
- Exactly {scenes} lines. One scene per line, in this format:
  NARRATION | ENGLISH KEYWORDS
- NARRATION: 15 to 30 words, spoken style. No numbering, bullets, quotes, emojis or stage directions.
- Scene 1 must be a strong hook. The last scene is a short call to action (like, follow, comment).
- ENGLISH KEYWORDS: 2 or 3 concrete English words describing a visual for a stock photo search
  (e.g. "volcano eruption", "old library"). Always English, always concrete, never abstract.
- {lang_rule}
- Only include facts you are confident are true. Skip anything uncertain.

After the last scene, add a line containing only ###META and then exactly these three lines
(written in the same language as the NARRATION):
TITLE: <catchy title under 70 characters>
DESCRIPTION: <2 to 3 sentences>
HASHTAGS: <8 to 12 hashtags separated by spaces>"""
    user = f"Topic / request: {topic}\nStyle: {STYLES.get(style, style)}\nNumber of scenes: {scenes}"
    return system, user


def _check(r):
    if r.status_code != 200:
        raise RuntimeError(f"API dogoggora {r.status_code}: {r.text[:300]}")
    return r.json()


def _gemini_post(key, model, system, user, timeout):
    return requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"systemInstruction": {"parts": [{"text": system}]},
              "contents": [{"role": "user", "parts": [{"text": user}]}],
              "generationConfig": {"temperature": 0.8}},
        timeout=timeout)


def _gemini_pick_model(key, timeout=30):
    """Model 'gemini-X-flash' isa haaraa (generateContent deeggaru) barbaada."""
    try:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                         headers={"x-goog-api-key": key},
                         params={"pageSize": 200}, timeout=timeout)
        if r.status_code != 200:
            return None
        best, best_v = None, -1.0
        for m in r.json().get("models", []):
            name = m.get("name", "").replace("models/", "")
            mt = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash", name)
            if mt and "generateContent" in m.get("supportedGenerationMethods", []):
                v = float(mt.group(1))
                if v > best_v:
                    best, best_v = name, v
        return best
    except Exception:
        return None


def call_llm(provider, key, model, system, user, timeout=90):
    if not key:
        raise RuntimeError("API key hin galchine. Settings (AI Agent) keessatti key galchi.")
    if provider.startswith("Gemini"):
        r = _gemini_post(key, model, system, user, timeout)
        if r.status_code == 404:  # model dhaabbateera: model haaraa ofumaan barbaadi
            alt = _gemini_pick_model(key)
            if alt and alt != model:
                r = _gemini_post(key, alt, system, user, timeout)
        data = _check(r)
        try:
            return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError):
            raise RuntimeError(f"Gemini deebii duwwaa deebise: {str(data)[:300]}")
    if provider.startswith("Groq"):
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "User-Agent": "Mozilla/5.0"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=timeout)
        return _check(r)["choices"][0]["message"]["content"]
    if provider.startswith("Claude"):
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": model, "max_tokens": 2500, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=timeout)
        return "".join(b.get("text", "") for b in _check(r)["content"] if b.get("type") == "text")
    raise RuntimeError(f"Provider hin beekamne: {provider}")


def clean_script(raw):
    """Deebii LLM -> (script_text, meta_text)."""
    raw = raw.replace("```text", "").replace("```", "").replace("｜", "|")
    parts = re.split(r"#{2,3}\s*META", raw, maxsplit=1, flags=re.I)
    body = parts[0]
    meta = parts[1].strip() if len(parts) > 1 else ""
    lines = []
    for line in body.splitlines():
        line = re.sub(r"^\s*(\d+[\.\)]|[-*•])\s*", "", line.strip())
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            text, kw = line.rsplit("|", 1)
            line = f"{text.strip()} | {kw.strip()}"
        lines.append(line)
    return "\n".join(lines), meta


def generate_script(topic, language, scenes, style, provider, key, model):
    topic = topic.strip()
    if not topic:
        raise RuntimeError("Mata-duree ykn prompt barreessi.")
    system, user = build_prompts(topic, language, scenes, style)
    raw = call_llm(provider, key, model, system, user)
    script, meta = clean_script(raw)
    if not script:
        raise RuntimeError("AI script hin kennine. Irra deebi'ii yaali.")
    return script, meta
