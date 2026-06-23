"""Modelos SQLAlchemy: las 5 tablas de la biblioteca de activos comerciales."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Estados del vídeo dentro del flujo "IA propone → tú apruebas → activo".
STATUS_PENDING = "pending_review"
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"

# Tipos de etiqueta.
TAG_TYPES = ("dolor", "fase", "objecion")

# Origen de una asignación de etiqueta.
SOURCE_MANUAL = "manual"
SOURCE_LLM = "llm_suggested"
SOURCE_AUTO = "auto"


class ContentVideo(Base):
    __tablename__ = "content_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_video_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    youtube_url: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Transcripción (opcional en v1, clave para la selección en v2+).
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_lang: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Inteligencia comercial (propuesta por DeepSeek, editable por la persona).
    summary: Mapped[str] = mapped_column(Text, default="")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pain_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    use_case: Mapped[str] = mapped_column(Text, default="")

    status: Mapped[str] = mapped_column(String(32), default=STATUS_PENDING, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tags: Mapped[list["VideoTag"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    links: Mapped[list["TrackedContentLink"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )

    @property
    def duration_label(self) -> str:
        if not self.duration_seconds:
            return "—"
        m, s = divmod(int(self.duration_seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    @property
    def approved_tags(self) -> list["VideoTag"]:
        return [vt for vt in self.tags if vt.approved]


class ContentTag(Base):
    __tablename__ = "content_tags"
    __table_args__ = (UniqueConstraint("name", "type", name="uq_tag_name_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)  # dolor | fase | objecion

    videos: Mapped[list["VideoTag"]] = relationship(back_populates="tag")

    @property
    def label(self) -> str:
        return f"{self.type}: {self.name}"


class VideoTag(Base):
    __tablename__ = "video_tags"
    __table_args__ = (UniqueConstraint("video_id", "tag_id", name="uq_video_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("content_videos.id", ondelete="CASCADE"))
    tag_id: Mapped[int] = mapped_column(ForeignKey("content_tags.id", ondelete="CASCADE"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(32), default=SOURCE_LLM)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)

    video: Mapped["ContentVideo"] = relationship(back_populates="tags")
    tag: Mapped["ContentTag"] = relationship(back_populates="videos")


class TrackedContentLink(Base):
    __tablename__ = "tracked_content_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("content_videos.id", ondelete="CASCADE"))

    # Identificadores externos (GHL / Chatwoot / agenda). Strings, no FKs.
    contact_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    setter_name: Mapped[str | None] = mapped_column(String(128), nullable=True)  # con quién habló el lead
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    appointment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    context: Mapped[str] = mapped_column(Text, default="")  # dolor / diagnóstico del lead
    message: Mapped[str] = mapped_column(Text, default="")  # mensaje personalizado generado

    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    first_clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_clicked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    human_click_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    video: Mapped["ContentVideo"] = relationship(back_populates="links")
    clicks: Mapped[list["ContentClickEvent"]] = relationship(
        back_populates="link", cascade="all, delete-orphan"
    )

    @property
    def is_hot(self) -> bool:
        """Lead "caliente": al menos un click humano (no preview/bot)."""
        return self.human_click_count > 0


class ContentClickEvent(Base):
    __tablename__ = "content_click_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("tracked_content_links.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(32), index=True)
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    contact_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    clicked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    referer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False)

    link: Mapped["TrackedContentLink"] = relationship(back_populates="clicks")
