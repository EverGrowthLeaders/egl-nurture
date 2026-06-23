"""Servidor de redirección: /r/{token}.

Registra el click y devuelve una página con etiquetas Open Graph (miniatura del
vídeo) que redirige al destino. Así se mantiene la PREVIEW de la miniatura en
WhatsApp/Telegram/etc. al mismo tiempo que se TRACKEA el click.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import links
from ..templating import templates

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    # Detrás de Traefik/Dokploy la IP real viene en X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _thumbnail(video) -> str:
    if video.thumbnail_url:
        return video.thumbnail_url
    return f"https://i.ytimg.com/vi/{video.youtube_video_id}/hqdefault.jpg"


@router.get("/r/{token}", include_in_schema=False)
def follow_link(
    token: str,
    request: Request,
    c: str | None = None,  # contact_id (de GHL) que puede venir en la URL
    db: Session = Depends(get_db),
):
    link = links.record_click(
        db,
        token=token,
        contact_id=c,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
        referer=request.headers.get("referer"),
    )
    if link is None or link.video is None:
        return RedirectResponse(url="https://www.youtube.com/", status_code=302)

    video = link.video
    description = (video.summary or video.description or "")[:200]
    return templates.TemplateResponse(
        request,
        "redirect.html",
        {
            "request": request,
            "title": video.title or "Vídeo",
            "description": description,
            "image": _thumbnail(video),
            "target": video.youtube_url,
        },
    )
