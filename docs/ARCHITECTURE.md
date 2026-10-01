# Shotcreator — Architecture

## Big idea

**Deterministic engine + pluggable AI.** The thing that draws pixels is 100%
deterministic (Pillow + ffmpeg) and never calls the network. The "smart"
parts — hook text, captions — live behind a tiny `AIProvider` interface, so
any model or OpenAI-compatible endpoint (OpenAI, 9router, Ollama, …) can be
plugged in, or skipped entirely in manual mode. Same provider, different
provider, or no provider: the rendered video looks identical.

## Repo layout

```
packages/engine/        # shotcreator-engine — the renderer (no network, no AI)
  shotcreator_engine/
    template.py         # ALL visual constants (Template dataclass)
    layout.py           # navy bg, autofit hook text, rounded card, font resolve
    motion.py           # dwell -> ease-in-out pan -> dwell
    render.py           # PIL frames -> ffmpeg rawvideo pipe (libx264, crf20)
    audio.py            # mux music/murottal/TTS onto the silent mp4
packages/ai/            # shotcreator-ai — the smart layer (stdlib only)
  shotcreator_ai/
    base.py             # AIProvider ABC: generate_hooks, generate_caption
    openai_compat.py    # OpenAI-compatible chat client (env-configured)
    manual.py           # pass-through provider (no AI)
apps/cli/               # shotcreator CLI: render / hooks
renderer/               # Dockerfile (python + ffmpeg) + queue worker
docs/                   # this file
```

## The look (locked by Template)

Ported 1:1 from the original scripts: 1080×1920 @30fps, navy `(11,21,38)`
background, bold hook text (Inter ExtraBold when available, DejaVu fallback),
screenshot in a 984×1120 rounded card at (48,400) radius 30, 2s dwell top,
slow ease pan, 2s dwell bottom, libx264 `yuv420p` CRF 20 preset medium.

Change the look by constructing a different `Template` — never by editing
render code paths.

## AI adapter contract

```python
class AIProvider(ABC):
    def generate_hooks(self, story: str) -> tuple[list[str], list[str]]: ...
    def generate_caption(self, story, hooks=None) -> str: ...
```

`OpenAICompatProvider` reads (never hardcodes):
`SHOTCREATOR_AI_BASE_URL`, `SHOTCREATOR_AI_API_KEY`, `SHOTCREATOR_AI_MODEL`.
Point the base URL at 9router (`http://…/v1`) and everything else just works.

## Data flow

```
screenshots + story
      │ (CLI / web UI / worker job JSON)
      ▼
AIProvider ──► hooks + caption        (optional; manual mode skips this)
      │
      ▼
engine.render_video ──► silent.mp4 ──► mux_audio ──► final.mp4
(Pillow frames → ffmpeg pipe)
```

## Deploy topology (Phase 2)

Cloudflare Pages hosts the web UI, Workers serve the API + job queue, R2
stores uploads and finished videos. Video encoding needs ffmpeg, which cannot
run on Workers — so `renderer/` ships as a container (Dockerfile) that polls
the queue and uploads results back to R2. Run it on any VM/container host.
