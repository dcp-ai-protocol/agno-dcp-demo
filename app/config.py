"""Application configuration loaded from environment variables.

Uses pydantic-settings to allow .env files locally and Fly secrets in
production. All values have safe defaults so the app boots without
configuration; the demo defaults to mock LLM and a local SQLite file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the demo service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Branding (visible in the UI)
    demo_title: str = "DCP-AI Banking Demo"
    demo_bank_name: str = "Demo Trust Bank"
    demo_human_principal: str = "ops@demo-trust-bank.example"

    # Storage
    dcp_db_path: str = "app/data/agent.db"

    # LLM
    llm_provider: Literal["mock", "anthropic", "openai"] = "mock"
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Server
    app_host: str = "0.0.0.0"  # noqa: S104  (intentional for container deploys)
    app_port: int = 8000
    app_log_level: str = "INFO"

    # Build / runtime metadata (filled at deploy time)
    git_sha: str = Field(default="local", description="Set at container build")
    deploy_region: str = Field(default="local")

    @property
    def db_absolute_path(self) -> Path:
        """Resolve the SQLite path against the app root."""
        path = Path(self.dcp_db_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parent.parent / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the singleton settings instance.

    The first call resolves the environment; later calls return the
    cached instance. Tests can monkey-patch ``_settings`` to swap.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
