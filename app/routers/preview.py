"""Sirve la miniatura compuesta (estilo vídeo de YouTube) usada como og:image."""

import re

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, Response

from ..services.thumbnail import compose_youtube_preview

router = APIRouter()

_YT_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")


@router.get("/thumb/{yt_id}.jpg", include_in_schema=False)
def thumb(yt_id: str):
    if not _YT_ID.match(yt_id):
        return RedirectResponse("https://www.youtube.com/", status_code=302)
    data = compose_youtube_preview(yt_id)
    if data is None:
        # Si falla la composición, cae a la miniatura normal de YouTube.
        return RedirectResponse(
            f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg", status_code=302
        )
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
