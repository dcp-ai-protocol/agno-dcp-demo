"""Tests for the DemoAgentService lifecycle and its DCP-AI surface."""

from __future__ import annotations

import pytest
from agno_dcp.exceptions import PolicyDenied

from app.agent import DemoAgentService
from app.tools import (
    lookup_customer,
    propose_payment_plan,
    send_confirmation,
)


@pytest.mark.asyncio
async def test_service_boots_with_identity(service: DemoAgentService) -> None:
    bundle = service.agent.dcp_bundle
    assert bundle.agent_id.startswith("agent:")
    assert bundle.security_tier == "tier-3"
    assert bundle.human_principal == "test@example.com"
    assert service.engine is not None
    assert len(service.engine.ruleset.rules) >= 5


@pytest.mark.asyncio
async def test_lookup_customer_is_allowed(service: DemoAgentService) -> None:
    result = await service.agent.run_tool(
        lookup_customer,
        {"customer_id": "C-100422"},
        tool_name="lookup_customer",
    )
    assert result["found"] is True
    assert result["name"] == "Mariana Soto"


@pytest.mark.asyncio
async def test_low_risk_payment_plan_allowed(service: DemoAgentService) -> None:
    result = await service.agent.run_tool(
        propose_payment_plan,
        {
            "customer_id": "C-100422",
            "total_amount_usd": 1840.50,
            "installments": 4,
            "discount_pct": 5,
        },
        tool_name="propose_payment_plan",
    )
    assert result["ok"] is True
    assert result["installments"] == 4
    assert len(result["schedule"]) == 4


@pytest.mark.asyncio
async def test_aggressive_discount_is_denied(service: DemoAgentService) -> None:
    with pytest.raises(PolicyDenied) as exc:
        await service.agent.run_tool(
            propose_payment_plan,
            {
                "customer_id": "C-100422",
                "total_amount_usd": 1840.50,
                "installments": 4,
                "discount_pct": 30,
            },
            tool_name="propose_payment_plan",
        )
    assert exc.value.decision is not None
    assert "20%" in exc.value.decision.reason


@pytest.mark.asyncio
async def test_phone_channel_send_is_denied(service: DemoAgentService) -> None:
    with pytest.raises(PolicyDenied):
        await service.agent.run_tool(
            send_confirmation,
            {
                "customer_id": "C-100424",
                "plan_id": "plan-x",
                "channel": "phone",
            },
            tool_name="send_confirmation",
        )


@pytest.mark.asyncio
async def test_audit_chain_grows_per_call(service: DemoAgentService) -> None:
    initial = await service.storage.get_audit_entries()
    initial_count = len(initial)

    await service.agent.run_tool(
        lookup_customer,
        {"customer_id": "C-100422"},
        tool_name="lookup_customer",
    )

    after = await service.storage.get_audit_entries()
    # +3 entries: INTENT_DECLARED, POLICY_DECISION, TOOL_EXECUTED
    assert len(after) - initial_count == 3
    types_added = [e["event_type"] for e in after[initial_count:]]
    assert types_added == ["INTENT_DECLARED", "POLICY_DECISION", "TOOL_EXECUTED"]


@pytest.mark.asyncio
async def test_chain_integrity_after_workload(service: DemoAgentService) -> None:
    from agno_dcp.audit.verifier import AuditChainVerifier

    # Apply a varied workload
    await service.agent.run_tool(
        lookup_customer, {"customer_id": "C-100422"}, tool_name="lookup_customer"
    )
    await service.agent.run_tool(
        propose_payment_plan,
        {
            "customer_id": "C-100422",
            "total_amount_usd": 1500,
            "installments": 3,
            "discount_pct": 10,
        },
        tool_name="propose_payment_plan",
    )
    # And a deny path
    try:
        await service.agent.run_tool(
            propose_payment_plan,
            {
                "customer_id": "C-100422",
                "total_amount_usd": 1500,
                "installments": 3,
                "discount_pct": 30,
            },
            tool_name="propose_payment_plan",
        )
    except PolicyDenied:
        pass

    result = await AuditChainVerifier(service.storage).verify()
    assert result.chain_intact is True
    assert result.entries_corrupted == []


@pytest.mark.asyncio
async def test_compliance_bundle_export(service: DemoAgentService, tmp_path) -> None:
    import zipfile

    from agno_dcp.audit.exporter import ComplianceBundleExporter

    await service.agent.run_tool(
        lookup_customer, {"customer_id": "C-100422"}, tool_name="lookup_customer"
    )

    exporter = ComplianceBundleExporter(service.chain, service.storage)
    path = await exporter.export(framework="eu_ai_act", output_dir=tmp_path / "bundles")

    assert path.exists()
    assert path.suffix == ".zip"
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "audit_log.jsonl" in names
        assert "compliance_mapping.json" in names
