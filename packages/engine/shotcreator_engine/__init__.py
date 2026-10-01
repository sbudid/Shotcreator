"""shotcreator_engine: deterministic vertical-video renderer (PIL + ffmpeg)."""
import os
from dataclasses import replace
from .template import Template, DEFAULT_TEMPLATE
from .render import render_video
from .audio import mux_audio
from . import layout, motion

# Override preset/crf via env (mis. SHOTCREATOR_PRESET=ultrafast di VPS kentang)
_env_preset = os.environ.get("SHOTCREATOR_PRESET", "").strip()
_env_crf = os.environ.get("SHOTCREATOR_CRF", "").strip()
if _env_preset or _env_crf:
    _kw = {}
    if _env_preset:
        _kw["preset"] = _env_preset
    if _env_crf:
        try:
            _kw["crf"] = int(_env_crf)
        except ValueError:
            pass
    DEFAULT_TEMPLATE = replace(DEFAULT_TEMPLATE, **_kw)

__all__ = [
    "Template",
    "DEFAULT_TEMPLATE",
    "render_video",
    "mux_audio",
    "layout",
    "motion",
]

__version__ = "0.1.0"
