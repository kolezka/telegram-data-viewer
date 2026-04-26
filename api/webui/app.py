"""FastAPI app factory and lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from webui.loader import load_telegram_data
from webui.state import AppState


WEB_DIST = Path(__file__).resolve().parent.parent.parent / "web" / "dist"


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    """Build the FastAPI app, loading data_dir into app.state at startup.

    `data_dir` may be None for tests that override state directly via
    `app.state.app_state = AppState(...)` after construction.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if data_dir is not None:
            app.state.app_state = load_telegram_data(data_dir)
        else:
            app.state.app_state = getattr(app.state, "app_state", AppState())
        yield

    app = FastAPI(
        title="tg-viewer",
        description="Telegram cache viewer API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # API routers FIRST. The order matters because StaticFiles(html=True) below
    # is a catch-all that swallows any unmatched path.
    from webui.routers import databases, users, chats, messages, media, stats, export_data
    app.include_router(databases.router)
    app.include_router(users.router)
    app.include_router(chats.router)
    app.include_router(messages.router)
    app.include_router(media.router)
    app.include_router(stats.router)
    app.include_router(export_data.router)

    # If web/dist exists, mount it at /. Otherwise fall back to the transitional
    # pages router (templates/index.html). Task 15 removes the fallback.
    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="webdist")
    else:
        from webui.routers import pages
        app.include_router(pages.router)

    return app
