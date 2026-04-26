"""FastAPI app factory and lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from webui.loader import load_telegram_data
from webui.state import AppState


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

    from webui.routers import pages
    app.include_router(pages.router)
    from webui.routers import databases
    app.include_router(databases.router)
    from webui.routers import users
    app.include_router(users.router)
    from webui.routers import chats
    app.include_router(chats.router)
    from webui.routers import messages
    app.include_router(messages.router)
    from webui.routers import media
    app.include_router(media.router)
    from webui.routers import stats
    app.include_router(stats.router)
    from webui.routers import export_data
    app.include_router(export_data.router)
    return app
