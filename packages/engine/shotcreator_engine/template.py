"""Render template: every visual constant of the shotcreator look, in one place.

Faithful to the original scripts (video_bri_lunas/make_video.py,
video_batch1/make_videos.py): navy background, bold hook text, rounded
screenshot card, dwell -> ease pan -> dwell motion, libx264 crf20.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

RGB = Tuple[int, int, int]


@dataclass(frozen=True)
class Template:
    # canvas
    width: int = 1080
    height: int = 1920
    fps: int = 30
    # colors
    bg_color: RGB = (11, 21, 38)        # navy
    text_color: RGB = (255, 255, 255)   # white
    # screenshot card geometry
    card_x: int = 48
    card_y: int = 400
    card_w: int = 984
    card_h: int = 1120
    card_radius: int = 30
    # hook text
    top_y: int = 96
    top_start_size: int = 88
    bot_y: int = 1568
    bot_start_size: int = 62
    max_text_w: int = 960
    line_height_ratio: float = 1.22
    min_font_size: int = 36
    # motion
    dwell_top: float = 1.0
    dwell_bot: float = 1.0
    pan_frac: float = 0.75
    # encode (bisa dioverride via env: SHOTCREATOR_PRESET, SHOTCREATOR_CRF)
    crf: int = 20
    preset: str = "veryfast"
    video_codec: str = "libx264"
    pix_fmt: str = "yuv420p"


DEFAULT_TEMPLATE = Template()
