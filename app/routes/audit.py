"""Audit-chain HTTP routes: live stream, list, verify, export.

The interesting one is ``GET /api/audit/stream``. It opens a
Server-Sent Events connection that pushes every new audit entry the
moment ``MerkleAuditChain.append`` writes one. The UI uses this to
animate the audit log without polling.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from agno_dcp.audit.exporter import ComplianceBundleExporter
from agno_dcp.audit.verifier import AuditChainVerifier
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from app.agent import DemoAgentService, get_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/entries")
async def list_entries(
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return audit entries in chronological order, newest last."""
    service: DemoAgentService = get_service()
    entries = await service.storage.get_audit_entries(start=offset)
    sliced = entries[: max(0, limit)]
    return {
        "entries": sliced,
        "total": len(entries),
        "offset": offset,
        "limit": limit,
    }


@router.get("/stream")
async def stream_entries() -> EventSourceResponse:
    """Server-Sent Events stream of new audit entries.

    Each event has type ``audit`` and a JSON-encoded ``data`` payload
    with the full :class:`AuditEntry` shape. Browsers reconnect
    automatically on disconnect.
    """
    service: DemoAgentService = get_service()
    queue = service.subscribe_audit()

    async def event_generator() -> Any:
        # Send a hello event so clients can confirm connection
        yield {"event": "hello", "data": json.dumps({"connected": True})}
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "audit", "data": json.dumps(payload, default=str)}
                except TimeoutError:
                    # Keepalive comment so proxies don't close the conn
                    yield {"event": "ping", "data": "{}"}
        finally:
            service.unsubscribe_audit(queue)

    return EventSourceResponse(event_generator())


@router.get("/verify")
async def verify_chain() -> dict[str, Any]:
    """Run the offline verifier and return the structured result.

    Surfaces what an external auditor would see if they ran
    ``agno-dcp verify --sqlite agent.db`` against this database.
    """
    service: DemoAgentService = get_service()
    verifier = AuditChainVerifier(service.storage)
    result = await verifier.verify()
    return result.model_dump()


@router.post("/seal")
async def seal_root() -> dict[str, Any]:
    """Compute and persist a fresh signed Merkle root snapshot."""
    service: DemoAgentService = get_service()
    sig = await service.chain.seal_root()
    return sig.model_dump()


_BUNDLES_DIR_NAME = "compliance_bundles"


@router.post("/export")
async def export_bundle(framework: str = "eu_ai_act") -> dict[str, Any]:
    """Generate a signed Compliance Bundle ZIP.

    ``framework`` selects which mapping to embed. Returns metadata
    plus a download URL the UI can offer to the user.
    """
    if framework not in ("eu_ai_act", "nist_ai_rmf"):
        raise HTTPException(status_code=400, detail="framework must be eu_ai_act or nist_ai_rmf")

    service: DemoAgentService = get_service()
    # Always seal a fresh root before exporting so the bundle is current.
    await service.chain.seal_root()

    bundles_dir = service.storage.path
    bundles_root = Path(bundles_dir).parent / _BUNDLES_DIR_NAME
    bundles_root.mkdir(parents=True, exist_ok=True)

    exporter = ComplianceBundleExporter(service.chain, service.storage)
    path = await exporter.export(framework=framework, output_dir=bundles_root)

    size = path.stat().st_size
    return {
        "framework": framework,
        "filename": path.name,
        "size_bytes": size,
        "download_url": f"/api/audit/bundles/{path.name}",
    }


@router.get("/bundles/{filename}")
async def download_bundle(filename: str) -> FileResponse:
    """Stream a previously-exported bundle to the browser."""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")
    if not filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="only .zip exports are served")
    service = get_service()
    bundles_root = Path(service.storage.path).parent / _BUNDLES_DIR_NAME
    target = bundles_root / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="bundle not found")
    return FileResponse(
        path=target,
        media_type="application/zip",
        filename=filename,
    )


@router.post("/reset")
async def reset_demo() -> dict[str, Any]:
    """Wipe the audit chain back to genesis. For demo replay only.

    Bound by application-layer convention; production deployments
    should never expose this. The Fly deployment exposes it because
    the demo is meant to be replayable; other deployments should
    remove this route.
    """
    from agno_dcp.audit.chain import AuditEvent, AuditEventType

    service = get_service()
    storage = service.storage

    def _wipe() -> None:
        conn = storage._connect()  # type: ignore[attr-defined]
        conn.execute("DELETE FROM dcp_audit_chain")
        conn.execute("DELETE FROM dcp_audit_roots")
        conn.execute("DELETE FROM dcp_intents")
        conn.execute("DELETE FROM dcp_policy_decisions")
        # Reclaim entry_index so the next event starts at 1
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN "
            "('dcp_audit_chain','dcp_audit_roots','dcp_intents','dcp_policy_decisions')"
        )

    await asyncio.to_thread(_wipe)
    # Re-seal a fresh AGENT_CREATED event so the UI shows continuity.
    bundle = service.agent.dcp_bundle
    await service.chain.append(
        AuditEvent(
            event_type=AuditEventType.AGENT_CREATED,
            agent_id=bundle.agent_id,
            payload={
                "agent_name": bundle.agent_name,
                "human_principal": bundle.human_principal,
                "security_tier": bundle.security_tier,
                "reset": True,
            },
        )
    )
    return {"ok": True, "reset_at": "now"}
