import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import set_job_status
from app.core.database import AsyncSessionLocal
from app.models.research import ResearchJob

logger = logging.getLogger(__name__)


async def update_job_status(
    job_id: str | uuid.UUID,
    status: str,
    error: Optional[str] = None,
    db: Optional[AsyncSession] = None,
    *,
    category: Optional[str] = None,
    processing_ms: Optional[int] = None,
) -> None:
    job_id_str = str(job_id)
    now = datetime.now(timezone.utc)

    values: dict = {"status": status, "updated_at": now}
    if status == "complete":
        values["completed_at"] = now
    if error is not None:
        values["error_message"] = error
    if category is not None:
        values["category"] = category
    if processing_ms is not None:
        values["processing_ms"] = processing_ms

    async def _write(session: AsyncSession) -> None:
        await session.execute(
            update(ResearchJob)
            .where(ResearchJob.id == uuid.UUID(job_id_str))
            .values(**values)
        )
        await session.commit()

    if db is not None:
        await _write(db)
    else:
        async with AsyncSessionLocal() as session:
            await _write(session)

    await set_job_status(job_id_str, status)
    logger.info(
        f"Job {job_id_str} → status={status}"
        + (f" error={error}" if error else "")
    )


async def increment_retry_count(job_id: str | uuid.UUID) -> None:
    """Increment retry_count using the ORM — avoids raw f-string SQL."""
    job_id_uuid = uuid.UUID(str(job_id))
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(ResearchJob)
            .where(ResearchJob.id == job_id_uuid)
            .values(
                retry_count=ResearchJob.retry_count + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
