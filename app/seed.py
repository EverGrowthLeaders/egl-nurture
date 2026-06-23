"""Vocabulario inicial de etiquetas comerciales (dolor / fase / objeción)."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ContentTag

# (tipo, nombre) — ampliable desde el dashboard o desde código.
SEED_TAGS: list[tuple[str, str]] = [
    # Dolores
    ("dolor", "no-show"),
    ("dolor", "leads se enfrían"),
    ("dolor", "falta de seguimiento"),
    ("dolor", "comerciales saturados"),
    ("dolor", "velocidad de contacto"),
    ("dolor", "base de datos sin explotar"),
    ("dolor", "no cierran"),
    ("dolor", "pocos leads"),
    # Fases del embudo
    ("fase", "pre-call"),
    ("fase", "post-call"),
    ("fase", "nurturing"),
    ("fase", "reactivación"),
    # Objeciones
    ("objecion", "mándame info"),
    ("objecion", "lo veo luego"),
    ("objecion", "es caro"),
    ("objecion", "tengo que pensarlo"),
]


def seed_tags(db: Session, tenant_id: int) -> int:
    """Inserta las etiquetas que falten para un tenant. Idempotente."""
    existing = {
        (t.type, t.name)
        for t in db.execute(
            select(ContentTag).where(ContentTag.tenant_id == tenant_id)
        ).scalars().all()
    }
    created = 0
    for tag_type, name in SEED_TAGS:
        if (tag_type, name) not in existing:
            db.add(ContentTag(tenant_id=tenant_id, type=tag_type, name=name))
            created += 1
    if created:
        db.commit()
    return created
