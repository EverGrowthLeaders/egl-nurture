"""Generación y tracking de enlaces únicos por (vídeo + lead + contexto)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ContentClickEvent, ContentVideo, TrackedContentLink

_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin caracteres ambiguos

# User-agents que generan "clicks" automáticos (previews de WhatsApp/Telegram/Slack,
# crawlers, etc.). Se registran pero marcados is_bot=True para no ensuciar la señal.
_BOT_MARKERS = (
    "bot", "crawler", "spider", "facebookexternalhit", "whatsapp", "telegrambot",
    "slackbot", "discordbot", "preview", "embedly", "quora link preview", "pinterest",
    "redditbot", "linkedinbot", "bingbot", "duckduckbot", "applebot", "twitterbot",
    "skypeuripreview", "vkshare", "google-structured", "ia_archiver", "petalbot",
)


def _new_token(db: Session, length: int = 7) -> str:
    for _ in range(20):
        token = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        exists = db.execute(
            select(TrackedContentLink.id).where(TrackedContentLink.token == token)
        ).first()
        if not exists:
            return token
    raise RuntimeError("No se pudo generar un token único.")


def hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    digest = hashlib.sha256(f"{settings.secret_key}:{ip}".encode()).hexdigest()
    return digest[:32]


def is_bot(user_agent: str | None) -> bool:
    if not user_agent:
        return True  # sin UA suele ser un bot/preview
    low = user_agent.lower()
    return any(marker in low for marker in _BOT_MARKERS)


def build_url(token: str, contact_id: str | None = None) -> str:
    """URL trackeada. Si hay contact_id, va en la query (?c=...) para visibilidad
    y atribución en GHL (también permite merge fields tipo ?c={{contact.id}})."""
    url = f"{settings.base_url.rstrip('/')}/r/{token}"
    if contact_id:
        url += f"?c={quote(str(contact_id), safe='')}"
    return url


def render_message(template: str, *, setter: str, link_url: str, contact_name: str = "", pain: str = "") -> str:
    """Rellena los placeholders de la plantilla y garantiza que el enlace esté presente."""
    out = template
    for key, value in {
        "setter": setter or "",
        "link": link_url,
        "contact_name": contact_name or "",
        "pain": pain or "",
    }.items():
        out = out.replace("{" + key + "}", value)
    # Seguridad: si el operador borró {link}, añadimos el enlace al final.
    if link_url and link_url not in out:
        out = f"{out.rstrip()}\n\n{link_url}"
    return out.strip()


def create_link(
    db: Session,
    *,
    tenant,
    video_id: int,
    message: str | None = None,
    context: str = "",
    setter_name: str | None = None,
    contact_id: str | None = None,
    contact_name: str | None = None,
    conversation_id: str | None = None,
    appointment_id: str | None = None,
) -> TrackedContentLink:
    """Crea el link único y construye el mensaje final (plantilla → texto con enlace)."""
    video = db.get(ContentVideo, video_id)
    token = _new_token(db)
    setter = (setter_name or tenant.default_setter or "").strip()

    # El {link} del mensaje: siempre el link trackeado (redirect + contact_id),
    # que mantiene el preview de la miniatura y registra el click.
    link_in_message = build_url(token, contact_id)

    template = message if message is not None else tenant.message_template
    final_message = render_message(
        template,
        setter=setter,
        link_url=link_in_message,
        contact_name=(contact_name or "").strip(),
        pain=(video.pain_category if video else "") or "",
    )

    link = TrackedContentLink(
        tenant_id=tenant.id,
        token=token,
        video_id=video_id,
        message=final_message,
        context=context,
        setter_name=setter or None,
        contact_id=contact_id,
        contact_name=contact_name,
        conversation_id=conversation_id,
        appointment_id=appointment_id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def record_click(
    db: Session,
    *,
    token: str,
    user_agent: str | None,
    ip: str | None,
    referer: str | None,
    contact_id: str | None = None,
) -> TrackedContentLink | None:
    """Registra el click y devuelve el link (o None si el token no existe).

    contact_id viene de la query ?c=... de la URL; si el link no tenía contacto
    asociado (p.ej. link reutilizable con merge field de GHL), se asocia ahora.
    """
    link = db.execute(
        select(TrackedContentLink).where(TrackedContentLink.token == token)
    ).scalar_one_or_none()
    if link is None:
        return None

    if contact_id and not link.contact_id:
        link.contact_id = contact_id
    effective_contact = link.contact_id or contact_id

    bot = is_bot(user_agent)
    now = datetime.now(timezone.utc)

    db.add(
        ContentClickEvent(
            tenant_id=link.tenant_id,
            link_id=link.id,
            token=token,
            video_id=link.video_id,
            contact_id=effective_contact,
            clicked_at=now,
            user_agent=(user_agent or "")[:512],
            referer=(referer or "")[:512] or None,
            ip_hash=hash_ip(ip),
            is_bot=bot,
        )
    )

    link.click_count += 1
    if not bot:
        link.human_click_count += 1
        if link.first_clicked_at is None:
            link.first_clicked_at = now
        link.last_clicked_at = now

    db.commit()
    db.refresh(link)
    return link
