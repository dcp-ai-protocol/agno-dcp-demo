"""Application-scoped DCPAgent factory + lifecycle.

The agent is constructed once at startup and reused across requests.
Its Citizenship Bundle is generated on the first boot and persisted
to the SQLite-backed audit store, so subsequent boots reuse the same
identity. This is the production pattern: agents are long-lived
identities, not request-scoped.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from agno_dcp import (
    DCPAgent,
    MerkleAuditChain,
    PolicyEngine,
    SQLiteStorage,
)
from agno_dcp.identity import (
    CitizenshipBundle,
    deserialize_bundle,
    generate_citizenship_bundle,
)

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


_POLICIES_PATH = Path(__file__).resolve().parent / "policies.yaml"
_KEY_FILE = "agent_secret_key.txt"


class DemoAgentService:
    """Owns the singleton DCPAgent + audit chain + storage.

    Constructed eagerly at app startup via ``initialize`` and torn
    down on shutdown. Routes call :meth:`get_agent` to obtain the
    live instance.
    """

    def __init__(self) -> None:
        self._agent: DCPAgent | None = None
        self._storage: SQLiteStorage | None = None
        self._chain: MerkleAuditChain | None = None
        self._engine: PolicyEngine | None = None
        self._settings: Settings | None = None
        self._lock = asyncio.Lock()
        self._listeners: list[asyncio.Queue[dict[str, Any]]] = []

    async def initialize(self, settings: Settings | None = None) -> None:
        """Boot the agent. Idempotent: safe to call twice."""
        async with self._lock:
            if self._agent is not None:
                return
            self._settings = settings or get_settings()
            db_path = self._settings.db_absolute_path
            self._storage = SQLiteStorage(str(db_path))
            await self._storage.initialize()

            bundle, secret_b64 = await self._load_or_create_identity(db_path.parent)

            self._chain = MerkleAuditChain(storage=self._storage)
            self._engine = PolicyEngine.from_yaml(_POLICIES_PATH)

            self._agent = DCPAgent(
                name=f"Collections Agent — {self._settings.demo_bank_name}",
                dcp_human_principal=self._settings.demo_human_principal,
                dcp_security_tier="tier-3",
                dcp_audit_chain=self._chain,
                dcp_policy_engine=self._engine,
                dcp_strict_mode=True,
                dcp_existing_bundle=bundle,
                dcp_secret_key_b64=secret_b64,
            )
            await self._agent.dcp_initialize()
            self._wire_audit_broadcast()
            logger.info(
                "Agent ready: %s · tier=%s · principal=%s",
                self._agent.dcp_bundle.agent_name,
                self._agent.dcp_security_tier,
                self._agent.dcp_human_principal,
            )

    async def _load_or_create_identity(self, dir_path: Path) -> tuple[CitizenshipBundle, str]:
        """Return (bundle, secret_key_b64), creating both on first boot.

        The secret key is persisted beside the audit DB. In production
        the secret would be fetched from an HSM / KMS rather than
        living on disk; for a public demo we rely on volume isolation
        plus chmod 600. Both files survive across container restarts
        when the directory is on a Fly persistent volume.
        """
        assert self._storage is not None
        assert self._settings is not None

        key_dir = dir_path / "keys"
        key_dir.mkdir(parents=True, exist_ok=True)
        key_path = key_dir / _KEY_FILE
        marker_path = dir_path / "agent_id.txt"

        if key_path.exists() and marker_path.exists():
            secret_b64 = key_path.read_text(encoding="utf-8").strip()
            agent_id = marker_path.read_text(encoding="utf-8").strip()
            stored = await self._storage.get_citizenship_bundle(agent_id)
            if secret_b64 and stored is not None:
                return deserialize_bundle(stored), secret_b64

        bundle, fresh_secret = generate_citizenship_bundle(
            agent_name=f"Collections Agent — {self._settings.demo_bank_name}",
            human_principal=self._settings.demo_human_principal,
            security_tier="tier-3",
            metadata={
                "deployment": self._settings.deploy_region,
                "git_sha": self._settings.git_sha,
            },
        )
        marker_path.write_text(bundle.agent_id, encoding="utf-8")
        key_path.write_text(fresh_secret, encoding="utf-8")
        try:
            key_path.chmod(0o600)
        except OSError:  # pragma: no cover  (Windows etc.)
            pass
        return bundle, fresh_secret

    def _wire_audit_broadcast(self) -> None:
        """Wrap ``chain.append`` so every entry fans out to listeners."""
        assert self._chain is not None
        original_append = self._chain.append

        async def append_and_broadcast(event: Any) -> Any:
            entry = await original_append(event)
            payload = {
                "entry_index": entry.entry_index,
                "event_type": entry.event_type.value,
                "agent_id": entry.agent_id,
                "payload": entry.payload,
                "prev_hash": entry.prev_hash,
                "entry_hash": entry.entry_hash,
                "created_at": entry.created_at,
            }
            # Fan out without blocking the append.
            for q in list(self._listeners):
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:  # pragma: no cover
                    pass
            return entry

        self._chain.append = append_and_broadcast  # type: ignore[method-assign]

    def subscribe_audit(self) -> asyncio.Queue[dict[str, Any]]:
        """Register a queue that receives every new audit entry.

        Caller must :meth:`unsubscribe_audit` when finished, otherwise
        the queue leaks. The SSE route handles this automatically.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._listeners.append(q)
        return q

    def unsubscribe_audit(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._listeners.remove(q)
        except ValueError:
            pass

    @property
    def agent(self) -> DCPAgent:
        if self._agent is None:
            raise RuntimeError("DemoAgentService not initialized")
        return self._agent

    @property
    def chain(self) -> MerkleAuditChain:
        if self._chain is None:
            raise RuntimeError("DemoAgentService not initialized")
        return self._chain

    @property
    def storage(self) -> SQLiteStorage:
        if self._storage is None:
            raise RuntimeError("DemoAgentService not initialized")
        return self._storage

    @property
    def engine(self) -> PolicyEngine:
        if self._engine is None:
            raise RuntimeError("DemoAgentService not initialized")
        return self._engine

    async def shutdown(self) -> None:
        if self._storage is not None:
            await self._storage.close()


# Module-level singleton accessed via FastAPI dependency.
_service: DemoAgentService | None = None


def get_service() -> DemoAgentService:
    global _service
    if _service is None:
        _service = DemoAgentService()
    return _service


def serializable(obj: Any) -> Any:
    """Best-effort JSON-clean of objects returned by tools.

    Pydantic models, datetimes, and bytes get coerced; everything else
    is round-tripped through ``json.dumps(default=str)``.
    """
    return json.loads(json.dumps(obj, default=str))
