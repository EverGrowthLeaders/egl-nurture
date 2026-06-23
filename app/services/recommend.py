"""Recomendación de vídeo para un lead concreto (prescripción de contenido)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import STATUS_ACTIVE, ContentVideo
from . import llm


def _candidate_dict(video: ContentVideo) -> dict:
    return {
        "id": video.id,
        "title": video.title,
        "summary": video.summary,
        "stage": video.stage,
        "pain_category": video.pain_category,
        "tags": [vt.tag.label for vt in video.approved_tags],
    }


def recommend(db: Session, lead_context: str) -> dict:
    """Devuelve la recomendación + el objeto de vídeo elegido y sus alternativas.

    Resultado:
      {
        "video": ContentVideo,
        "reasoning": str, "confidence": float,
        "alternatives": [ContentVideo, ...],
        "lead_context": str,
      }
    """
    videos = (
        db.execute(
            select(ContentVideo)
            .where(ContentVideo.status == STATUS_ACTIVE)
            .options(selectinload(ContentVideo.tags))
        )
        .scalars()
        .all()
    )
    if not videos:
        raise llm.LLMError(
            "No hay vídeos ACTIVOS en la biblioteca. Ingesta y aprueba al menos uno."
        )

    by_id = {v.id: v for v in videos}
    candidates = [_candidate_dict(v) for v in videos]

    result = llm.recommend_video(lead_context=lead_context, candidates=candidates)

    chosen = by_id[result["video_id"]]
    alternatives = [by_id[i] for i in result["alternatives"] if i in by_id]
    return {
        "video": chosen,
        "reasoning": result["reasoning"],
        "confidence": result["confidence"],
        "alternatives": alternatives,
        "lead_context": lead_context,
    }
