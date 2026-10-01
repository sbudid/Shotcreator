"""Manual provider: return the user's own text untouched.

Use when no AI is configured — the engine renders exactly what you type.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .base import AIProvider


class ManualProvider(AIProvider):
    name = "manual"

    def __init__(self,
                 top_lines: Optional[Sequence[str]] = None,
                 bot_lines: Optional[Sequence[str]] = None,
                 caption: str = ""):
        self._top = [str(x) for x in (top_lines or [""])]
        self._bot = [str(x) for x in (bot_lines or [""])]
        self._caption = caption

    def generate_hooks(self, story: str) -> Tuple[List[str], List[str]]:
        return list(self._top), list(self._bot)

    def generate_caption(self, story: str,
                         hooks: Optional[Tuple[List[str], List[str]]] = None) -> str:
        return self._caption
