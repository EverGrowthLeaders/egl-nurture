"""Dashboard web (Jinja2): ingesta, revisión/aprobación, recomendación y tracking."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..db import get_db
from ..models import (
    SOURCE_MANUAL,
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    STATUS_PENDING,
    ContentTag,
    ContentVideo,
    TrackedContentLink,
    VideoTag,
)
from ..services import links as links_service
from ..services import recommend as recommend_service
from ..services.ingest import IngestError, ingest_video
from ..services.llm import LLMError
from ..services.youtube import YouTubeError
from ..templating import templates

router = APIRouter(include_in_schema=False)


def _ctx(request: Request, **kwargs) -> dict:
    base = {
        "request": request,
        "msg": request.query_params.get("msg"),
        "err": request.query_params.get("err"),
        "message_template": settings.message_template,
        "default_setter": settings.default_setter,
    }
    base.update(kwargs)
    return base


# ── Biblioteca ───────────────────────────────────────────────────────────────


@router.get("/")
def index(request: Request, status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    stmt = select(ContentVideo).order_by(ContentVideo.created_at.desc())
    if status in (STATUS_PENDING, STATUS_ACTIVE, STATUS_ARCHIVED):
        stmt = stmt.where(ContentVideo.status == status)
    if q:
        stmt = stmt.where(ContentVideo.title.ilike(f"%{q}%"))
    videos = db.execute(stmt.options(selectinload(ContentVideo.tags))).scalars().all()

    counts = dict(
        db.execute(select(ContentVideo.status, func.count()).group_by(ContentVideo.status)).all()
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        _ctx(request, videos=videos, counts=counts, status=status, q=q or ""),
    )


@router.post("/ingest")
def ingest(request: Request, url: str = Form(...), db: Session = Depends(get_db)):
    try:
        video = ingest_video(db, url)
    except (IngestError, YouTubeError) as err:
        return RedirectResponse(f"/?err={err}", status_code=303)
    except LLMError as err:
        return RedirectResponse(f"/?err=Error del modelo: {err}", status_code=303)
    return RedirectResponse(
        f"/videos/{video.id}?msg=Vídeo ingerido. Revisa la clasificación y actívalo.",
        status_code=303,
    )


# ── Detalle / revisión de un vídeo ────────────────────────────────────────────


@router.get("/videos/{video_id}")
def video_detail(video_id: int, request: Request, db: Session = Depends(get_db)):
    video = db.get(ContentVideo, video_id)
    if not video:
        return RedirectResponse("/?err=Vídeo no encontrado", status_code=303)
    links = (
        db.execute(
            select(TrackedContentLink)
            .where(TrackedContentLink.video_id == video_id)
            .order_by(TrackedContentLink.created_at.desc())
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request,
        "video_detail.html",
        _ctx(request, video=video, links=links, tag_types=("dolor", "fase", "objecion")),
    )


@router.post("/videos/{video_id}/update")
def video_update(
    video_id: int,
    request: Request,
    summary: str = Form(""),
    stage: str = Form(""),
    pain_category: str = Form(""),
    use_case: str = Form(""),
    youtube_url: str = Form(""),
    approved_tag: list[int] = Form(default=[]),
    new_tag_name: str = Form(""),
    new_tag_type: str = Form(""),
    db: Session = Depends(get_db),
):
    video = db.get(ContentVideo, video_id)
    if not video:
        return RedirectResponse("/?err=Vídeo no encontrado", status_code=303)

    video.summary = summary.strip()
    video.stage = stage.strip() or None
    video.pain_category = pain_category.strip() or None
    video.use_case = use_case.strip()
    if youtube_url.strip():
        video.youtube_url = youtube_url.strip()  # URL de redirect (puede llevar &list=...)

    approved_ids = set(approved_tag)
    for vt in video.tags:
        vt.approved = vt.id in approved_ids

    if new_tag_name.strip() and new_tag_type.strip() in ("dolor", "fase", "objecion"):
        name = new_tag_name.strip()
        ttype = new_tag_type.strip()
        tag = db.execute(
            select(ContentTag).where(ContentTag.name == name, ContentTag.type == ttype)
        ).scalar_one_or_none()
        if tag is None:
            tag = ContentTag(name=name, type=ttype)
            db.add(tag)
            db.flush()
        exists = db.execute(
            select(VideoTag).where(VideoTag.video_id == video.id, VideoTag.tag_id == tag.id)
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                VideoTag(
                    video_id=video.id, tag_id=tag.id, confidence=1.0,
                    source=SOURCE_MANUAL, approved=True,
                )
            )

    db.commit()
    return RedirectResponse(f"/videos/{video_id}?msg=Cambios guardados.", status_code=303)


@router.post("/videos/{video_id}/status")
def video_status(video_id: int, request: Request, status: str = Form(...), db: Session = Depends(get_db)):
    video = db.get(ContentVideo, video_id)
    if not video:
        return RedirectResponse("/?err=Vídeo no encontrado", status_code=303)
    if status in (STATUS_PENDING, STATUS_ACTIVE, STATUS_ARCHIVED):
        video.status = status
        db.commit()
    label = {STATUS_ACTIVE: "activado", STATUS_ARCHIVED: "archivado", STATUS_PENDING: "marcado en revisión"}
    return RedirectResponse(
        f"/videos/{video_id}?msg=Vídeo {label.get(status, 'actualizado')}.", status_code=303
    )


# ── Recomendación (prescripción) ──────────────────────────────────────────────


@router.get("/recommend")
def recommend_form(request: Request):
    return templates.TemplateResponse(request, "recommend.html", _ctx(request, result=None, context=""))


@router.post("/recommend")
def recommend_run(request: Request, context: str = Form(...), db: Session = Depends(get_db)):
    try:
        result = recommend_service.recommend(db, context.strip())
    except LLMError as err:
        return templates.TemplateResponse(
            request, "recommend.html", _ctx(request, result=None, context=context, err=str(err))
        )
    return templates.TemplateResponse(
        request, "recommend.html", _ctx(request, result=result, context=context)
    )


# ── Links trackeados ──────────────────────────────────────────────────────────


@router.post("/links")
def create_link(
    request: Request,
    video_id: int = Form(...),
    message: str = Form(""),
    context: str = Form(""),
    setter_name: str = Form(""),
    contact_id: str = Form(""),
    contact_name: str = Form(""),
    conversation_id: str = Form(""),
    appointment_id: str = Form(""),
    db: Session = Depends(get_db),
):
    if not db.get(ContentVideo, video_id):
        return RedirectResponse("/?err=Vídeo no encontrado", status_code=303)
    link = links_service.create_link(
        db,
        video_id=video_id,
        message=message if message.strip() else None,  # vacío → plantilla por defecto
        context=context.strip(),
        setter_name=setter_name.strip() or None,
        contact_id=contact_id.strip() or None,
        contact_name=contact_name.strip() or None,
        conversation_id=conversation_id.strip() or None,
        appointment_id=appointment_id.strip() or None,
    )
    return RedirectResponse(f"/links/{link.token}?msg=Link generado.", status_code=303)


@router.get("/links")
def links_list(request: Request, db: Session = Depends(get_db)):
    links = (
        db.execute(
            select(TrackedContentLink)
            .order_by(TrackedContentLink.created_at.desc())
            .options(selectinload(TrackedContentLink.video))
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request, "links.html", _ctx(request, links=links, build_url=links_service.build_url)
    )


@router.get("/links/{token}")
def link_detail(token: str, request: Request, db: Session = Depends(get_db)):
    link = db.execute(
        select(TrackedContentLink).where(TrackedContentLink.token == token)
    ).scalar_one_or_none()
    if not link:
        return RedirectResponse("/links?err=Link no encontrado", status_code=303)
    clicks = sorted(link.clicks, key=lambda c: c.clicked_at, reverse=True)
    return templates.TemplateResponse(
        request,
        "link_detail.html",
        _ctx(request, link=link, clicks=clicks, url=links_service.build_url(link.token, link.contact_id)),
    )
