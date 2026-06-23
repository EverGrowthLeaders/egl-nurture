"""Autenticación mínima para los endpoints /api/* mutantes."""

from fastapi import Header, HTTPException, status

from .config import settings


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    """Si ADMIN_TOKEN está definido, exige la cabecera X-Admin-Token correcta.

    Si no está definido (desarrollo), no exige nada.
    """
    if not settings.admin_token:
        return
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Admin-Token inválido o ausente.",
        )
