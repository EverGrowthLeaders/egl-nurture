"""Punto de entrada de la app FastAPI."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__
from .auth import NotAuthenticated
from .config import settings
from .db import init_db
from .templating import BASE_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="EGL Nurture Signal", version=__version__, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    same_site="lax",
    max_age=60 * 60 * 24 * 14,  # 14 días
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.exception_handler(NotAuthenticated)
async def _redirect_to_login(request: Request, exc: NotAuthenticated):
    return RedirectResponse("/login", status_code=303)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok", "version": __version__, "llm": "live" if settings.llm_enabled else "demo"}


# Routers (se importan después de crear `templates` para evitar ciclos).
from .routers import account, api, preview, redirect, ui  # noqa: E402
from .routers import settings as settings_router  # noqa: E402

app.include_router(redirect.router)
app.include_router(preview.router)
app.include_router(account.router)
app.include_router(api.router)
app.include_router(settings_router.router)
app.include_router(ui.router)
