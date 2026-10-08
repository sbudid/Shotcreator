#!/usr/bin/env python3
"""shotcreator CLI.

Render:
  shotcreator render --image a.png --pan-secs 13 \\
      --top "OBAT LELAH\\nBUAT SEORANG IBU" --bot "PELUK ANAKMU" \\
      --audio music.mp3 -o out.mp4

Multi-segment:
  shotcreator render --image before.png --pan-secs 6 --image after.png --pan-secs 6 \\
      --top "BUKAN KUCING," --bot "INI DUGONG!" -o out.mp4

AI hooks (needs SHOTCREATOR_AI_* env or --provider manual):
  shotcreator hooks --story "cerita ibu dan anak..." --provider openai_compat
"""
from __future__ import annotations

import argparse
import os
import sys


def _split_lines(s: str):
    return [ln for ln in s.replace("\\n", "\n").split("\n")]


def _get_provider(name: str):
    from shotcreator_ai import ManualProvider, OpenAICompatProvider
    if name == "manual":
        return ManualProvider()
    if name == "openai_compat":
        return OpenAICompatProvider()
    raise SystemExit(f"unknown provider: {name} (use manual | openai_compat)")


def cmd_render(args: argparse.Namespace) -> None:
    from shotcreator_engine import Template, render_video
    from shotcreator_engine.audio import mux_audio

    template = Template(
        dwell_top=args.dwell_top,
        dwell_bot=args.dwell_bot,
        pan_frac=args.pan_frac,
    )
    segments = list(zip(args.image, args.pan_secs))
    top = _split_lines(args.top)
    bot = _split_lines(args.bot)

    if args.audio:
        silent = args.output + ".silent.mp4"
        render_video(segments, top, bot, silent, template=template)
        mux_audio(silent, args.audio, args.output)
        os.remove(silent)
    else:
        render_video(segments, top, bot, args.output, template=template)
    print("OK ->", args.output)


def cmd_hooks(args: argparse.Namespace) -> None:
    provider = _get_provider(args.provider)
    top, bot = provider.generate_hooks(args.story)
    print("TOP:")
    for ln in top:
        print("  " + ln)
    print("BOTTOM:")
    for ln in bot:
        print("  " + ln)
    if args.caption:
        print("CAPTION:")
        print("  " + provider.generate_caption(args.story, (top, bot)))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shotcreator",
                                description="Vertical video generator (1080x1920)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render screenshot(s) to mp4")
    r.add_argument("--image", action="append", required=True,
                   help="screenshot image (repeatable for multi-segment)")
    r.add_argument("--pan-secs", type=float, action="append", default=[],
                   help="pan seconds per --image (default 9 each)")
    r.add_argument("--top", required=True, help='hook lines, "\\n" separated')
    r.add_argument("--bot", required=True, help='bottom lines, "\\n" separated')
    r.add_argument("--audio", default=None, help="audio file to mux (mp3/m4a)")
    r.add_argument("-o", "--output", required=True, help="output mp4 path")
    r.add_argument("--dwell-top", type=float, default=1.0)
    r.add_argument("--dwell-bot", type=float, default=1.0)
    r.add_argument("--pan-frac", type=float, default=0.75)
    r.set_defaults(func=cmd_render)

    h = sub.add_parser("hooks", help="generate hook text via AI provider")
    h.add_argument("--story", required=True, help="story description")
    h.add_argument("--provider",
                   default=os.environ.get("SHOTCREATOR_AI_PROVIDER", "manual"),
                   help="manual | openai_compat")
    h.add_argument("--caption", action="store_true",
                   help="also generate a caption")
    h.set_defaults(func=cmd_hooks)
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if args.cmd == "render":
        if not args.pan_secs:
            args.pan_secs = [9.0] * len(args.image)
        if len(args.pan_secs) != len(args.image):
            raise SystemExit("--pan-secs count must match --image count")
    args.func(args)


if __name__ == "__main__":
    main()
