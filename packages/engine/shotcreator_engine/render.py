"""Render segments to mp4: PIL frames piped as rawvideo into ffmpeg.

Port of the original scripts' encode path: raw RGB24 frames at WxH@FPS
straight into libx264 (yuv420p, crf 20, preset medium).
"""
from __future__ import annotations

import os
import subprocess
from typing import List, Sequence, Tuple, Union

from PIL import Image

from .layout import make_background, prepare_shot, rounded_mask
from .motion import iter_offsets
from .template import DEFAULT_TEMPLATE, Template

# (image path | PIL image, pan_seconds)
Segment = Tuple[Union[str, "os.PathLike", Image.Image], float]


def _open_image(src: Union[str, "os.PathLike", Image.Image]) -> Image.Image:
    if isinstance(src, Image.Image):
        return src.convert("RGB")
    return Image.open(src).convert("RGB")


def _ffmpeg_cmd(t: Template, out_path: str, overwrite: bool) -> list:
    return [
        "ffmpeg", "-y" if overwrite else "-n",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{t.width}x{t.height}", "-r", str(t.fps), "-i", "-",
        "-c:v", t.video_codec, "-pix_fmt", t.pix_fmt,
        "-crf", str(t.crf), "-preset", t.preset,
        out_path,
    ]


def render_video(segments: Sequence[Segment],
                 top_lines: Sequence[str],
                 bot_lines: Sequence[str],
                 out_path: str,
                 template: Template = DEFAULT_TEMPLATE,
                 overwrite: bool = True) -> str:
    """Render one video from segments. Returns out_path.

    Each segment is (image, pan_seconds): the card holds the top of the
    screenshot for dwell_top, eases down, then holds the bottom for
    dwell_bot (see motion.iter_offsets).
    """
    t = template
    bg = make_background(t, list(top_lines), list(bot_lines))
    mask = rounded_mask(t.card_w, t.card_h, t.card_radius)

    shots: List[Tuple[Image.Image, float, int]] = []
    for src, pan_s in segments:
        img = prepare_shot(_open_image(src), t)
        max_off = max(0, img.height - t.card_h)
        shots.append((img, float(pan_s), max_off))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    proc = subprocess.Popen(
        _ffmpeg_cmd(t, out_path, overwrite),
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert proc.stdin is not None
    try:
        for img, pan_s, max_off in shots:
            travel = int(max_off * t.pan_frac)
            for off in iter_offsets(t.dwell_top, pan_s, t.dwell_bot, travel, t.fps):
                frame = bg.copy()
                crop = img.crop((0, off, t.card_w, off + t.card_h))
                frame.paste(crop, (t.card_x, t.card_y), mask)
                proc.stdin.write(frame.tobytes())
    finally:
        proc.stdin.close()
        proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")
    return out_path
