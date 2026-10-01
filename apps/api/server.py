#!/usr/bin/env python3
"""Shotcreator API server (stdlib only).

Endpoint:
  POST /api/hooks       {story}
                        -> {top_lines[], bot_lines[]}
                        (konfigurasi AI dibaca dari env vars server,
                         bukan dari request)
  POST /api/jobs        {images:[{name, data_url}], top_lines[], bot_lines[],
                         audio:{name, data_url}|null, pan_secs?}
                        -> {job_id}
  GET  /api/jobs/:id    -> {status: queued|rendering|done|error,
                            progress?, video_url?, top_lines?, bot_lines?, error?}
  GET  /videos/:file    -> file mp4 hasil render
  GET  /api/health      -> {ok: true}

Jalankan:
  python3 server.py

Env:
  PORT                  default 8000
  SHOTCREATOR_AI_BASE_URL   base URL AI OpenAI-compatible (wajib untuk /api/hooks)
  SHOTCREATOR_AI_API_KEY    API key AI (kalau provider membutuhkannya)
  SHOTCREATOR_AI_MODEL      model AI
  SHOTCREATOR_FONT      path font bold untuk hook (default: DejaVuSans-Bold)
  SHOTCREATOR_DATA      direktori data (default ./data)

Render jalan di background thread; engine (packages/engine) + ffmpeg dipakai
langsung, tanpa queue eksternal.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# --- repo layout: apps/api/server.py -> repo root -> packages/{engine,ai} ---
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for pkg in ("packages/engine", "packages/ai"):
    p = os.path.join(REPO_ROOT, pkg)
    if p not in sys.path:
        sys.path.insert(0, p)

PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("SHOTCREATOR_DATA",
                          os.path.join(os.path.dirname(__file__), "data"))
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
VIDEOS_DIR = os.path.join(DATA_DIR, "videos")
WEB_DIR = os.path.join(REPO_ROOT, "apps", "web")

MAX_BODY = 200 * 1024 * 1024          # 200 MB per request
MAX_FILE = 30 * 1024 * 1024          # 30 MB per file
DEFAULT_PAN_SECS = 13.0

os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(VIDEOS_DIR, exist_ok=True)

SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DATA_URL_RE = re.compile(r"^data:([A-Za-z0-9][A-Za-z0-9.+\-/]*);base64,(.*)$", re.S)

IMAGE_MIMES = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
    "image/gif": ".gif",
}
AUDIO_MIMES = {
    "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/x-m4a": ".m4a",
    "audio/wav": ".wav", "audio/webm": ".webm", "audio/ogg": ".ogg",
}


# ---------------------------------------------------------------- jobs
class JobStore:
    """In-memory jobs + persistensi status akhir ke disk."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}
        self._reload_done()

    def _reload_done(self):
        for jid in os.listdir(JOBS_DIR):
            meta = os.path.join(JOBS_DIR, jid, "job.json")
            if not os.path.isfile(meta):
                continue
            try:
                with open(meta, encoding="utf-8") as f:
                    job = json.load(f)
                if job.get("status") in ("done", "error"):
                    self._jobs[jid] = job
            except Exception:
                pass

    def create(self, payload: dict) -> dict:
        jid = uuid.uuid4().hex[:16]
        job = {
            "job_id": jid,
            "status": "queued",
            "progress": 5,
            "created_at": time.time(),
            "top_lines": payload.get("top_lines", []),
            "bot_lines": payload.get("bot_lines", []),
        }
        with self._lock:
            self._jobs[jid] = job
        return job

    def get(self, jid: str):
        with self._lock:
            return dict(self._jobs.get(jid, {}))

    def update(self, jid: str, **fields):
        with self._lock:
            job = self._jobs.get(jid)
            if job is None:
                return
            job.update(fields)
            job = dict(job)
        if fields.get("status") in ("done", "error"):
            try:
                os.makedirs(os.path.join(JOBS_DIR, jid), exist_ok=True)
                with open(os.path.join(JOBS_DIR, jid, "job.json"), "w",
                          encoding="utf-8") as f:
                    json.dump(job, f, ensure_ascii=False)
            except Exception:
                pass

    def public(self, jid: str, base_url: str):
        job = self.get(jid)
        if not job:
            return None
        out = {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job.get("progress", 0),
        }
        if job.get("top_lines"):
            out["top_lines"] = job["top_lines"]
        if job.get("bot_lines"):
            out["bot_lines"] = job["bot_lines"]
        if job["status"] == "done" and job.get("video_file"):
            out["video_url"] = f"{base_url}/videos/{job['video_file']}"
        if job["status"] == "error":
            out["error"] = job.get("error") or "Render gagal tanpa pesan."
        return out


JOBS = JobStore()


# ---------------------------------------------------------------- helpers
def decode_data_url(data_url: str, allowed: dict, label: str):
    """Return (ext, bytes). Raise ValueError dengan pesan Indonesia."""
    m = DATA_URL_RE.match((data_url or "").strip())
    if not m:
        raise ValueError(f"{label}: format data URL tidak valid.")
    mime, b64 = m.group(1).lower(), m.group(2)
    ext = allowed.get(mime)
    if not ext:
        raise ValueError(
            f"{label}: tipe file tidak didukung ({mime}).")
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError(f"{label}: isi base64 rusak.")
    if len(raw) > MAX_FILE:
        raise ValueError(
            f"{label}: file terlalu besar (maks {MAX_FILE // 1024 // 1024} MB).")
    if not raw:
        raise ValueError(f"{label}: file kosong.")
    return ext, raw


def make_ai_provider():
    """Bangun provider AI dari env vars server. Raise ValueError (pesan ID)."""
    from shotcreator_ai import OpenAICompatProvider

    base_url = (os.environ.get("SHOTCREATOR_AI_BASE_URL") or "").strip()
    model = (os.environ.get("SHOTCREATOR_AI_MODEL") or "").strip()
    cred = (os.environ.get("SHOTCREATOR_AI_API_KEY") or "").strip()
    if not base_url:
        raise ValueError(
            "AI belum dikonfigurasi di server. "
            "Set SHOTCREATOR_AI_BASE_URL di server "
            "(dan SHOTCREATOR_AI_API_KEY / SHOTCREATOR_AI_MODEL bila perlu), "
            "lalu coba lagi.")
    return OpenAICompatProvider(base_url or None, cred or None,
                                model or None)


# ---------------------------------------------------------------- worker
def render_job(jid: str, payload: dict):
    """Background thread: render -> mux audio. Hook sudah final dari client
    (manual atau hasil /api/hooks)."""
    job_dir = os.path.join(JOBS_DIR, jid)
    os.makedirs(job_dir, exist_ok=True)
    t0 = time.time()
    try:
        JOBS.update(jid, status="rendering", progress=8)

        images = payload.get("images") or []
        if not images:
            raise ValueError("Upload dulu minimal 1 screenshot.")
        if len(images) > 20:
            raise ValueError("Maksimal 20 gambar per job.")

        top_lines = [str(x).strip() for x in (payload.get("top_lines") or [])
                     if str(x).strip()]
        bot_lines = [str(x).strip() for x in (payload.get("bot_lines") or [])
                     if str(x).strip()]

        # field ai.* dari client diabaikan — hook sudah final di payload
        if not top_lines or not bot_lines:
            raise ValueError("Isi teks hook atas & bawah dulu.")

        # simpan input
        img_paths = []
        for i, img in enumerate(images):
            name = str(img.get("name") or f"gambar-{i+1}")
            ext, raw = decode_data_url(img.get("data_url", ""), IMAGE_MIMES,
                                       f"Gambar {name}")
            path = os.path.join(job_dir, f"img_{i:02d}{ext}")
            with open(path, "wb") as f:
                f.write(raw)
            img_paths.append(path)

        audio_path = None
        audio = payload.get("audio")
        if audio:
            ext, raw = decode_data_url(audio.get("data_url", ""), AUDIO_MIMES,
                                       "Audio")
            audio_path = os.path.join(job_dir, f"audio{ext}")
            with open(audio_path, "wb") as f:
                f.write(raw)

        pan_secs = payload.get("pan_secs")
        if not isinstance(pan_secs, list) or len(pan_secs) != len(img_paths):
            pan_secs = [DEFAULT_PAN_SECS] * len(img_paths)
        pan_secs = [max(1.0, float(x)) for x in pan_secs]

        # estimasi durasi untuk progress bar
        total_est = sum(2.0 + 2.0 + p for p in pan_secs)
        stop_flag = {"stop": False}

        def progress_loop():
            while not stop_flag["stop"]:
                el = time.time() - t0
                frac = min(el / max(total_est, 1.0), 1.0)
                JOBS.update(jid, progress=int(10 + 85 * frac))
                time.sleep(0.5)

        pt = threading.Thread(target=progress_loop, daemon=True)
        pt.start()
        try:
            from shotcreator_engine import render_video
            segments = list(zip(img_paths, pan_secs))
            silent = os.path.join(job_dir, "silent.mp4")
            render_video(segments, top_lines, bot_lines, silent)

            final_name = f"{jid}.mp4"
            os.makedirs(VIDEOS_DIR, exist_ok=True)
            final_path = os.path.join(VIDEOS_DIR, final_name)
            if audio_path:
                from shotcreator_engine.audio import mux_audio
                mux_audio(silent, audio_path, final_path)
                try:
                    os.remove(silent)
                except OSError:
                    pass
            else:
                shutil.move(silent, final_path)
        finally:
            stop_flag["stop"] = True
            pt.join(timeout=2)

        JOBS.update(jid, status="done", progress=100, video_file=final_name)
    except Exception as e:  # noqa: BLE001 - semua error jadi status job
        msg = str(e) or "Terjadi kesalahan tak dikenal."
        if "ValueError" in type(e).__name__:
            detail = msg  # pesan validasi sudah Bahasa Indonesia
        else:
            traceback.print_exc()
            detail = "Gagal merender video. Coba lagi."
        JOBS.update(jid, status="error", error=detail)


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "ShotcreatorAPI/0.1"

    # -- util --
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, msg: str, code: int):
        self._send_json({"error": msg}, code)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("Request terlalu besar.")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise ValueError("Body harus JSON yang valid.")

    def _base_url(self):
        host = self.headers.get("Host") or f"localhost:{PORT}"
        scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" \
            else "http"
        return f"{scheme}://{host}"

    # -- routes --
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            return self._send_json({"ok": True})

        m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)", path)
        if m:
            job = JOBS.public(m.group(1), self._base_url())
            if not job:
                return self._send_error_json("Job tidak ditemukan.", 404)
            return self._send_json(job)

        m = re.fullmatch(r"/videos/([A-Za-z0-9_-]+\.mp4)", path)
        if m:
            fpath = os.path.join(VIDEOS_DIR, m.group(1))
            if not os.path.isfile(fpath):
                return self._send_error_json("Video tidak ditemukan.", 404)
            size = os.path.getsize(fpath)
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition",
                             f'inline; filename="{m.group(1)}"')
            self.end_headers()
            with open(fpath, "rb") as f:
                shutil.copyfileobj(f, self.wfile, length=1024 * 256)
            return

        # static: web UI (biar server bisa jalan standalone)
        if path in ("/", "/index.html"):
            return self._serve_file(os.path.join(WEB_DIR, "index.html"),
                                    "text/html; charset=utf-8")
        if path in ("/app.js", "/styles.css"):
            ctype = ("application/javascript; charset=utf-8"
                     if path.endswith(".js") else "text/css; charset=utf-8")
            return self._serve_file(os.path.join(WEB_DIR, path.lstrip("/")),
                                    ctype)

        return self._send_error_json("Tidak ditemukan.", 404)

    def _serve_file(self, fpath, ctype):
        if not os.path.isfile(fpath):
            return self._send_error_json("Tidak ditemukan.", 404)
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/hooks":
                return self._handle_hooks()
            if path == "/api/jobs":
                return self._handle_jobs()
            return self._send_error_json("Tidak ditemukan.", 404)
        except ValueError as e:
            return self._send_error_json(str(e), 400)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_json(
                "Terjadi kesalahan di server. Coba lagi.", 500)

    def _handle_hooks(self):
        body = self._read_json()
        story = (body.get("story") or "").strip()
        if not story:
            return self._send_error_json("Isi dulu deskripsi ceritanya.", 400)
        try:
            provider = make_ai_provider()
            top, bot = provider.generate_hooks(story)
        except ValueError as e:
            return self._send_error_json(str(e), 400)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            return self._send_error_json(
                "Gagal menghubungi AI. Cek konfigurasi AI di server.", 502)
        return self._send_json({"top_lines": top, "bot_lines": bot})

    def _handle_jobs(self):
        body = self._read_json()
        images = body.get("images")
        if not images or not isinstance(images, list):
            return self._send_error_json(
                "Upload dulu minimal 1 screenshot.", 400)
        job = JOBS.create(body)
        t = threading.Thread(target=render_job,
                             args=(job["job_id"], body), daemon=True)
        t.start()
        return self._send_json({"job_id": job["job_id"]}, 202)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


def main():
    # ffmpeg harus ada
    if shutil.which("ffmpeg") is None:
        sys.stderr.write(
            "PERINGATAN: ffmpeg tidak ditemukan di PATH. "
            "Render video akan gagal sampai ffmpeg terinstal.\n")
    # Pillow harus ada (dibutuhkan engine)
    try:
        import PIL  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "PERINGATAN: Pillow belum terinstal. "
            "Jalankan: pip install -r requirements.txt\n")

    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Shotcreator API jalan di http://0.0.0.0:{PORT}")
    print(f"Data dir : {DATA_DIR}")
    print(f"Web UI   : http://localhost:{PORT}/  (atau via Cloudflare Pages)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")


if __name__ == "__main__":
    main()
