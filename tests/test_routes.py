"""HTTP-level tests against the FastAPI ASGI app."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_index_renders(http_client) -> None:
    r = await http_client.get("/")
    assert r.status_code == 200
    assert "DCP-AI Banking Demo" in r.text
    # Banking-grade UI markers
    for marker in (
        "Cryptographic governance",
        "Tamper-evident audit chain",
        "One-click scenarios",
        "Compliance surface",
        "Citizenship Bundle",
    ):
        assert marker in r.text, f"missing UI marker: {marker}"


@pytest.mark.asyncio
async def test_healthz(http_client) -> None:
    r = await http_client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"


@pytest.mark.asyncio
async def test_agent_info(http_client) -> None:
    r = await http_client.get("/api/agent/info")
    assert r.status_code == 200
    data = r.json()
    assert data["agent_id"].startswith("agent:")
    assert data["security_tier"] == "tier-3"
    assert "lookup_customer" in data["tools"]
    assert len(data["customers"]) == 3


@pytest.mark.asyncio
async def test_agent_run_unknown_tool(http_client) -> None:
    r = await http_client.post(
        "/api/agent/run",
        json={"tool_name": "definitely_not_a_tool", "args": {}},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_agent_run_lookup(http_client) -> None:
    r = await http_client.post(
        "/api/agent/run",
        json={"tool_name": "lookup_customer", "args": {"customer_id": "C-100422"}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["approved"] is True
    assert data["result"]["found"] is True


@pytest.mark.asyncio
async def test_scenario_low_risk(http_client) -> None:
    r = await http_client.post(
        "/api/agent/scenario",
        json={"scenario": "low_risk"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["scenario"] == "low_risk"
    assert data["executed_steps"] == 3
    assert all(t["approved"] for t in data["transcript"])


@pytest.mark.asyncio
async def test_scenario_high_risk_denies(http_client) -> None:
    r = await http_client.post(
        "/api/agent/scenario",
        json={"scenario": "high_risk"},
    )
    assert r.status_code == 200
    data = r.json()
    # Stops on the first deny
    assert data["executed_steps"] == 2
    last = data["transcript"][-1]
    assert last["approved"] is False
    assert "20%" in last["reason"]


@pytest.mark.asyncio
async def test_scenario_restricted_channel(http_client) -> None:
    r = await http_client.post(
        "/api/agent/scenario",
        json={"scenario": "restricted_channel"},
    )
    assert r.status_code == 200
    data = r.json()
    last = data["transcript"][-1]
    assert last["approved"] is False
    assert "Phone" in last["reason"]


@pytest.mark.asyncio
async def test_audit_verify_after_workload(http_client) -> None:
    await http_client.post("/api/agent/scenario", json={"scenario": "low_risk"})
    r = await http_client.get("/api/audit/verify")
    assert r.status_code == 200
    data = r.json()
    assert data["chain_intact"] is True
    assert data["entries_checked"] >= 9  # 3 steps x 3 entries + AGENT_CREATED


@pytest.mark.asyncio
async def test_audit_export(http_client) -> None:
    await http_client.post("/api/agent/scenario", json={"scenario": "low_risk"})
    r = await http_client.post("/api/audit/export?framework=nist_ai_rmf")
    assert r.status_code == 200
    data = r.json()
    assert data["framework"] == "nist_ai_rmf"
    assert data["filename"].endswith(".zip")
    assert data["size_bytes"] > 100

    # Now download it
    download = await http_client.get(data["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"


@pytest.mark.asyncio
async def test_audit_export_invalid_framework(http_client) -> None:
    r = await http_client.post("/api/audit/export?framework=spam")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_audit_reset(http_client) -> None:
    await http_client.post("/api/agent/scenario", json={"scenario": "low_risk"})
    before = (await http_client.get("/api/audit/entries")).json()["total"]
    assert before > 1

    r = await http_client.post("/api/audit/reset")
    assert r.status_code == 200

    after = (await http_client.get("/api/audit/entries")).json()["total"]
    # Reset wipes and seals a fresh AGENT_CREATED only
    assert after < before
    assert after >= 1
