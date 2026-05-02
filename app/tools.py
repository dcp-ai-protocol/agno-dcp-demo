"""Banking collections tools (mock implementations).

Realistic enough to read like a production system in screenshots:
customer profiles, payment plans, callback scheduling, and email
confirmations. Backing data is a deterministic in-memory fixture so
the demo is reproducible and screen-recordable.

Each function is a plain Python callable. The :class:`DCPAgent`
in ``app/agent.py`` runs them through ``run_tool`` so every call
flows through the DCP-AI policy gate and audit chain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

CUSTOMER_FIXTURES: dict[str, dict[str, Any]] = {
    "C-100422": {
        "customer_id": "C-100422",
        "name": "Mariana Soto",
        "tier": "tier-2",
        "outstanding_balance_usd": 1840.50,
        "days_past_due": 12,
        "preferred_channel": "email",
        "email": "mariana.soto@example.com",
        "phone": "+56 9 4422 8170",
        "history": [
            {
                "date": "2026-03-12",
                "event": "payment_received",
                "amount_usd": 250,
            },
            {
                "date": "2026-04-04",
                "event": "missed_payment",
                "amount_usd": 250,
            },
        ],
        "credit_score": 712,
    },
    "C-100423": {
        "customer_id": "C-100423",
        "name": "Joaquín Bermúdez",
        "tier": "tier-3",
        "outstanding_balance_usd": 7420.10,
        "days_past_due": 47,
        "preferred_channel": "phone",
        "email": "j.bermudez@example.com",
        "phone": "+56 2 2987 1140",
        "history": [
            {
                "date": "2026-02-28",
                "event": "settlement_proposal_declined",
            },
            {
                "date": "2026-04-15",
                "event": "missed_payment",
                "amount_usd": 600,
            },
        ],
        "credit_score": 588,
    },
    "C-100424": {
        "customer_id": "C-100424",
        "name": "Renata Falcão",
        "tier": "tier-1",
        "outstanding_balance_usd": 320.00,
        "days_past_due": 4,
        "preferred_channel": "email",
        "email": "renata.falcao@example.com",
        "phone": "+55 11 9 8841 5532",
        "history": [
            {
                "date": "2026-04-10",
                "event": "auto_pay_failed",
                "amount_usd": 320,
            },
        ],
        "credit_score": 791,
    },
}


def lookup_customer(customer_id: str) -> dict[str, Any]:
    """Fetch customer record from the (mock) CRM.

    In production this would hit a real CRM API; the contract is
    identical so swapping is trivial.
    """
    record = CUSTOMER_FIXTURES.get(customer_id)
    if record is None:
        return {
            "found": False,
            "customer_id": customer_id,
            "error": "Customer not on file.",
        }
    # Return a copy to make tools side-effect-free.
    return {"found": True, **record}


def propose_payment_plan(
    customer_id: str,
    total_amount_usd: float,
    installments: int = 3,
    discount_pct: float = 0.0,
) -> dict[str, Any]:
    """Generate a structured payment plan proposal.

    Validates inputs and returns a dictionary describing the plan,
    suitable for downstream signing or email composition. Does NOT
    send anything.
    """
    if installments < 1:
        return {"ok": False, "error": "installments must be >= 1"}
    if discount_pct < 0 or discount_pct > 100:
        return {"ok": False, "error": "discount_pct out of range (0..100)"}
    if total_amount_usd <= 0:
        return {"ok": False, "error": "total_amount_usd must be > 0"}

    customer = CUSTOMER_FIXTURES.get(customer_id)
    if customer is None:
        return {"ok": False, "error": "unknown customer"}

    discounted = round(total_amount_usd * (1 - discount_pct / 100), 2)
    per_installment = round(discounted / installments, 2)
    today = datetime.now(UTC).date()
    schedule = [
        {
            "n": i + 1,
            "due_date": (today + timedelta(days=30 * (i + 1))).isoformat(),
            "amount_usd": per_installment,
        }
        for i in range(installments)
    ]
    return {
        "ok": True,
        "customer_id": customer_id,
        "customer_name": customer["name"],
        "original_amount_usd": total_amount_usd,
        "discount_pct": discount_pct,
        "discounted_amount_usd": discounted,
        "installments": installments,
        "per_installment_usd": per_installment,
        "schedule": schedule,
        "proposed_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def schedule_callback(
    customer_id: str,
    when_iso: str,
    reason: str,
) -> dict[str, Any]:
    """Schedule a callback with the human collections team.

    Returns a confirmation envelope. Does not actually book anything;
    in production this would talk to a calendar API.
    """
    customer = CUSTOMER_FIXTURES.get(customer_id)
    if customer is None:
        return {"ok": False, "error": "unknown customer"}
    try:
        when_dt = datetime.fromisoformat(when_iso)
    except ValueError:
        return {"ok": False, "error": f"invalid ISO datetime: {when_iso}"}
    return {
        "ok": True,
        "callback_id": f"cb-{customer_id}-{int(when_dt.timestamp())}",
        "customer_id": customer_id,
        "customer_name": customer["name"],
        "when_iso": when_dt.isoformat(),
        "reason": reason,
        "channel": customer["preferred_channel"],
        "scheduled_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def send_confirmation(
    customer_id: str,
    plan_id: str,
    channel: str = "email",
) -> dict[str, Any]:
    """Send the agreed payment-plan confirmation to the customer.

    In production this would call a transactional email or SMS
    provider. Returns a dispatch record that the audit chain seals.
    """
    customer = CUSTOMER_FIXTURES.get(customer_id)
    if customer is None:
        return {"ok": False, "error": "unknown customer"}
    if channel not in ("email", "sms", "phone"):
        return {"ok": False, "error": f"unsupported channel: {channel}"}
    addr = customer["email"] if channel == "email" else customer["phone"]
    return {
        "ok": True,
        "delivery_id": f"dlv-{plan_id}",
        "customer_id": customer_id,
        "channel": channel,
        "to": addr,
        "subject": "Payment plan confirmation",
        "queued_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


# Tool registry exposed to the agent. Order matters for some UIs;
# sorted from "low risk read" to "outbound communication".
ALL_TOOLS = [
    lookup_customer,
    propose_payment_plan,
    schedule_callback,
    send_confirmation,
]
