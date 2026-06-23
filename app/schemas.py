"""Esquemas de entrada/salida para la API JSON."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .models import ContentVideo, TrackedContentLink
from .services import links as links_service


class IngestRequest(BaseModel):
    url: str = Field(..., description="URL o ID de YouTube")


class RecommendRequest(BaseModel):
    context: str = Field(..., description="Diagnóstico / dolor del lead")


class CreateLinkRequest(BaseModel):
    video_id: int
    context: str = ""  # diagnóstico / dolor del lead
    setter_name: str | None = None  # con quién habló el lead (p.ej. "Laura")
    # Si se omite, se usa la plantilla por defecto (settings.message_template).
    # Acepta placeholders {setter} {link} {contact_name} {pain}.
    message: str | None = None
    contact_id: str | None = None
    contact_name: str | None = None
    conversation_id: str | None = None
    appointment_id: str | None = None


class ApproveRequest(BaseModel):
    approve_all_tags: bool = True


def video_to_dict(v: ContentVideo) -> dict:
    return {
        "id": v.id,
        "youtube_video_id": v.youtube_video_id,
        "youtube_url": v.youtube_url,
        "title": v.title,
        "thumbnail_url": v.thumbnail_url,
        "duration_seconds": v.duration_seconds,
        "channel_name": v.channel_name,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "has_transcript": bool(v.transcript),
        "summary": v.summary,
        "stage": v.stage,
        "pain_category": v.pain_category,
        "use_case": v.use_case,
        "status": v.status,
        "tags": [
            {
                "name": vt.tag.name,
                "type": vt.tag.type,
                "confidence": vt.confidence,
                "source": vt.source,
                "approved": vt.approved,
            }
            for vt in v.tags
        ],
    }


def link_to_dict(link: TrackedContentLink) -> dict:
    return {
        "token": link.token,
        "url": links_service.build_url(link.token, link.contact_id),
        "redirect_url": link.video.youtube_url if link.video else None,
        "video_id": link.video_id,
        "setter_name": link.setter_name,
        "contact_id": link.contact_id,
        "contact_name": link.contact_name,
        "conversation_id": link.conversation_id,
        "appointment_id": link.appointment_id,
        "context": link.context,
        "message": link.message,
        "sent_at": link.sent_at.isoformat() if link.sent_at else None,
        "first_clicked_at": link.first_clicked_at.isoformat() if link.first_clicked_at else None,
        "last_clicked_at": link.last_clicked_at.isoformat() if link.last_clicked_at else None,
        "click_count": link.click_count,
        "human_click_count": link.human_click_count,
        "is_hot": link.is_hot,
    }
