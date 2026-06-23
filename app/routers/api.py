"""API JSON — pensada para integrarse con n8n / GHL / Chatwoot."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..models import STATUS_ACTIVE, ContentVideo
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


@router.get("/videos")
def list_videos(status: str | None = None, db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(ContentVideo).order_by(ContentVideo.created_at.desc())
    if status:
        stmt = stmt.where(ContentVideo.status == status)
    return [video_to_dict(v) for v in db.execute(stmt).scalars().all()]


@router.get("/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db)) -> dict:
    video = db.get(ContentVideo, video_id)
    if not video:
        raise HTTPException(404, "Vídeo no encontrado")
    return video_to_dict(video)


@router.post("/videos", dependencies=[Depends(require_admin)])
def ingest(body: IngestRequest, db: Session = Depends(get_db)) -> dict:
    try:
        video = ingest_video(db, body.url)
    except (IngestError, YouTubeError) as err:
        raise HTTPException(400, str(err)) from err
    except LLMError as err:
        raise HTTPException(502, f"Error del modelo: {err}") from err
    return video_to_dict(video)


@router.post("/videos/{video_id}/approve", dependencies=[Depends(require_admin)])
def approve(video_id: int, body: ApproveRequest, db: Session = Depends(get_db)) -> dict:
    video = db.get(ContentVideo, video_id)
    if not video:
        raise HTTPException(404, "Vídeo no encontrado")
    if body.approve_all_tags:
        for vt in video.tags:
            vt.approved = True
    video.status = STATUS_ACTIVE
    db.commit()
    db.refresh(video)
    return video_to_dict(video)


@router.post("/recommend")
def recommend(body: RecommendRequest, db: Session = Depends(get_db)) -> dict:
    try:
        result = recommend_service.recommend(db, body.context)
    except LLMError as err:
        raise HTTPException(400, str(err)) from err
    return {
        "video": video_to_dict(result["video"]),
        "reasoning": result["reasoning"],
        "message": result["message"],
        "confidence": result["confidence"],
        "alternatives": [video_to_dict(v) for v in result["alternatives"]],
    }


@router.post("/links", dependencies=[Depends(require_admin)])
def create_link(body: CreateLinkRequest, db: Session = Depends(get_db)) -> dict:
    if not db.get(ContentVideo, body.video_id):
        raise HTTPException(404, "Vídeo no encontrado")
    link = links_service.create_link(
        db,
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
