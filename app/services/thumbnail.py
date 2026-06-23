"""Compone una miniatura que parece un vídeo de YouTube: la imagen del vídeo +
botón de play centrado + marca de agua "YouTube" abajo a la derecha.

Se usa como og:image del link trackeado, de modo que en WhatsApp/Telegram el
preview se vea como un vídeo de YouTube aunque el enlace sea de nuestro dominio.
"""

from __future__ import annotations

import io

import httpx

W, H = 1280, 720
_THUMB_NAMES = ("maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg")


def _download(yt_id: str):
    from PIL import Image

    for name in _THUMB_NAMES:
        try:
            r = httpx.get(
                f"https://i.ytimg.com/vi/{yt_id}/{name}", timeout=15, follow_redirects=True
            )
        except httpx.HTTPError:
            continue
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            # YouTube devuelve un placeholder gris 120x90 si no existe ese tamaño.
            if img.size[0] >= 320:
                return img
    return None


def _cover(img, w: int, h: int):
    """Escala y recorta al centro para llenar w×h (object-fit: cover)."""
    from PIL import Image

    sw, sh = img.size
    scale = max(w / sw, h / sh)
    nw, nh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def _font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)  # Pillow >= 10
    except TypeError:
        return ImageFont.load_default()


def _draw_play_button(draw, cx: int, cy: int):
    """Botón de play translúcido centrado, estilo reproductor."""
    r = 78
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(15, 15, 15, 165))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255, 60), width=3)
    draw.polygon([(cx - 24, cy - 36), (cx - 24, cy + 36), (cx + 38, cy)], fill=(255, 255, 255, 240))


def _draw_youtube_watermark(draw, w: int, h: int):
    """Logo de YouTube (rectángulo rojo con triángulo) + 'YouTube' abajo a la derecha."""
    margin = 32
    word = "YouTube"
    font = _font(36)
    try:
        bbox = draw.textbbox((0, 0), word, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        toff = bbox[1]
    except Exception:  # noqa: BLE001
        tw, th, toff = 130, 28, 0

    mark_w, mark_h, gap = 56, 38, 10
    total_w = mark_w + gap + tw
    x = w - margin - total_w
    y = h - margin - mark_h

    # Sombra suave para legibilidad sobre miniaturas claras.
    draw.rounded_rectangle([x - 10, y - 8, x + total_w + 10, y + mark_h + 8], radius=10, fill=(0, 0, 0, 90))
    # Marca roja con triángulo blanco.
    draw.rounded_rectangle([x, y, x + mark_w, y + mark_h], radius=9, fill=(255, 0, 0, 240))
    tcx, tcy = x + mark_w // 2, y + mark_h // 2
    draw.polygon([(tcx - 8, tcy - 10), (tcx - 8, tcy + 10), (tcx + 11, tcy)], fill=(255, 255, 255, 255))
    # Palabra "YouTube".
    ty = y + (mark_h - th) // 2 - toff
    draw.text((x + mark_w + gap, ty), word, font=font, fill=(255, 255, 255, 245))


def compose_youtube_preview(yt_id: str) -> bytes | None:
    """Devuelve los bytes JPEG de la miniatura compuesta, o None si no se pudo."""
    from PIL import Image, ImageDraw

    base = _download(yt_id)
    if base is None:
        return None

    canvas = _cover(base, W, H).convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    _draw_play_button(draw, W // 2, H // 2)
    _draw_youtube_watermark(draw, W, H)

    out = Image.alpha_composite(canvas, overlay).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()
