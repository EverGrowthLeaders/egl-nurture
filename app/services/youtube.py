"""Extracción de metadata y transcripción desde YouTube.

- Metadata: yt-dlp (no requiere API key de Google), con respaldo en oEmbed si
  YouTube bloquea al servidor por "bot" (típico en IPs de datacenter como Dokploy).
- Transcripción: youtube-transcript-api con respaldo en los subtítulos de yt-dlp.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from ..config import settings

YOUTUBE_ID_RE = re.compile(
    r"""(?:
        youtu\.be/ |
        youtube\.com/(?:watch\?(?:.*&)?v= | embed/ | shorts/ | live/ | v/)
    )([0-9A-Za-z_-]{11})""",
    re.VERBOSE,
)


class YouTubeError(Exception):
    """Error recuperable al hablar con YouTube (red, vídeo privado, etc.)."""


def extract_video_id(url_or_id: str) -> str | None:
    """Devuelve el ID de 11 caracteres a partir de una URL o del propio ID."""
    text = (url_or_id or "").strip()
    if not text:
        return None
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", text):
        return text
    match = YOUTUBE_ID_RE.search(text)
    return match.group(1) if match else None


def redirect_url_for(raw_input: str, video_id: str) -> str:
    """URL a la que apuntará el redirect /r/<token>.

    Se guarda la URL TAL CUAL la pega el usuario (p.ej. con &list=... de playlist),
    para que el lead consuma más contenido. Si solo pasó un ID, se construye la URL.
    """
    text = (raw_input or "").strip()
    if text.lower().startswith(("http://", "https://")):
        return text
    return f"https://www.youtube.com/watch?v={video_id}"


def _parse_upload_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fetch_metadata(url_or_id: str) -> dict:
    """Obtiene los metadatos del vídeo mediante yt-dlp."""
    import yt_dlp  # import perezoso para acelerar el arranque

    video_id = extract_video_id(url_or_id)
    if not video_id:
        raise YouTubeError("No se pudo reconocer un ID de vídeo de YouTube en la URL.")

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    # Cookies para evitar el "Sign in to confirm you're not a bot" en servidores.
    if settings.ytdlp_cookiefile:
        opts["cookiefile"] = settings.ytdlp_cookiefile
    if settings.ytdlp_player_client:
        clients = [c.strip() for c in settings.ytdlp_player_client.split(",") if c.strip()]
        opts["extractor_args"] = {"youtube": {"player_client": clients}}

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as err:  # noqa: BLE001 — yt-dlp lanza muchos tipos
        # YouTube suele bloquear IPs de datacenter ("not a bot"): probamos oEmbed,
        # un endpoint público que devuelve título, miniatura y canal sin login.
        fallback = _fetch_metadata_oembed(video_id, url)
        if fallback is not None:
            return fallback
        raise YouTubeError(
            "No se pudo obtener la información del vídeo "
            f"({err}). Si es un servidor, configura YTDLP_COOKIEFILE con un "
            "cookies.txt de YouTube (ver README)."
        ) from err

    return {
        "youtube_video_id": info.get("id", video_id),
        "youtube_url": info.get("webpage_url") or url,
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "thumbnail_url": info.get("thumbnail"),
        "duration_seconds": info.get("duration"),
        "channel_id": info.get("channel_id"),
        "channel_name": info.get("uploader") or info.get("channel"),
        "published_at": _parse_upload_date(info.get("upload_date")),
    }


def _fetch_metadata_oembed(video_id: str, url: str) -> dict | None:
    """Respaldo vía oEmbed de YouTube (público, sin login). Solo da título,
    miniatura y canal; el resto queda vacío y se completa a mano/IA. None si falla."""
    try:
        resp = httpx.get(
            "https://www.youtube.com/oembed",
            params={"url": url, "format": "json"},
            timeout=20,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None

    return {
        "youtube_video_id": video_id,
        "youtube_url": url,
        "title": data.get("title") or "",
        "description": "",
        "thumbnail_url": data.get("thumbnail_url")
        or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "duration_seconds": None,
        "channel_id": None,
        "channel_name": data.get("author_name"),
        "published_at": None,
    }


def fetch_transcript(video_id: str, langs: list[str]) -> tuple[str | None, str | None]:
    """Devuelve (texto, idioma) o (None, None) si no hay transcripción disponible.

    Nunca lanza: la transcripción es opcional en v1.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, None

    cookies = settings.ytdlp_cookiefile or None

    # 1) Intento directo en los idiomas preferidos.
    try:
        entries = YouTubeTranscriptApi.get_transcript(video_id, languages=langs, cookies=cookies)
        text = " ".join(e["text"] for e in entries if e.get("text")).strip()
        if text:
            return text, langs[0]
    except Exception:  # noqa: BLE001
        pass

    # 2) Cualquier transcripción disponible (manual o automática), con traducción
    #    al primer idioma preferido si es posible.
    try:
        listing = YouTubeTranscriptApi.list_transcripts(video_id, cookies=cookies)
        for transcript in listing:
            try:
                if transcript.language_code not in langs and transcript.is_translatable:
                    transcript = transcript.translate(langs[0])
                entries = transcript.fetch()
                text = " ".join(e["text"] for e in entries if e.get("text")).strip()
                if text:
                    return text, transcript.language_code
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass

    return None, None
