"""Servidor de redirección: /r/{token} registra el click y redirige al vídeo."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import links

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    # Detrás de Traefik/Dokploy la IP real viene en X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/r/{token}", include_in_schema=False)
def follow_link(token: str, request: Request, db: Session = Depends(get_db)):
    link = links.record_click(
        db,
        token=token,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
        referer=request.headers.get("referer"),
    )
    if link is None:
        return RedirectResponse(url="https://www.youtube.com/", status_code=302)
    return RedirectResponse(url=link.video.youtube_url, status_code=302)
