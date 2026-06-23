"""Autenticación: sesión de usuario (UI) y API key por tenant (API)."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Tenant, User


class NotAuthenticated(Exception):
    """La lanza la UI para redirigir a /login."""


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("uid")
    if not uid:
        raise NotAuthenticated()
    user = db.get(User, uid)
    if user is None:
        request.session.clear()
        raise NotAuthenticated()
    return user


def current_tenant(user: User = Depends(current_user)) -> Tenant:
    return user.tenant


def api_tenant(
    x_api_key: str | None = Header(default=None), db: Session = Depends(get_db)
) -> Tenant:
    """Resuelve el tenant a partir de la cabecera X-Api-Key (para la API)."""
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta la cabecera X-Api-Key")
    tenant = db.execute(
        select(Tenant).where(Tenant.api_key == x_api_key)
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Api-Key inválida")
    return tenant
