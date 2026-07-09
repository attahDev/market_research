"""
Separate async engine to the MAIN GMBTE Postgres DB (not this service's own DB).

Credits are shared across all ~8 AI services and live in the main platform's
database, not per-microservice. This module talks to that database directly
via raw SQL — it does not own these tables, so no ORM models are defined here.

SCHEMA CAVEAT: built against an assumed shape, not yet confirmed against the
real main-platform schema:

    user_credits(
        user_id           uuid primary key,
        credits_balance   integer,
        credits_reset_at  timestamptz
    )

    credit_transactions(
        id            uuid primary key,
        user_id       uuid,
        service       text,       -- e.g. 'market_research', 'proposal_builder'
        amount        integer,
        status        text,       -- 'reserved' | 'committed' | 'refunded'
        reference_id  uuid,       -- ties reserve/commit/refund rows together
        created_at    timestamptz
    )

Once the real schema is confirmed, only the SQL strings below need updating —
callers in credits_service.py are unaffected.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

logger = logging.getLogger(__name__)

_credits_engine: Optional[AsyncEngine] = None
_CreditsSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def get_credits_engine() -> AsyncEngine:
    global _credits_engine, _CreditsSessionLocal
    if _credits_engine is None:
        if not settings.credits_database_url:
            raise RuntimeError(
                "CREDITS_DATABASE_URL is not set — cannot reach the main GMBTE DB"
            )
        _credits_engine = create_async_engine(
            settings.credits_database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
        _CreditsSessionLocal = async_sessionmaker(
            _credits_engine, expire_on_commit=False, class_=AsyncSession
        )
    return _credits_engine


def _session_factory() -> async_sessionmaker[AsyncSession]:
    get_credits_engine()  # ensures _CreditsSessionLocal is initialized
    assert _CreditsSessionLocal is not None
    return _CreditsSessionLocal


async def dispose_credits_engine() -> None:
    global _credits_engine, _CreditsSessionLocal
    if _credits_engine:
        await _credits_engine.dispose()
        _credits_engine = None
        _CreditsSessionLocal = None


# ---------------------------------------------------------------------------
# Raw SQL operations — atomic at the DB level via WHERE ... RETURNING
# ---------------------------------------------------------------------------

_RESERVE_SQL = text("""
    UPDATE user_credits
    SET credits_balance = credits_balance - :amount
    WHERE user_id = :user_id AND credits_balance >= :amount
    RETURNING credits_balance
""")

_REFUND_SQL = text("""
    UPDATE user_credits
    SET credits_balance = credits_balance + :amount
    WHERE user_id = :user_id
    RETURNING credits_balance
""")

_BALANCE_SQL = text("""
    SELECT credits_balance, credits_reset_at
    FROM user_credits
    WHERE user_id = :user_id
""")

_LEDGER_INSERT_SQL = text("""
    INSERT INTO credit_transactions
        (id, user_id, service, amount, status, reference_id, created_at)
    VALUES
        (:id, :user_id, :service, :amount, :status, :reference_id, now())
""")


async def reserve_credits(user_id: str, amount: int, service: str, reference_id: str) -> Optional[int]:
    """
    Atomically deduct `amount` if the balance covers it.
    Returns the new balance on success, or None if insufficient / user not found.
    Writes a 'reserved' ledger row on success.
    Raises on DB connection failure — caller decides fail-open/fail-closed.
    """
    Session = _session_factory()
    async with Session() as session:
        result = await session.execute(_RESERVE_SQL, {"user_id": user_id, "amount": amount})
        row = result.first()
        if row is None:
            await session.rollback()
            return None

        new_balance = row[0]
        await session.execute(_LEDGER_INSERT_SQL, {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "service": service,
            "amount": amount,
            "status": "reserved",
            "reference_id": reference_id,
        })
        await session.commit()
        return new_balance


async def commit_reservation(user_id: str, amount: int, service: str, reference_id: str) -> None:
    """
    Marks a prior reservation as successfully consumed.
    No balance change here — the deduction already happened at reserve time.
    This is purely a ledger entry marking the outcome.
    """
    Session = _session_factory()
    async with Session() as session:
        await session.execute(_LEDGER_INSERT_SQL, {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "service": service,
            "amount": amount,
            "status": "committed",
            "reference_id": reference_id,
        })
        await session.commit()


async def refund_reservation(user_id: str, amount: int, service: str, reference_id: str) -> Optional[int]:
    """
    Refunds `amount` back onto the user's balance and logs it.
    Returns the new balance, or None if the user row doesn't exist.
    """
    Session = _session_factory()
    async with Session() as session:
        result = await session.execute(_REFUND_SQL, {"user_id": user_id, "amount": amount})
        row = result.first()
        if row is None:
            await session.rollback()
            return None

        new_balance = row[0]
        await session.execute(_LEDGER_INSERT_SQL, {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "service": service,
            "amount": amount,
            "status": "refunded",
            "reference_id": reference_id,
        })
        await session.commit()
        return new_balance


async def get_balance(user_id: str) -> Optional[dict]:
    Session = _session_factory()
    async with Session() as session:
        result = await session.execute(_BALANCE_SQL, {"user_id": user_id})
        row = result.first()
        if row is None:
            return None
        return {"credits_balance": row[0], "credits_reset_at": row[1]}
