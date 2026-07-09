"""
Entitlement + credit orchestration for market_research, mirroring the pattern
used in proposal-builder so all AI services share one ledger and one failure
policy against the main GMBTE Postgres DB.

Fails CLOSED on credit-DB errors — a DB error blocks the request rather than
granting a free run. This matters more here than in a synchronous service:
market research jobs are async, so a fail-open bug wouldn't surface until a
much later credits/ledger reconciliation, making it harder to catch.
"""

import logging

from app.core import credits_db
from app.core.config import (
    CREDIT_COST_CACHE, CREDIT_COST_FRESH, ENTITLED_PLANS, SERVICE_NAME,
)

logger = logging.getLogger(__name__)


def is_entitled(plan_tier: str) -> bool:
    """Gate 1 — does this plan tier include Research AI at all? No DB call."""
    return plan_tier in ENTITLED_PLANS


def cost_for(source: str) -> int:
    """source is 'cache' or 'fresh'. Cache hits cost less — no external API spend."""
    return CREDIT_COST_CACHE if source == "cache" else CREDIT_COST_FRESH


async def reserve(user_id: str, amount: int, reference_id: str) -> dict:
    """
    Reserve credits before doing any work.
    Returns:
        {"status": "ok", "balance": int}
        {"status": "insufficient", "balance": None}
        {"status": "error"}   — DB failure; caller should fail closed (block request)
    """
    try:
        new_balance = await credits_db.reserve_credits(
            user_id=user_id, amount=amount, service=SERVICE_NAME, reference_id=reference_id,
        )
        if new_balance is None:
            return {"status": "insufficient", "balance": None}
        return {"status": "ok", "balance": new_balance}
    except Exception as e:
        logger.error(f"Credit reservation failed (fail-closed) user={user_id} ref={reference_id}: {e}")
        return {"status": "error", "balance": None}


async def commit(user_id: str, amount: int, reference_id: str) -> None:
    """Mark a reservation as successfully consumed once the job actually completes."""
    try:
        await credits_db.commit_reservation(
            user_id=user_id, amount=amount, service=SERVICE_NAME, reference_id=reference_id,
        )
    except Exception as e:
        # Don't fail the already-successful job over a ledger write — log loudly for reconciliation.
        logger.error(f"Credit commit failed to record (job succeeded regardless) user={user_id} ref={reference_id}: {e}")


async def refund(user_id: str, amount: int, reference_id: str) -> None:
    """Refund a reservation when the pipeline fails after credits were already taken."""
    try:
        new_balance = await credits_db.refund_reservation(
            user_id=user_id, amount=amount, service=SERVICE_NAME, reference_id=reference_id,
        )
        if new_balance is None:
            logger.error(f"Refund failed — user_credits row not found for user={user_id}")
        else:
            logger.info(f"Refunded {amount} credits to user={user_id} ref={reference_id} new_balance={new_balance}")
    except Exception as e:
        logger.error(f"Credit refund failed user={user_id} ref={reference_id}: {e}")


async def get_balance(user_id: str) -> dict:
    try:
        result = await credits_db.get_balance(user_id)
        if result is None:
            return {"credits_balance": 0, "credits_reset_at": None}
        return result
    except Exception as e:
        logger.warning(f"Balance read failed user={user_id}: {e}")
        return {"credits_balance": 0, "credits_reset_at": None}
