"""Punto de entrada de la app FastAPI."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .db import init_db
from .templating import BASE_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="EGL Nurture Signal", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "version": __version__, "llm": "live" if settings.llm_enabled else "demo"}


# Routers (se importan después de crear `templates` para evitar ciclos).
from .routers import api, redirect, ui  # noqa: E402

app.include_router(redirect.router)
app.include_router(api.router)
app.include_router(ui.router)
