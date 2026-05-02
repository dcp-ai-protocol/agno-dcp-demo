"""Server-rendered HTML pages.

Single-page app pattern: one ``GET /`` route returns the dashboard
shell; HTMX + SSE handle every interaction after that.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.agent import get_service
from app.config import get_settings
from app.tools import CUSTOMER_FIXTURES

router = APIRouter(tags=["pages"])

_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    service = get_service()
    bundle = service.agent.dcp_bundle
    return _templates.TemplateResponse(
        request,
        "index.html",
        {
            "settings": settings,
            "bundle": bundle,
            "customers": list(CUSTOMER_FIXTURES.values()),
        },
    )


@router.get("/healthz", response_class=HTMLResponse)
async def healthz() -> HTMLResponse:
    return HTMLResponse("ok")
