"""Orquesta la ingesta de un vídeo: metadata → transcripción → clasificación IA → BBDD."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    SOURCE_LLM,
    STATUS_PENDING,
    ContentTag,
    ContentVideo,
    VideoTag,
)
from . import llm, youtube


class IngestError(Exception):
    pass


def _tag_vocabulary(db: Session, tenant_id: int) -> list[str]:
    tags = db.execute(
        select(ContentTag).where(ContentTag.tenant_id == tenant_id)
    ).scalars().all()
    return [t.label for t in tags]


def _get_or_create_tag(db: Session, tenant_id: int, name: str, ttype: str) -> ContentTag:
    tag = db.execute(
        select(ContentTag).where(
            ContentTag.tenant_id == tenant_id,
            ContentTag.name == name,
            ContentTag.type == ttype,
        )
    ).scalar_one_or_none()
    if tag is None:
        tag = ContentTag(tenant_id=tenant_id, name=name, type=ttype)
        db.add(tag)
        db.flush()
    return tag


def ingest_video(db: Session, tenant_id: int, url_or_id: str) -> ContentVideo:
    """Ingesta (o devuelve si ya existía) un vídeo de YouTube y lo deja en revisión."""
    video_id = youtube.extract_video_id(url_or_id)
    if not video_id:
        raise IngestError("No se reconoció una URL/ID de YouTube válido.")

    # URL que se guarda tal cual (p.ej. con &list=... de playlist) y a la que
    # redirige /r/<token>.
    redirect_url = youtube.redirect_url_for(url_or_id, video_id)

    existing = db.execute(
        select(ContentVideo).where(
            ContentVideo.tenant_id == tenant_id,
            ContentVideo.youtube_video_id == video_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Si re-pegas el mismo vídeo con una URL (p.ej. ahora con playlist), se actualiza.
        if url_or_id.strip().lower().startswith(("http://", "https://")) and redirect_url != existing.youtube_url:
            existing.youtube_url = redirect_url
            db.commit()
            db.refresh(existing)
        return existing

    # 1) Metadata (yt-dlp)
    meta = youtube.fetch_metadata(video_id)

    # 2) Transcripción (opcional)
    transcript, lang = youtube.fetch_transcript(video_id, settings.langs)

    # 3) Clasificación comercial (DeepSeek o mock)
    classification = llm.classify_video(
        title=meta["title"],
        description=meta["description"],
        transcript=transcript,
        tag_vocabulary=_tag_vocabulary(db, tenant_id),
    )

    # 4) Persistir
    video = ContentVideo(
        tenant_id=tenant_id,
        youtube_video_id=meta["youtube_video_id"],
        youtube_url=redirect_url,  # tal cual lo pegó el usuario (puede llevar &list=...)
        title=meta["title"],
        description=meta["description"],
        thumbnail_url=meta["thumbnail_url"],
        duration_seconds=meta["duration_seconds"],
        channel_id=meta["channel_id"],
        channel_name=meta["channel_name"],
        published_at=meta["published_at"],
        transcript=transcript,
        transcript_lang=lang,
        summary=classification["summary"],
        stage=classification["stage"],
        pain_category=classification["pain_category"],
        use_case=classification["use_case"],
        status=STATUS_PENDING,
    )
    db.add(video)
    db.flush()

    for t in classification["tags"]:
        tag = _get_or_create_tag(db, tenant_id, t["name"], t["type"])
        db.add(
            VideoTag(
                video_id=video.id,
                tag_id=tag.id,
                confidence=t["confidence"],
                source=SOURCE_LLM,
                approved=False,  # la persona aprueba en el dashboard
            )
        )

    db.commit()
    db.refresh(video)
    return video
