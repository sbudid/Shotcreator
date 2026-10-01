"""shotcreator_engine: deterministic vertical-video renderer (PIL + ffmpeg)."""
from .template import Template, DEFAULT_TEMPLATE
from .render import render_video
from .audio import mux_audio
from . import layout, motion

__all__ = [
    "Template",
    "DEFAULT_TEMPLATE",
    "render_video",
    "mux_audio",
    "layout",
    "motion",
]

__version__ = "0.1.0"
