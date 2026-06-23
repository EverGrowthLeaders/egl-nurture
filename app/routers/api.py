"""API JSON (multi-tenant) — para integrar con n8n / GHL / Chatwoot.

Autenticación por tenant con la cabecera `X-Api-Key` (cada tenant tiene la suya,
visible en Settings)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import api_tenant
from ..db import get_db
from ..models import STATUS_ACTIVE, ContentVideo, Tenant, TrackedContentLink
from ..schemas import (
    ApproveRequest,
    CreateLinkRequest,
    IngestRequest,
    RecommendRequest,
    link_to_dict,
    video_to_dict,
)
from ..services import links as links_service
from ..services import recommend as recommend_service
from ..services.ingest import IngestError, ingest_video
from ..services.llm import LLMError
from ..services.youtube import YouTubeError

router = APIRouter(prefix="/api", tags=["api"])


def _get_video(db: Session, tenant: Tenant, video_id: int) -> ContentVideo:
    video = db.get(ContentVideo, video_id)
    if not video or video.tenant_id != tenant.id:
        raise HTTPException(404, "Vídeo no encontrado")
    return video


@router.get("/videos")
def list_videos(
    status: str | None = None,
    tenant: Tenant = Depends(api_tenant),
    db: Session = Depends(get_db),
) -> list[dict]:
    stmt = (
        select(ContentVideo)
        .where(ContentVideo.tenant_id == tenant.id)
        .order_by(ContentVideo.created_at.desc())
    )
    if status:
        stmt = stmt.where(ContentVideo.status == status)
    return [video_to_dict(v) for v in db.execute(stmt).scalars().all()]


@router.get("/videos/{video_id}")
def get_video(
    video_id: int, tenant: Tenant = Depends(api_tenant), db: Session = Depends(get_db)
) -> dict:
    return video_to_dict(_get_video(db, tenant, video_id))


@router.post("/videos")
def ingest(
    body: IngestRequest, tenant: Tenant = Depends(api_tenant), db: Session = Depends(get_db)
) -> dict:
    try:
        video = ingest_video(db, tenant.id, body.url)
    except (IngestError, YouTubeError) as err:
        raise HTTPException(400, str(err)) from err
    except LLMError as err:
        raise HTTPException(502, f"Error del modelo: {err}") from err
    return video_to_dict(video)


@router.post("/videos/{video_id}/approve")
def approve(
    video_id: int,
    body: ApproveRequest,
    tenant: Tenant = Depends(api_tenant),
    db: Session = Depends(get_db),
) -> dict:
    video = _get_video(db, tenant, video_id)
    if body.approve_all_tags:
        for vt in video.tags:
            vt.approved = True
    video.status = STATUS_ACTIVE
    db.commit()
    db.refresh(video)
    return video_to_dict(video)


@router.post("/recommend")
def recommend(
    body: RecommendRequest, tenant: Tenant = Depends(api_tenant), db: Session = Depends(get_db)
) -> dict:
    try:
        result = recommend_service.recommend(db, tenant.id, body.context)
    except LLMError as err:
        raise HTTPException(400, str(err)) from err
    return {
        "video": video_to_dict(result["video"]),
        "reasoning": result["reasoning"],
        "confidence": result["confidence"],
        "alternatives": [video_to_dict(v) for v in result["alternatives"]],
    }


@router.get("/links")
def list_links(
    contact_id: str | None = None,
    video_id: int | None = None,
    tenant: Tenant = Depends(api_tenant),
    db: Session = Depends(get_db),
) -> list[dict]:
    """¿Abrió el contacto el vídeo? Filtrable por contact_id y/o video_id."""
    stmt = (
        select(TrackedContentLink)
        .where(TrackedContentLink.tenant_id == tenant.id)
        .order_by(TrackedContentLink.created_at.desc())
        .options(selectinload(TrackedContentLink.video))
    )
    if contact_id:
        stmt = stmt.where(TrackedContentLink.contact_id == contact_id)
    if video_id is not None:
        stmt = stmt.where(TrackedContentLink.video_id == video_id)
    return [link_to_dict(link) for link in db.execute(stmt).scalars().all()]


@router.get("/links/{token}")
def get_link(
    token: str, tenant: Tenant = Depends(api_tenant), db: Session = Depends(get_db)
) -> dict:
    link = db.execute(
        select(TrackedContentLink)
        .where(TrackedContentLink.token == token, TrackedContentLink.tenant_id == tenant.id)
        .options(selectinload(TrackedContentLink.video))
    ).scalar_one_or_none()
    if not link:
        raise HTTPException(404, "Link no encontrado")
    return link_to_dict(link)


@router.post("/links")
def create_link(
    body: CreateLinkRequest, tenant: Tenant = Depends(api_tenant), db: Session = Depends(get_db)
) -> dict:
    _get_video(db, tenant, body.video_id)
    link = links_service.create_link(
        db,
        tenant=tenant,
        video_id=body.video_id,
        message=body.message,
        context=body.context,
        setter_name=body.setter_name,
        contact_id=body.contact_id,
        contact_name=body.contact_name,
        conversation_id=body.conversation_id,
        appointment_id=body.appointment_id,
    )
    return link_to_dict(link)
