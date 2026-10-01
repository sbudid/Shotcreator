"""Static frame layout: navy background, autofit hook text, rounded card mask."""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

from .template import Template

_FONT_WEIGHT = "ExtraBold"  # Inter variable-weight name used by the originals

# Checked in order when $SHOTCREATOR_FONT is not set.
_FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def resolve_font_path() -> str | None:
    """Font file to use: $SHOTCREATOR_FONT first, then system fallbacks."""
    env = os.environ.get("SHOTCREATOR_FONT")
    if env and os.path.isfile(env):
        return env
    for path in _FALLBACK_FONTS:
        if os.path.isfile(path):
            return path
    return None


def load_font(size: int):
    """Bold display font at *size*; tries the ExtraBold variation when available."""
    path = resolve_font_path()
    if path is None:
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # very old Pillow without size support
            return ImageFont.load_default()
    font = ImageFont.truetype(path, size)
    try:
        font.set_variation_by_name(_FONT_WEIGHT)
    except Exception:
        pass  # static fonts (DejaVu etc.) have no variations
    return font


def fit_font(draw: ImageDraw.ImageDraw, lines, start_size: int, max_w: int,
             lh_ratio: float = 1.22, min_size: int = 36):
    """Shrink the font until every line fits max_w. Returns (font, line_height)."""
    size = start_size
    while size >= min_size:
        font = load_font(size)
        if all(draw.textlength(ln, font=font) <= max_w for ln in lines):
            return font, int(size * lh_ratio)
        size -= 4
    return load_font(min_size), int(min_size * lh_ratio)


def rounded_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=r, fill=255)
    return mask


def make_background(t: Template, top_lines, bot_lines) -> Image.Image:
    """Navy background with centered hook text at top and bottom."""
    bg = Image.new("RGB", (t.width, t.height), t.bg_color)
    d = ImageDraw.Draw(bg)

    f_top, lh_top = fit_font(d, top_lines, t.top_start_size, t.max_text_w,
                             t.line_height_ratio, t.min_font_size)
    y = t.top_y
    for ln in top_lines:
        tw = d.textlength(ln, font=f_top)
        d.text(((t.width - tw) / 2, y), ln, font=f_top, fill=t.text_color)
        y += lh_top

    f_bot, lh_bot = fit_font(d, bot_lines, t.bot_start_size, t.max_text_w,
                             t.line_height_ratio, t.min_font_size)
    y = t.bot_y
    for ln in bot_lines:
        tw = d.textlength(ln, font=f_bot)
        d.text(((t.width - tw) / 2, y), ln, font=f_bot, fill=t.text_color)
        y += lh_bot
    return bg


def prepare_shot(img: Image.Image, t: Template) -> Image.Image:
    """Scale a screenshot to the card width; pad if shorter than the card."""
    w = t.card_w
    h = int(img.height * (w / img.width))
    img = img.resize((w, h), Image.LANCZOS)
    if h < t.card_h:
        canvas = Image.new("RGB", (w, t.card_h), (0, 0, 0))
        canvas.paste(img, (0, (t.card_h - h) // 2))
        return canvas
    return img
