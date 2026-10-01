"""AIProvider: the pluggable "smart" layer (hooks, captions).

The render engine never depends on this. Any provider — OpenAI, 9router,
Ollama, or plain manual input — implements this interface and the videos
come out identical.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate_hooks(self, story: str) -> Tuple[List[str], List[str]]:
        """Return (top_lines, bottom_lines) hook text for a story description."""

    @abstractmethod
    def generate_caption(self, story: str,
                         hooks: Optional[Tuple[List[str], List[str]]] = None) -> str:
        """Return a ready-to-post caption (with hashtags)."""
