"""FastAPI entry point.

Wires the agent lifecycle into application startup/shutdown, mounts
static assets, registers all routers.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.agent import get_service
from app.config import get_settings
from app.routes import agent as agent_routes
from app.routes import audit as audit_routes
from app.routes import pages as pages_routes


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _setup_logging(settings.app_log_level)
    service = get_service()
    await service.initialize(settings)
    try:
        yield
    finally:
        await service.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.demo_title,
        description=(
            "End-to-end demo of agno-dcp: cryptographic governance "
            "for Agno agents. Identity, signed policy gating, "
            "tamper-evident audit, and offline-verifiable Compliance "
            "Bundles for a banking collections workflow."
        ),
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(pages_routes.router)
    app.include_router(agent_routes.router)
    app.include_router(audit_routes.router)
    return app


app = create_app()
