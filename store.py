"""
History (video durii) + Telegram backup.
- Video hunda runs/<id>/ keessatti meta.json waliin kuufama (app yeroo rafu/haaromfamu haqamuu danda'a).
- Telegram: video fi script bot kee irraa chat kee tti ergama (dhaabbataa; Telegram keessa hafa).
"""
import json
import re
import shutil
import time
from pathlib import Path

import requests

KEEP = 25  # video dhumaa meeqa app keessatti haa tursu


def title_from(meta, script):
    m = re.search(r"TITLE:\s*(.+)", meta or "")
    if m:
        return m.group(1).strip()
    first = (script or "").strip().splitlines()[0] if (script or "").strip() else "Video"
    return first.split("|")[0].strip()[:70]


def save_meta(run_dir, script, meta, **extra):
    data = {"created": time.strftime("%Y-%m-%d %H:%M"),
            "title": title_from(meta, script),
            "script": script, "meta": meta or "", **extra}
    Path(run_dir, "meta.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    return data


def cleanup(runs_dir, keep=KEEP):
    dirs = sorted(p for p in Path(runs_dir).iterdir() if p.is_dir())
    for p in dirs[:-keep]:
        shutil.rmtree(p, ignore_errors=True)


def load_history(runs_dir, limit=KEEP):
    items = []
    for mp in sorted(Path(runs_dir).glob("*/meta.json"), reverse=True)[:limit]:
        try:
            d = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            continue
        d["id"] = mp.parent.name
        d["has_video"] = (mp.parent / "output.mp4").exists()
        items.append(d)
    return items


def _tg(token, method, **kw):
    return requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=300, **kw)


def tg_backup(token, chat_id, video_path, title, script, meta):
    """Video + script Telegram'tti ergi. [(maqaa, milkaa'e?, ibsa)] deebisa."""
    results = []
    video = Path(video_path)
    mb = video.stat().st_size / 1e6 if video.exists() else 0
    if video.exists() and mb <= 49:
        with open(video, "rb") as f:
            r = _tg(token, "sendVideo",
                    data={"chat_id": chat_id, "caption": (title or "Video")[:200],
                          "supports_streaming": "true"},
                    files={"video": ("video.mp4", f, "video/mp4")})
        ok = r.status_code == 200 and r.json().get("ok", False)
        results.append(("Video", ok, "" if ok else r.text[:200]))
    elif video.exists():
        results.append(("Video", False, f"Faayilii {mb:.0f} MB (Telegram bot 50 MB gadi qofa)"))
    text = f"{title}\n\n{meta}\n\n----- SCRIPT -----\n{script}"
    r = _tg(token, "sendDocument",
            data={"chat_id": chat_id, "caption": "Script + Title/Description/Hashtags"},
            files={"document": ("script.txt", text.encode("utf-8"), "text/plain")})
    ok = r.status_code == 200 and r.json().get("ok", False)
    results.append(("Script", ok, "" if ok else r.text[:200]))
    return results


def tg_find_chats(token):
    """Bot kee waliin haasa'aniiru: Chat ID barbaada. (chats{id: maqaa}, dogoggora)"""
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30)
    js = r.json()
    if not js.get("ok"):
        return {}, js.get("description", "Token dogoggora")
    chats = {}
    for u in js.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        c = m.get("chat", {})
        if c.get("id"):
            chats[c["id"]] = c.get("username") or c.get("first_name") or c.get("title") or ""
    return chats, ""


# ---------------- Kuusaa dhaabbataa: Hugging Face (dataset dhuunfaa) ----------------
def _hf():
    try:
        import huggingface_hub as hh
    except ImportError:
        raise RuntimeError("GitHub keessatti requirements.txt irratti 'huggingface_hub' jedhu dabali.")
    return hh


def hf_repo_id(token):
    name = _hf().HfApi(token=token).whoami()["name"]
    return f"{name}/faceless-history"


def hf_save(token, run_dir):
    """Video + meta.json + script.txt Hugging Face dataset dhuunfaa kee tti olkaa'a."""
    hh = _hf()
    api = hh.HfApi(token=token)
    repo = hf_repo_id(token)
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    rid = Path(run_dir).name
    api.upload_folder(folder_path=str(run_dir), path_in_repo=f"runs/{rid}", repo_id=repo,
                      repo_type="dataset", allow_patterns=["output.mp4", "meta.json", "script.txt"],
                      commit_message=f"add {rid}")
    return repo


def hf_history(token, limit=30):
    hh = _hf()
    repo = hf_repo_id(token)
    api = hh.HfApi(token=token)
    try:
        files = api.list_repo_files(repo, repo_type="dataset")
    except Exception as e:
        if "404" in str(e) or "RepositoryNotFound" in type(e).__name__:
            return []  # duraan homaa hin kuufamne
        raise
    ids = sorted({f.split("/")[1] for f in files
                  if f.startswith("runs/") and f.endswith("/meta.json")}, reverse=True)[:limit]
    items = []
    for rid in ids:
        p = hh.hf_hub_download(repo_id=repo, filename=f"runs/{rid}/meta.json",
                               repo_type="dataset", token=token)
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        d["id"] = rid
        d["remote"] = True
        d["has_video"] = f"runs/{rid}/output.mp4" in files
        items.append(d)
    return items


def hf_video_path(token, rid):
    return _hf().hf_hub_download(repo_id=hf_repo_id(token), filename=f"runs/{rid}/output.mp4",
                                 repo_type="dataset", token=token)


def hf_delete(token, rid):
    _hf().HfApi(token=token).delete_folder(path_in_repo=f"runs/{rid}", repo_id=hf_repo_id(token),
                                           repo_type="dataset")
