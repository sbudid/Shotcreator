"""shotcreator_ai: pluggable AI providers (hooks, captions)."""
from .base import AIProvider
from .manual import ManualProvider
from .openai_compat import OpenAICompatProvider

__all__ = ["AIProvider", "ManualProvider", "OpenAICompatProvider"]

__version__ = "0.1.0"
