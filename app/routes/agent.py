"""HTTP routes that drive the Collections Agent.

Two surfaces:

* ``POST /api/agent/run``: structured JSON entrypoint that runs a
  named tool through the full DCP-AI pipeline and returns the
  decision + result.
* ``POST /api/agent/scenario``: pre-baked scenarios (Mariana,
  Joaquín, Renata) that exercise the policy gate from the UI with
  one click. Useful for live demos.
"""

from __future__ import annotations

import logging
from typing import Any

from agno_dcp.exceptions import PolicyDenied
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent import DemoAgentService, get_service, serializable
from app.tools import ALL_TOOLS, CUSTOMER_FIXTURES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

_TOOL_BY_NAME = {fn.__name__: fn for fn in ALL_TOOLS}


class ToolRunRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool to invoke.")
    args: dict[str, Any] = Field(default_factory=dict)


class ToolRunResponse(BaseModel):
    approved: bool
    reason: str
    rule_name: str | None
    result: Any | None
    error: str | None


@router.post("/run", response_model=ToolRunResponse)
async def run_tool(req: ToolRunRequest) -> ToolRunResponse:
    """Run a named tool through DCP-AI gating + execution + audit.

    On a deny verdict the response carries ``approved=False`` and the
    deny reason; the tool is NOT executed (strict mode is on).
    """
    service: DemoAgentService = get_service()
    fn = _TOOL_BY_NAME.get(req.tool_name)
    if fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tool: {req.tool_name}. Available: {list(_TOOL_BY_NAME)}",
        )

    try:
        result = await service.agent.run_tool(fn, req.args, tool_name=req.tool_name)
        return ToolRunResponse(
            approved=True,
            reason="approved",
            rule_name=None,
            result=serializable(result),
            error=None,
        )
    except PolicyDenied as exc:
        decision = getattr(exc, "decision", None)
        return ToolRunResponse(
            approved=False,
            reason=str(exc),
            rule_name=getattr(decision, "rule_name", None) if decision else None,
            result=None,
            error=None,
        )
    except Exception as exc:
        logger.exception("Tool %s raised", req.tool_name)
        return ToolRunResponse(
            approved=True,  # tool was approved; the failure is downstream
            reason="approved",
            rule_name=None,
            result=None,
            error=f"{type(exc).__name__}: {exc}",
        )


class ScenarioRequest(BaseModel):
    scenario: str = Field(..., description="One of: low_risk, high_risk, restricted_channel")


@router.post("/scenario")
async def run_scenario(req: ScenarioRequest) -> dict[str, Any]:
    """Run a complete pre-baked scenario.

    Each scenario is a small sequence of tool calls that demonstrates
    a specific policy interaction. Returns the list of outcomes so
    the UI can render a transcript.
    """
    service: DemoAgentService = get_service()
    if req.scenario == "low_risk":
        steps = [
            ("lookup_customer", {"customer_id": "C-100422"}),
            (
                "propose_payment_plan",
                {
                    "customer_id": "C-100422",
                    "total_amount_usd": 1840.50,
                    "installments": 4,
                    "discount_pct": 5,
                },
            ),
            (
                "send_confirmation",
                {"customer_id": "C-100422", "plan_id": "plan-0001", "channel": "email"},
            ),
        ]
    elif req.scenario == "high_risk":
        steps = [
            ("lookup_customer", {"customer_id": "C-100423"}),
            (
                "propose_payment_plan",
                {
                    "customer_id": "C-100423",
                    "total_amount_usd": 7420.10,
                    "installments": 6,
                    "discount_pct": 25,
                },
            ),
        ]
    elif req.scenario == "restricted_channel":
        steps = [
            ("lookup_customer", {"customer_id": "C-100424"}),
            (
                "propose_payment_plan",
                {
                    "customer_id": "C-100424",
                    "total_amount_usd": 320,
                    "installments": 2,
                    "discount_pct": 0,
                },
            ),
            (
                "send_confirmation",
                {"customer_id": "C-100424", "plan_id": "plan-0002", "channel": "phone"},
            ),
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")

    transcript: list[dict[str, Any]] = []
    for tool_name, args in steps:
        fn = _TOOL_BY_NAME[tool_name]
        try:
            result = await service.agent.run_tool(fn, args, tool_name=tool_name)
            transcript.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "approved": True,
                    "result": serializable(result),
                }
            )
        except PolicyDenied as exc:
            transcript.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "approved": False,
                    "reason": str(exc),
                    "rule_name": getattr(exc.decision, "rule_name", None) if exc.decision else None,
                }
            )
            # Stop the scenario after the first deny to mirror real flow.
            break
    return {
        "scenario": req.scenario,
        "transcript": transcript,
        "total_steps": len(steps),
        "executed_steps": len(transcript),
    }


@router.get("/info")
async def agent_info() -> dict[str, Any]:
    """Identity + capability snapshot for the dashboard header."""
    service = get_service()
    bundle = service.agent.dcp_bundle
    return {
        "agent_id": bundle.agent_id,
        "agent_name": bundle.agent_name,
        "human_principal": bundle.human_principal,
        "security_tier": bundle.security_tier,
        "public_key_b64": bundle.public_key_b64,
        "created_at": bundle.created_at,
        "tools": [fn.__name__ for fn in ALL_TOOLS],
        "customers": [
            {"customer_id": c["customer_id"], "name": c["name"], "tier": c["tier"]}
            for c in CUSTOMER_FIXTURES.values()
        ],
        "policy_engine_id": service.engine.engine_id,
    }
