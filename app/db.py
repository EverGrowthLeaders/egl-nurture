"""Motor de base de datos y sesiones. Compatible con Postgres (producción) y SQLite (local)."""

import os
import time
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.database_url
    if url.startswith("sqlite"):
        # Asegura que exista la carpeta del fichero .db
        db_path = url.replace("sqlite:///", "")
        if db_path and db_path not in (":memory:",):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def wait_for_db(retries: int = 20, delay: float = 1.5) -> None:
    """Espera a que la base de datos acepte conexiones (Postgres puede tardar en arrancar)."""
    last_err: Exception | None = None
    for _ in range(retries):
        try:
            with engine.connect():
                return
        except Exception as err:  # noqa: BLE001
            last_err = err
            time.sleep(delay)
    raise RuntimeError(f"No se pudo conectar a la base de datos: {last_err}")


def init_db() -> None:
    """Crea las tablas y siembra el vocabulario de etiquetas comerciales."""
    from . import models  # noqa: F401  (registra los modelos en Base.metadata)
    from .seed import seed_tags

    wait_for_db()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_tags(db)
