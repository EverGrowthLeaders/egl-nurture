"""Datos de demostración: vídeos de ejemplo ya activos, sin tocar la red ni la API.

Útil para probar el dashboard, la recomendación y el tracking sin depender de
YouTube ni de la API key de DeepInfra. Ejecutar con:  python -m app.demo
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, init_db
from .models import (
    SOURCE_MANUAL,
    STATUS_ACTIVE,
    ContentTag,
    ContentVideo,
    VideoTag,
)

# (youtube_id, título, resumen, stage, dolor, use_case, [(tipo, etiqueta), ...])
DEMO_VIDEOS = [
    (
        "dQw4w9WgXcQ",
        "No-show: cómo conseguir +80% de asistencia a tus llamadas",
        "Sistema de recordatorios y confirmación para que los leads agendados sí aparezcan a la llamada.",
        "pre-call",
        "no-show",
        "Mandar a leads que agendan pero no asisten a la reunión.",
        [("dolor", "no-show"), ("fase", "pre-call")],
    ),
    (
        "9bZkp7q19f0",
        "Por qué tus seguimientos comerciales no convierten",
        "Explica por qué los leads se enfrían cuando el comercial tarda en contactar y cómo arreglarlo.",
        "pre-call",
        "leads se enfrían",
        "Leads que entran pero el equipo tarda en contactar; bases de datos que se enfrían.",
        [("dolor", "leads se enfrían"), ("dolor", "falta de seguimiento"), ("fase", "pre-call")],
    ),
    (
        "kJQP7kiw5Fk",
        "Reactivación de base de datos: vender a leads antiguos",
        "Cómo reactivar leads dormidos y sacar reuniones de una base de datos antigua sin gastar más en ads.",
        "reactivación",
        "base de datos sin explotar",
        "Empresas con muchos leads antiguos en la BBDD sin explotar.",
        [("dolor", "base de datos sin explotar"), ("fase", "reactivación")],
    ),
    (
        "3JZ_D3ELwOQ",
        "Velocidad de contacto: ingesta comercial en menos de 5 minutos",
        "Sistema de ingesta comercial para contactar al lead en caliente y multiplicar la conversión.",
        "pre-call",
        "velocidad de contacto",
        "Equipos donde el comercial tarda en contactar al lead nuevo.",
        [("dolor", "velocidad de contacto"), ("dolor", "comerciales saturados"), ("fase", "pre-call")],
    ),
]


def seed_demo_videos(db: Session, tenant_id: int) -> int:
    created = 0
    for yt_id, title, summary, stage, pain, use_case, tags in DEMO_VIDEOS:
        exists = db.execute(
            select(ContentVideo).where(
                ContentVideo.tenant_id == tenant_id,
                ContentVideo.youtube_video_id == yt_id,
            )
        ).scalar_one_or_none()
        if exists:
            continue
        video = ContentVideo(
            tenant_id=tenant_id,
            youtube_video_id=yt_id,
            youtube_url=f"https://www.youtube.com/watch?v={yt_id}",
            title=title,
            description=summary,
            thumbnail_url=f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg",
            duration_seconds=540,
            channel_name="Demo",
            summary=summary,
            stage=stage,
            pain_category=pain,
            use_case=use_case,
            status=STATUS_ACTIVE,
        )
        db.add(video)
        db.flush()
        for ttype, name in tags:
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
            db.add(
                VideoTag(
                    video_id=video.id,
                    tag_id=tag.id,
                    confidence=1.0,
                    source=SOURCE_MANUAL,
                    approved=True,
                )
            )
        created += 1
    db.commit()
    return created


def main() -> None:
    init_db()
    from .bootstrap import create_tenant
    from .models import User

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == "demo@demo.com")).scalar_one_or_none()
        tenant = user.tenant if user else create_tenant(
            db, name="Demo", email="demo@demo.com", password="demo1234"
        )
        n = seed_demo_videos(db, tenant.id)
    print(f"Vídeos de demo insertados: {n} · login: demo@demo.com / demo1234")


if __name__ == "__main__":
    main()
