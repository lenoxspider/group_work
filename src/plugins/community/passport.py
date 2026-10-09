"""Passport renderer - composes a citizen's identity card as a PNG.

Deliberately free of Discord and network access: it takes already-fetched data
and avatar bytes and returns PNG bytes, so it can be tested with synthetic
inputs and run in a worker thread without touching the event loop.
"""

import io
import logging
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger("plugins.community.passport")

# Squid Game palette
PINK = (255, 0, 144)
DARK = (16, 16, 20)
CARD = (30, 30, 38)
LIGHT = (238, 238, 244)
MUTED = (150, 150, 162)

W, H = 1000, 620
PHOTO_W, PHOTO_H = 200, 240

_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
_REG = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "C:/Windows/Fonts/consola.ttf",
]


@lru_cache(maxsize=None)
def _font(paths: Tuple[str, ...], size: int) -> ImageFont.ImageFont:
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    # Last resort: Pillow's bundled bitmap font. Ugly, but never crashes.
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


@dataclass
class PassportData:
    display_name: str
    citizen_no: str
    status: str                       # "CITIZEN" | "CATIZEN"
    balance: int
    signed_at: Optional[str] = None   # ISO timestamp or None
    avatar_bytes: Optional[bytes] = None


def _photo(avatar_bytes: Optional[bytes]) -> Image.Image:
    box = Image.new("RGB", (PHOTO_W, PHOTO_H), (52, 52, 62))
    if not avatar_bytes:
        return box
    try:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
    except Exception:
        return box
    return ImageOps.fit(avatar, (PHOTO_W, PHOTO_H), Image.Resampling.LANCZOS)


def _signed_label(signed_at: Optional[str]) -> str:
    if not signed_at:
        return "NOT SIGNED"
    try:
        return datetime.fromisoformat(signed_at).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "NOT SIGNED"


def _field(draw, x: int, y: int, label: str, value: str) -> None:
    draw.text((x, y), label.upper(), font=_font(tuple(_REG), 15), fill=MUTED)
    draw.text((x, y + 20), str(value), font=_font(tuple(_BOLD), 25), fill=LIGHT)


def _mrz(name: str, citizen_no: str) -> Tuple[str, str]:
    clean = "".join(c if (c.isascii() and c.isalnum()) else "<" for c in name.upper())
    line1 = f"P<CVL{clean}"
    line2 = f"{citizen_no}<CVL{clean}"
    return line1[:44].ljust(44, "<"), line2[:44].ljust(44, "<")


def render_passport(data: PassportData) -> bytes:
    img = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    # Card
    draw.rounded_rectangle([16, 16, W - 16, H - 16], radius=22, fill=CARD, outline=PINK, width=2)

    # Header
    draw.text((48, 42), "COLLECTIVE OF TOVARISHCH", font=_font(tuple(_BOLD), 33), fill=LIGHT)
    draw.text((48, 86), "PASSPORT", font=_font(tuple(_BOLD), 21), fill=PINK)
    draw.text((W - 48, 82), "○ △ □", anchor="ra", font=_font(tuple(_BOLD), 26), fill=MUTED)
    draw.line([(48, 126), (W - 48, 126)], fill=PINK, width=3)

    # Photo
    photo = _photo(data.avatar_bytes)
    img.paste(photo, (48, 152))
    draw.rectangle([48, 152, 48 + PHOTO_W, 152 + PHOTO_H], outline=PINK, width=2)
    draw.text((48, 152 + PHOTO_H + 10), "BEARER", font=_font(tuple(_REG), 14), fill=MUTED)

    # Fields
    fx = 300
    rows = [
        ("Name", data.display_name),
        ("Citizen No.", data.citizen_no),
        ("Status", data.status.upper()),
        ("Balance", f"{data.balance:,} spi"),
        ("Signed", _signed_label(data.signed_at)),
    ]
    y = 152
    for label, value in rows:
        _field(draw, fx, y, label, value)
        y += 62

    # Machine-readable zone (decorative)
    mono = _font(tuple(_MONO), 18)
    l1, l2 = _mrz(data.display_name, data.citizen_no)
    draw.text((48, H - 96), l1, font=mono, fill=MUTED)
    draw.text((48, H - 70), l2, font=mono, fill=MUTED)
    draw.text((W - 48, H - 70), "FRONT MAN", anchor="ra", font=_font(tuple(_BOLD), 16), fill=PINK)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
