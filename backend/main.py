import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, update

from app.core.cache import close_redis, get_redis
from app.core.config import settings
from app.core.database import AsyncSessionLocal, create_schema, dispose_engine
from app.core.middleware import AuthMiddleware, RequestIDMiddleware
from app.models.research import ResearchJob

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
async def _timeout_sweep() -> None:
    from app.services.job_utils import update_job_status, increment_retry_count
    from app.api.v1.research import run_research_pipeline

    while True:
        try:
            await asyncio.sleep(60)
            timeout_cutoff = datetime.now(timezone.utc) - timedelta(
                seconds=settings.job_processing_timeout_seconds
            )

            stuck = []
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ResearchJob).where(
                        ResearchJob.status == "processing",
                        ResearchJob.updated_at < timeout_cutoff,
                    )
                )
                for job in result.scalars().all():
                    stuck.append({
                        "id":               str(job.id),
                        "query":            job.query,
                        "query_normalized": job.query_normalized,
                        "retry_count":      job.retry_count,
                        "updated_at":       job.updated_at,
                    })

            for job in stuck:
                job_id = job["id"]
                logger.warning(
                    f"Timeout sweep: job {job_id} stuck since {job['updated_at']}"
                )

                if job["retry_count"] < settings.job_max_retries:
                    await increment_retry_count(job_id)
                    await update_job_status(
                        job_id, "pending",
                        error=f"Timed out after {settings.job_processing_timeout_seconds}s",
                    )
                    asyncio.create_task(
                        run_research_pipeline(
                            job_id, job["query"], job["query_normalized"]
                        )
                    )
                    logger.info(
                        f"Re-queued job {job_id} "
                        f"(retry {job['retry_count'] + 1}/{settings.job_max_retries})"
                    )
                else:
                    await update_job_status(
                        job_id, "failed",
                        error=f"Timed out and exhausted {settings.job_max_retries} retries",
                    )
                    logger.error(f"Job {job_id} permanently failed via timeout sweep")

        except asyncio.CancelledError:
            logger.info("Timeout sweep cancelled")
            break
        except Exception as e:
            logger.error(f"Timeout sweep error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Market Research AI service...")
    await create_schema()

    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("Redis connection OK")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    sweep_task = asyncio.create_task(_timeout_sweep())
    logger.info("Timeout sweep task started")

    yield

    sweep_task.cancel()
    try:
        await sweep_task
    except asyncio.CancelledError:
        pass
    await dispose_engine()
    await close_redis()
    logger.info("Market Research AI service shut down")

app = FastAPI(
    title="Market Research AI",
    description="AI-powered market research microservice",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

_origins = ["*"] if settings.app_env == "development" else settings.allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=settings.app_env != "development",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestIDMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    from fastapi import HTTPException
    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)

    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "detail": str(exc) if settings.app_env == "development" else None,
            },
            "request_id": request_id,
        },
    )

from app.api.v1.research import router as research_router
app.include_router(research_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "market-research-ai"}
