#!/usr/bin/env python3
"""Shotcreator render worker: consume job JSON files, render mp4 via the engine.

Usage:
  python worker.py --once            process every pending *.json in the queue dir, then exit
  python worker.py                   poll the queue dir forever (default)
  echo '{...}' | python worker.py --stdin

Job JSON schema:
  {
    "segments": [{"image": "/in/a.png", "pan_sec": 13}],
    "top": ["HOOK LINE 1", "HOOK LINE 2"],
    "bottom": ["BOTTOM LINE"],
    "audio": "/in/music.mp3",        # optional
    "output": "/out/video.mp4",
    "dwell_top": 2.0, "dwell_bot": 2.0, "pan_frac": 0.75   # optional
  }

Queue dir comes from $SHOTCREATOR_QUEUE_DIR (default /queue). Processed jobs
get a sibling "<name>.json.done.json"; failures get "<name>.json.error.json".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

from shotcreator_engine import Template, render_video
from shotcreator_engine.audio import mux_audio


def process_job(job: dict) -> dict:
    template = Template(
        dwell_top=float(job.get("dwell_top", 2.0)),
        dwell_bot=float(job.get("dwell_bot", 2.0)),
        pan_frac=float(job.get("pan_frac", 0.75)),
    )
    segments = [(s["image"], float(s.get("pan_sec", 13.0)))
                for s in job.get("segments", [])]
    if not segments:
        raise ValueError("job has no segments")
    out = job["output"]
    audio = job.get("audio")
    if audio:
        silent = out + ".silent.mp4"
        render_video(segments, job.get("top", []), job.get("bottom", []),
                     silent, template=template)
        mux_audio(silent, audio, out)
        os.remove(silent)
    else:
        render_video(segments, job.get("top", []), job.get("bottom", []),
                     out, template=template)
    return {"ok": True, "output": out}


def process_file(path: str) -> None:
    if os.path.exists(path + ".done.json"):
        return
    try:
        with open(path) as f:
            job = json.load(f)
        result = process_job(job)
        with open(path + ".done.json", "w") as f:
            json.dump(result, f)
        print(f"OK {path}", flush=True)
    except Exception as e:  # noqa: BLE001 - worker must not die on a bad job
        with open(path + ".error.json", "w") as f:
            json.dump({"ok": False, "error": str(e),
                       "trace": traceback.format_exc()}, f)
        print(f"FAIL {path}: {e}", flush=True)


def pending_jobs(queue_dir: str):
    for name in sorted(os.listdir(queue_dir)):
        if name.endswith(".json") and not (
                name.endswith(".done.json") or name.endswith(".error.json")):
            yield os.path.join(queue_dir, name)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="shotcreator render worker")
    ap.add_argument("--once", action="store_true",
                    help="process pending jobs once, then exit")
    ap.add_argument("--stdin", action="store_true",
                    help="read one job JSON from stdin")
    ap.add_argument("--queue-dir",
                    default=os.environ.get("SHOTCREATOR_QUEUE_DIR", "/queue"))
    args = ap.parse_args(argv)

    if args.stdin:
        print(json.dumps(process_job(json.load(sys.stdin))))
        return

    os.makedirs(args.queue_dir, exist_ok=True)
    while True:
        for path in pending_jobs(args.queue_dir):
            process_file(path)
        if args.once:
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
