"""Motion curves: dwell -> ease-in-out pan -> dwell.

Port of the batch script's per-segment timing: hold the top of the
screenshot for dwell_top seconds, slow-pan down with smoothstep easing,
then hold the bottom for dwell_bot seconds.
"""
from __future__ import annotations

from typing import Iterator


def ease_in_out(t: float) -> float:
    """Smoothstep easing: slow start, fast middle, slow end."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def iter_offsets(dwell_top_s: float, pan_s: float, dwell_bot_s: float,
                 travel_px: int, fps: int) -> Iterator[int]:
    """Yield the vertical crop offset for every frame of one segment."""
    n_dwell_top = int(fps * dwell_top_s)
    n_pan = int(fps * pan_s)
    n_dwell_bot = int(fps * dwell_bot_s)
    for _ in range(n_dwell_top):
        yield 0
    for i in range(n_pan):
        t = i / max(1, n_pan - 1)
        yield int(travel_px * ease_in_out(t))
    for _ in range(n_dwell_bot):
        yield travel_px


def segment_frame_count(dwell_top_s: float, pan_s: float, dwell_bot_s: float,
                        fps: int) -> int:
    """Total frames one segment produces (handy for duration estimates)."""
    return (int(fps * dwell_top_s) + int(fps * pan_s)
            + int(fps * dwell_bot_s))
