"""Arranque: crea el tenant/usuario inicial (opcional vía env), reasigna datos
previos a un tenant por defecto y siembra etiquetas por tenant."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    ContentClickEvent,
    ContentTag,
    ContentVideo,
    Tenant,
    TrackedContentLink,
    User,
)
from .security import hash_password, new_api_key
from .seed import seed_tags

_SCOPED = (ContentVideo, ContentTag, TrackedContentLink, ContentClickEvent)


def create_tenant(db: Session, *, name: str, email: str, password: str) -> Tenant:
    """Crea un tenant + su usuario inicial. Lanza si el email ya existe."""
    email = email.strip().lower()
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise ValueError(f"Ya existe un usuario con el email {email}")
    tenant = Tenant(name=name.strip() or email, api_key=new_api_key())
    db.add(tenant)
    db.flush()
    db.add(User(tenant_id=tenant.id, email=email, password_hash=hash_password(password)))
    seed_tags(db, tenant.id)
    db.commit()
    db.refresh(tenant)
    return tenant


def _has_orphan_rows(db: Session) -> bool:
    for model in _SCOPED:
        n = db.execute(
            select(func.count()).select_from(model).where(model.tenant_id.is_(None))
        ).scalar()
        if n:
            return True
    return False


def bootstrap(db: Session) -> None:
    # 1) Cuenta inicial desde env (cómodo para el primer deploy en Dokploy).
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        email = settings.bootstrap_admin_email.strip().lower()
        if not db.execute(select(User).where(User.email == email)).scalar_one_or_none():
            create_tenant(
                db,
                name=settings.bootstrap_tenant_name,
                email=email,
                password=settings.bootstrap_admin_password,
            )

    # 2) Datos previos sin tenant → asignarlos a un tenant por defecto.
    if _has_orphan_rows(db):
        default = db.execute(select(Tenant).order_by(Tenant.id)).scalars().first()
        if default is None:
            default = Tenant(name="Default", api_key=new_api_key())
            db.add(default)
            db.flush()
            seed_tags(db, default.id)
        for model in _SCOPED:
            db.execute(
                update(model).where(model.tenant_id.is_(None)).values(tenant_id=default.id)
            )
        db.commit()

    # 3) Asegura api_key y etiquetas para todos los tenants.
    for tenant in db.execute(select(Tenant)).scalars().all():
        if not tenant.api_key:
            tenant.api_key = new_api_key()
        seed_tags(db, tenant.id)
    db.commit()
