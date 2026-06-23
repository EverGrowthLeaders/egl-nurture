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


def _add_missing_columns() -> None:
    """Migración ligera: añade tenant_id a tablas que ya existían (pre multi-tenant).

    create_all() no altera tablas existentes, así que añadimos la columna a mano.
    Idempotente y compatible con Postgres y SQLite.
    """
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = ("content_videos", "content_tags", "tracked_content_links", "content_click_events")
    with engine.begin() as conn:
        for table in tables:
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if "tenant_id" not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER"))


def init_db() -> None:
    """Crea/migra tablas, asegura un tenant para los datos previos y siembra etiquetas."""
    from . import models  # noqa: F401  (registra los modelos en Base.metadata)
    from .bootstrap import bootstrap

    wait_for_db()
    Base.metadata.create_all(bind=engine)  # crea tenants/users y tablas nuevas
    _add_missing_columns()                  # añade tenant_id a tablas antiguas
    with SessionLocal() as db:
        bootstrap(db)
