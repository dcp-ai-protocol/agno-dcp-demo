"""Shared pytest fixtures for the demo's tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.agent import DemoAgentService
from app.config import Settings


def _settings(tmp_path: Path) -> Settings:
    """Build a Settings object pointing at an isolated tmp DB."""
    return Settings(
        dcp_db_path=str(tmp_path / "agent.db"),
        demo_bank_name="Test Trust Bank",
        demo_human_principal="test@example.com",
        llm_provider="mock",
    )


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    return asyncio.DefaultEventLoopPolicy()


@pytest_asyncio.fixture
async def service(tmp_path: Path) -> AsyncIterator[DemoAgentService]:
    s = DemoAgentService()
    await s.initialize(_settings(tmp_path))
    try:
        yield s
    finally:
        await s.shutdown()


@pytest_asyncio.fixture
async def http_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """ASGI in-process HTTP client.

    The test app shares a fresh ``DemoAgentService`` because the
    module-level singleton is reset per-test by monkey-patching.
    """
    import app.agent as agent_module
    import app.config as config_module

    # Reset module-level state so each test gets a clean agent + db
    agent_module._service = None
    config_module._settings = _settings(tmp_path)

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger lifespan startup
        async with app.router.lifespan_context(app):
            yield client
