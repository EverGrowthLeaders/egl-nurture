"""Servidor de redirección: /r/{token}.

Registra el click y devuelve una página con Open Graph (miniatura estilo YouTube)
que redirige al destino. Además, si fue una apertura HUMANA y el tenant tiene GHL
configurado, escribe el campo personalizado del contacto (en segundo plano).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Tenant
from ..services import ghl, links
from ..templating import templates

router = APIRouter()
log = logging.getLogger("egl.redirect")


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _preview_image(video) -> str:
    return f"{settings.base_url.rstrip('/')}/thumb/{video.youtube_video_id}.jpg"


def _write_ghl(token: str, contact_id: str, field_id: str, field_type: str, override: str) -> None:
    """Best-effort: escribe el campo en GHL; nunca rompe el redirect."""
    try:
        ghl.update_contact_field(
            token=token, contact_id=contact_id, field_id=field_id,
            data_type=field_type, override=override,
        )
    except ghl.GHLError as err:
        log.warning("GHL write falló: %s", err)


@router.get("/r/{token}", include_in_schema=False)
def follow_link(
    token: str,
    request: Request,
    background: BackgroundTasks,
    c: str | None = None,  # contact_id (de GHL) que puede venir en la URL
    db: Session = Depends(get_db),
):
    user_agent = request.headers.get("user-agent")
    link = links.record_click(
        db,
        token=token,
        contact_id=c,
        user_agent=user_agent,
        ip=_client_ip(request),
        referer=request.headers.get("referer"),
    )
    if link is None or link.video is None:
        return RedirectResponse(url="https://www.youtube.com/", status_code=302)

    # Apertura humana → escribir en GHL el campo elegido (en segundo plano).
    if not links.is_bot(user_agent) and link.contact_id:
        tenant = db.get(Tenant, link.tenant_id)
        if tenant and tenant.ghl_ready:
            background.add_task(
                _write_ghl,
                tenant.ghl_token, link.contact_id,
                tenant.ghl_field_id, tenant.ghl_field_type, tenant.ghl_field_value,
            )

    video = link.video
    return templates.TemplateResponse(
        request,
        "redirect.html",
        {
            "request": request,
            "title": video.title or "Vídeo",
            "description": (video.summary or video.description or "")[:200],
            "image": _preview_image(video),
            "target": video.youtube_url,
        },
    )
