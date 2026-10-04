#!/usr/bin/env python3
"""Proses antrean hook Shotcreator via command-code API.

- money_pending/  -> deepseek flash (teks `story`)
- vision_pending/ -> gemini flash vision (gambar img_*)

Untuk tiap job: tulis {money,vision}_done/{job_id}.json lalu hapus direktori
pending. Job yang gagal total (bukan error jaringan) ditulis dengan
status "failed" + reason agar tidak macet di antrean.

Stdlib only. Konfigurasi dibaca dari ~/workspace/shotcreator/.env:
  COMMANDCODE_BASE_URL / COMMANDCODE_API_KEY
  COMMANDCODE_HOOK_MODEL / COMMANDCODE_VISION_MODEL

Jalankan:  python3 process_pending.py
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import time
import urllib.request
import urllib.error

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_FILE = os.path.join(REPO_ROOT, ".env")
DATA_DIR = os.environ.get("SHOTCREATOR_DATA",
                          os.path.join(os.path.dirname(__file__), "data"))
MONEY_PENDING = os.path.join(DATA_DIR, "money_pending")
MONEY_DONE = os.path.join(DATA_DIR, "money_done")
VISION_PENDING = os.path.join(DATA_DIR, "vision_pending")
VISION_DONE = os.path.join(DATA_DIR, "vision_done")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

SYSTEM_PROMPT = (
    "Kamu penulis hook video vertikal TikTok/Reels berbahasa Indonesia. "
    "Balas HANYA dengan JSON seperti ini: "
    '{"top": ["BARIS ATAS 1", "BARIS ATAS 2"], "bottom": ["BARIS BAWAH"]}. '
    "Huruf kapital semua, tiap baris maksimal 28 karakter, 1-2 baris per "
    "bagian, gaya bikin penasaran dan emosional. "
    "JANGAN mengklaim pengalaman pribadi seperti 'aku pakai' atau 'favoritku'."
)

IMG_EXTS = {".png": "image/png", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}

MAX_ATTEMPTS = 20          # ~5 menit retry @15s sebelum ditandai gagal
CONNECT_TIMEOUT = 90       # detik per request


def load_config() -> dict:
    cfg: dict = {}
    try:
        with open(ENV_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except OSError:
        pass
    base = (cfg.get("COMMANDCODE_BASE_URL")
            or os.environ.get("COMMANDCODE_BASE_URL", "")).rstrip("/")
    key = cfg.get("COMMANDCODE_API_KEY") or os.environ.get("COMMANDCODE_API_KEY", "")
    hook_model = (cfg.get("COMMANDCODE_HOOK_MODEL")
                  or os.environ.get("COMMANDCODE_HOOK_MODEL")
                  or "deepseek/deepseek-v4-flash")
    vision_model = (cfg.get("COMMANDCODE_VISION_MODEL")
                    or os.environ.get("COMMANDCODE_VISION_MODEL")
                    or "google/gemini-3.8-flash")
    if not base or not key:
        raise SystemExit("command-code belum dikonfigurasi di .env")
    return {"base": base, "key": key, "hook": hook_model, "vision": vision_model}


def chat_completions(cfg: dict, model: str, messages: list,
                     timeout: int = CONNECT_TIMEOUT) -> str:
    body = json.dumps({"model": model, "messages": messages,
                       "temperature": 0.7}).encode()
    req = urllib.request.Request(
        cfg["base"] + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + cfg["key"],
                 "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"API HTTP {e.code}: {detail}")
    data = json.loads(raw)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"respons API tak terduga: {e}")


def parse_hooks(text: str) -> tuple[list, list]:
    """Ambil JSON {top, bottom} dari jawaban model; normalisasi aturan hook."""
    t = text.strip()
    # buang code fence ```json ... ```
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    obj = json.loads(t[t.index("{"): t.rindex("}") + 1])

    def norm(lines):
        out = []
        for x in lines or []:
            s = str(x).strip().upper()
            if not s:
                continue
            if len(s) > 28:
                s = s[:28].rstrip()
            out.append(s)
            if len(out) == 2:
                break
        return out

    top, bot = norm(obj.get("top")), norm(obj.get("bottom"))
    if not top or not bot:
        raise ValueError("model tidak mengembalikan top/bottom yang valid")
    return top, bot


def write_done(done_dir: str, job_id: str, payload: dict):
    os.makedirs(done_dir, exist_ok=True)
    tmp = os.path.join(done_dir, job_id + ".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, os.path.join(done_dir, job_id + ".json"))


def bump_attempts(pending_path: str) -> int:
    try:
        with open(pending_path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    n = int(meta.get("attempts", 0) or 0) + 1
    meta["attempts"] = n
    try:
        with open(pending_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    except OSError:
        pass
    return n


def process_money(cfg: dict) -> int:
    done = 0
    if not os.path.isdir(MONEY_PENDING):
        return 0
    for job_id in sorted(os.listdir(MONEY_PENDING)):
        job_dir = os.path.join(MONEY_PENDING, job_id)
        pending_path = os.path.join(job_dir, "pending.json")
        if not os.path.isdir(job_dir) or not os.path.isfile(pending_path):
            continue
        try:
            with open(pending_path, encoding="utf-8") as f:
                meta = json.load(f)
            story = (meta.get("story") or "").strip()
            if not story:
                write_done(MONEY_DONE, job_id,
                           {"job_id": job_id, "status": "failed",
                            "reason": "story kosong", "top_lines": [],
                            "bot_lines": []})
                shutil.rmtree(job_dir, ignore_errors=True)
                done += 1
                continue
            text = chat_completions(
                cfg, cfg["hook"],
                [{"role": "user",
                  "content": SYSTEM_PROMPT + "\n\nDeskripsi:\n" + story}])
            top, bot = parse_hooks(text)
            write_done(MONEY_DONE, job_id,
                       {"job_id": job_id, "status": "done",
                        "top_lines": top, "bot_lines": bot})
            shutil.rmtree(job_dir, ignore_errors=True)
            done += 1
            print(f"[money] {job_id}: done ({cfg['hook']})")
        except Exception as e:  # noqa: BLE001 - retry next run
            n = bump_attempts(pending_path)
            print(f"[money] {job_id}: percobaan {n} gagal: {e}",
                  file=sys.stderr)
            if n >= MAX_ATTEMPTS:
                write_done(MONEY_DONE, job_id,
                           {"job_id": job_id, "status": "failed",
                            "reason": f"AI gagal {n}x: {e}",
                            "top_lines": [], "bot_lines": []})
                shutil.rmtree(job_dir, ignore_errors=True)
                done += 1
    return done


def process_vision(cfg: dict) -> int:
    done = 0
    if not os.path.isdir(VISION_PENDING):
        return 0
    for job_id in sorted(os.listdir(VISION_PENDING)):
        job_dir = os.path.join(VISION_PENDING, job_id)
        pending_path = os.path.join(job_dir, "pending.json")
        if not os.path.isdir(job_dir) or not os.path.isfile(pending_path):
            continue
        try:
            imgs = []
            for name in sorted(os.listdir(job_dir)):
                ext = os.path.splitext(name)[1].lower()
                if not name.startswith("img_") or ext not in IMG_EXTS:
                    continue
                path = os.path.join(job_dir, name)
                size = os.path.getsize(path)
                if size < 1024:  # placeholder 1x1 dsb — tidak bisa dianalisis
                    continue
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                imgs.append({"type": "image_url", "image_url": {
                    "url": f"data:{IMG_EXTS[ext]};base64," + b64}})
                if len(imgs) == 5:
                    break
            if not imgs:
                write_done(VISION_DONE, job_id,
                           {"job_id": job_id, "status": "failed",
                            "reason": "tidak ada gambar valid untuk dianalisis",
                            "top_lines": [], "bot_lines": []})
                shutil.rmtree(job_dir, ignore_errors=True)
                done += 1
                continue
            content = [{"type": "text",
                        "text": SYSTEM_PROMPT + "\n\nBuatkan hook untuk "
                        "gambar-gambar ini."}] + imgs
            text = chat_completions(cfg, cfg["vision"],
                                    [{"role": "user", "content": content}],
                                    timeout=120)
            top, bot = parse_hooks(text)
            write_done(VISION_DONE, job_id,
                       {"job_id": job_id, "status": "done",
                        "top_lines": top, "bot_lines": bot})
            shutil.rmtree(job_dir, ignore_errors=True)
            done += 1
            print(f"[vision] {job_id}: done ({cfg['vision']}, "
                  f"{len(imgs)} gambar)")
        except Exception as e:  # noqa: BLE001 - retry next run
            n = bump_attempts(pending_path)
            print(f"[vision] {job_id}: percobaan {n} gagal: {e}",
                  file=sys.stderr)
            if n >= MAX_ATTEMPTS:
                write_done(VISION_DONE, job_id,
                           {"job_id": job_id, "status": "failed",
                            "reason": f"AI gagal {n}x: {e}",
                            "top_lines": [], "bot_lines": []})
                shutil.rmtree(job_dir, ignore_errors=True)
                done += 1
    return done


def main() -> int:
    cfg = load_config()
    n = process_money(cfg) + process_vision(cfg)
    if n:
        print(f"selesai: {n} job diproses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
