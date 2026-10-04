"""OpenAI-compatible chat provider (stdlib only, no extra dependencies).

Works with OpenAI, 9router, Ollama, LM Studio, or any endpoint speaking the
OpenAI chat-completions API. Configure via environment — never hardcode keys:

  SHOTCREATOR_AI_BASE_URL   default https://api.openai.com/v1
                            e.g. http://localhost:20128/v1 for 9router
  SHOTCREATOR_AI_API_KEY    bearer token ("x" is fine for local servers)
  SHOTCREATOR_AI_MODEL      default gpt-4o-mini
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import List, Optional, Tuple

from .base import AIProvider


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


class OpenAICompatProvider(AIProvider):
    name = "openai_compat"

    def __init__(self, base_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: int = 60):
        self.base_url = (base_url
                         or _env("SHOTCREATOR_AI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        # None = "not passed"; empty string = explicitly empty (local servers).
        self.api_key = api_key if api_key is not None else _env("SHOTCREATOR_AI_API_KEY")
        self.model = model or _env("SHOTCREATOR_AI_MODEL", "gpt-4o-mini")
        self.timeout = timeout

    def _chat(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError(
                "SHOTCREATOR_AI_API_KEY is not set; point it at your "
                "OpenAI key or 9router/Ollama endpoint."
            )
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        }).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}",
                     # command-code/Cloudflare menolak request tanpa UA browser
                     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/126.0.0.0 Safari/537.36"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Handle SSE-style suffix ("data: [DONE]") yang kadang ditempel 9router
        raw = raw.strip()
        if raw.endswith("data: [DONE]"):
            raw = raw[: -len("data: [DONE]")].strip()
        # Kalau masih ada baris SSE, ambil baris JSON pertama yang valid
        if raw.startswith("data:"):
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("data:") and line != "data: [DONE]":
                    raw = line[len("data:"):].strip()
                    break
        data = json.loads(raw)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"unexpected chat-completions response: {e}")

    @staticmethod
    def _parse_hooks(text: str) -> Tuple[List[str], List[str]]:
        # Preferred: JSON {"top": [...], "bottom": [...]}
        try:
            obj = json.loads(text[text.index("{"): text.rindex("}") + 1])
            top = [str(x).strip().upper() for x in obj.get("top", []) if str(x).strip()]
            bot = [str(x).strip().upper() for x in obj.get("bottom", []) if str(x).strip()]
            if top and bot:
                return top, bot
        except Exception:
            pass
        # Fallback: split non-empty lines in half.
        lines = [ln.strip().upper() for ln in text.splitlines() if ln.strip()]
        mid = max(1, len(lines) // 2)
        return lines[:mid], lines[mid:] or [""]

    def generate_hooks(self, story: str) -> Tuple[List[str], List[str]]:
        system = (
            "Kamu penulis hook video vertikal TikTok/Reels berbahasa Indonesia. "
            "Balas HANYA dengan JSON seperti ini: "
            '{"top": ["BARIS ATAS 1", "BARIS ATAS 2"], "bottom": ["BARIS BAWAH"]}. '
            "Huruf kapital semua, tiap baris maksimal 28 karakter, 1-2 baris per "
            "bagian, gaya bikin penasaran dan emosional."
        )
        return self._parse_hooks(self._chat(system, story))

    def generate_caption(self, story: str,
                         hooks: Optional[Tuple[List[str], List[str]]] = None) -> str:
        system = (
            "Kamu penulis caption TikTok/Reels berbahasa Indonesia. "
            "Tulis 2-4 kalimat santai lalu 5-8 hashtag relevan. "
            "Balas hanya dengan caption-nya, tanpa teks lain."
        )
        user = story
        if hooks:
            user += "\nHook video: " + " / ".join(hooks[0]) + " // " + " / ".join(hooks[1])
        return self._chat(system, user).strip()
