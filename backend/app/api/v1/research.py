import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    acquire_lock, cache_result, check_idempotency, get_cached_result,
    get_inflight_job_id, release_lock, set_idempotency,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.models.research import ResearchJob, ResearchJobParticipant, ResearchResult
from app.schemas.research import (
    AnalystRatingsData, ChartData, ClassificationResult,
    CreditsBlock, EnrichmentPanel, ErrorDetail, FinalRecommendation,
    FundamentalsData, MetricCards, NewsSentimentData,
    OnChainData, ResearchRequest, ResultData,
)
from app.services import credits_service
from app.services.aggregator import aggregate
from app.services.classifier import classify_query, normalize_query
from app.services.job_utils import increment_retry_count, update_job_status
from app.services.rate_limiter import check_rate_limit
from app.services.summarizer import summarize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["research"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _success(data, request: Request) -> dict:
    return {"success": True, "data": data, "request_id": _request_id(request)}


def _error(code: str, message: str, request: Request, detail=None, status_code: int = 400):
    raise HTTPException(
        status_code=status_code,
        detail={
            "success": False,
            "error": {"code": code, "message": message, "detail": detail},
            "request_id": _request_id(request),
        },
    )


def _shape_response(raw_data: Optional[dict], category: str):
    if not raw_data:
        return None, None, None

    primary = raw_data.get("primary_data") or {}
    if not primary:
        return None, None, None

    def _try_build(model, key: str):
        try:
            val = primary.get(key)
            return model(**val) if val else None
        except Exception:
            return None

    enrichments = EnrichmentPanel(
        news=_try_build(NewsSentimentData, "news_sentiment"),
        onchain=_try_build(OnChainData, "onchain"),
        fundamentals=_try_build(FundamentalsData, "fundamentals"),
        analyst_ratings=_try_build(AnalystRatingsData, "analyst_ratings"),
    )

    charts = ChartData(
        ohlc_1d=primary.get("ohlc_1d", []),
        ohlc_7d=primary.get("ohlc_7d", []),
        ohlc_30d=primary.get("ohlc_30d", []),
        ohlc_1y=primary.get("ohlc_1y", []),
        ohlc_5y=primary.get("ohlc_5y", []),
    )

    analyst = enrichments.analyst_ratings

    if category in ("stock", "commodity"):
        metrics = MetricCards(
            name=primary.get("name"),
            ticker=primary.get("ticker"),
            current_price=primary.get("current_price"),
            price_change_24h=primary.get("price_change_24h"),
            market_cap=primary.get("market_cap"),
            volume=primary.get("volume"),
            week_52_high=primary.get("week_52_high"),
            week_52_low=primary.get("week_52_low"),
            pe_ratio=primary.get("pe_ratio"),
            analyst_consensus=analyst.consensus_rating if analyst else None,
            analyst_target_price=analyst.target_price_consensus if analyst else None,
            analyst_total=analyst.total_analysts if analyst else None,
        )
    elif category == "crypto":
        metrics = MetricCards(
            name=primary.get("name"),
            symbol=primary.get("symbol"),
            current_price=primary.get("current_price"),
            price_change_24h=primary.get("price_change_24h"),
            market_cap=primary.get("market_cap"),
            volume=primary.get("volume_24h"),
        )
    else:
        metrics = None

    return metrics, charts, enrichments


def _credits_block(reservation_status: Optional[dict], cost: int) -> Optional[dict]:
    if reservation_status is None:
        return None
    return CreditsBlock(
        used_this_call=cost,
        monthly_remaining=reservation_status["balance"],
        bonus_remaining=0,  # main-platform schema doesn't split monthly/bonus yet
        total_remaining=reservation_status["balance"],
    ).model_dump()


async def _add_participant(
    db: AsyncSession, job_id: uuid.UUID, user_id: str, reference_id: str, cost: int, role: str
) -> None:
    db.add(ResearchJobParticipant(
        job_id=job_id,
        user_id=uuid.UUID(user_id),
        reference_id=reference_id,
        cost=cost,
        role=role,
    ))


# ---------------------------------------------------------------------------
# Background pipeline
# Settles EVERY participant attached to the job — original requester and any
# users who joined an in-flight job for the same query — not just one
# reference_id. Each participant is only settled once (settled flag guards
# against the finally-block running twice on retry).
# ---------------------------------------------------------------------------

async def _settle_participants(job_id: str, outcome: str) -> None:
    """outcome is 'commit' or 'refund'."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ResearchJobParticipant).where(
                ResearchJobParticipant.job_id == uuid.UUID(job_id),
                ResearchJobParticipant.settled == False,  # noqa: E712
            )
        )
        participants = result.scalars().all()

        for p in participants:
            try:
                if outcome == "commit":
                    await credits_service.commit(str(p.user_id), p.cost, p.reference_id)
                else:
                    await credits_service.refund(str(p.user_id), p.cost, p.reference_id)
                p.settled = True
            except Exception as e:
                logger.error(
                    f"Failed to settle participant user={p.user_id} "
                    f"job={job_id} outcome={outcome}: {e}"
                )

        await db.commit()


async def run_research_pipeline(job_id: str, query: str, query_normalized: str) -> None:
    start_time = time.monotonic()
    await update_job_status(job_id, "processing")

    try:
        classification: ClassificationResult = await classify_query(query)
        market_data = await aggregate(query, classification)
        llm_output  = await summarize(market_data)
        processing_ms = int((time.monotonic() - start_time) * 1000)

        recommendations = [r.model_dump() for r in (llm_output.recommendations or [])]

        async with AsyncSessionLocal() as db:
            db.add(ResearchResult(
                job_id=uuid.UUID(job_id),
                category=classification.category,
                query_normalized=query_normalized,
                balance=llm_output.balance,
                trend_summary=llm_output.trend_summary,
                insights=llm_output.insights,
                opportunities=llm_output.opportunities or [],
                risks=llm_output.risks or [],
                recommendations=recommendations,
                tags=llm_output.tags,
                raw_data=market_data.model_dump(),
                classifier_confidence=classification.confidence,
                classifier_source=classification.source,
                data_confidence=market_data.data_confidence,
                fetched_at=market_data.fetched_at,
            ))
            await db.execute(
                update(ResearchJob)
                .where(ResearchJob.id == uuid.UUID(job_id))
                .values(
                    status="complete",
                    category=classification.category,
                    processing_ms=processing_ms,
                    completed_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc)
                    + timedelta(seconds=settings.job_result_expiry_seconds),
                )
            )
            await db.commit()

        await cache_result(
            query_normalized,
            {
                "category":        classification.category,
                "balance":         llm_output.balance,
                "trend_summary":   llm_output.trend_summary,
                "insights":        llm_output.insights,
                "opportunities":   llm_output.opportunities or [],
                "risks":           llm_output.risks or [],
                "recommendations": recommendations,
                "tags":            llm_output.tags,
                "data_confidence": market_data.data_confidence,
                "fetched_at":      market_data.fetched_at,
                "raw_data":        market_data.model_dump(),
            },
            classification.category,
        )

        if not settings.bypass_rate_limits:
            await _settle_participants(job_id, outcome="commit")

        logger.info(f"Pipeline complete: job={job_id} ms={processing_ms}")

    except Exception as e:
        logger.exception(f"Pipeline failed: job={job_id}")
        await update_job_status(job_id, "failed", error=str(e))

        if not settings.bypass_rate_limits:
            await _settle_participants(job_id, outcome="refund")

    finally:
        await release_lock(query_normalized)


# ---------------------------------------------------------------------------
# POST /api/v1/research
# ---------------------------------------------------------------------------

@router.post("/research", status_code=202)
async def create_research_job(
    body: ResearchRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    query            = body.query.strip()
    query_normalized = normalize_query(query)
    user_id          = getattr(request.state, "user_id", None)
    plan_tier        = getattr(request.state, "plan_tier", "free")
    bypass           = settings.bypass_rate_limits

    idem_key = request.headers.get("X-Idempotency-Key")
    if idem_key:
        cached_idem = await check_idempotency(idem_key)
        if cached_idem:
            logger.debug(f"Idempotency hit: key={idem_key}")
            return _success(cached_idem, request)

    if not bypass:
        if not credits_service.is_entitled(plan_tier):
            _error(
                "PLAN_ACCESS_DENIED",
                f"Your current plan ({plan_tier}) does not include Research AI. "
                "Upgrade to Founder Workspace or above.",
                request,
                status_code=403,
            )

        is_limited, retry_after = await check_rate_limit(user_id)
        if is_limited:
            response.headers["Retry-After"] = str(retry_after)
            _error(
                "RATE_LIMITED",
                f"Too many requests. Try again in {retry_after}s.",
                request,
                status_code=429,
            )

    cached = await get_cached_result(query_normalized)
    source = "cache" if cached else "fresh"
    cost = credits_service.cost_for(source)

    reservation_status = None
    reference_id = str(uuid.uuid4())
    if not bypass:
        reservation_status = await credits_service.reserve(user_id, cost, reference_id)

        if reservation_status["status"] == "insufficient":
            _error(
                "INSUFFICIENT_CREDITS",
                f"You need {cost} credits for this request. Purchase a top-up "
                "or wait for your monthly reset.",
                request,
                status_code=402,
            )
        if reservation_status["status"] == "error":
            _error(
                "CREDITS_SERVICE_UNAVAILABLE",
                "We couldn't verify your credit balance right now. No credits were charged. "
                "Please try again shortly.",
                request,
                status_code=503,
            )

    credits_block = _credits_block(reservation_status, cost)

    # ── Cache hit → settle immediately, return result ───────────────────────
    if cached:
        job = ResearchJob(
            query=query,
            query_normalized=query_normalized,
            status="complete",
            source="cache",
            user_id=uuid.UUID(user_id) if user_id else None,
            plan_tier=plan_tier,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.flush()
        db.add(ResearchResult(
            job_id=job.id,
            category=cached.get("category", "general"),
            query_normalized=query_normalized,
            balance=cached.get("balance", ""),
            trend_summary=cached.get("trend_summary", ""),
            insights=cached.get("insights", []),
            opportunities=cached.get("opportunities", []),
            risks=cached.get("risks", []),
            recommendations=cached.get("recommendations", []),
            tags=cached.get("tags", []),
            data_confidence=cached.get("data_confidence"),
            fetched_at=cached.get("fetched_at"),
            raw_data=cached.get("raw_data"),
        ))

        if not bypass and reservation_status and reservation_status["status"] == "ok":
            await _add_participant(db, job.id, user_id, reference_id, cost, role="original")

        await db.commit()

        if not bypass and reservation_status and reservation_status["status"] == "ok":
            await credits_service.commit(user_id, cost, reference_id)

        response_data = {"job_id": str(job.id), "credits": credits_block}
        if idem_key:
            await set_idempotency(idem_key, response_data)
        return _success(response_data, request)

    # ── In-flight dedup — now properly tracked as a participant ─────────────
    existing_job_id = await get_inflight_job_id(query_normalized)
    if existing_job_id:
        if not bypass and reservation_status and reservation_status["status"] == "ok":
            await _add_participant(
                db, uuid.UUID(existing_job_id), user_id, reference_id, cost, role="joined"
            )
            await db.commit()
            # NOT committed/refunded here — settled later when the shared
            # job's pipeline actually finishes, alongside every other participant.

        response_data = {"job_id": existing_job_id, "credits": credits_block}
        if idem_key:
            await set_idempotency(idem_key, response_data)
        return _success(response_data, request)

    # ── Fresh job ─────────────────────────────────────────────────────────
    job = ResearchJob(
        query=query,
        query_normalized=query_normalized,
        status="pending",
        source="fresh",
        user_id=uuid.UUID(user_id) if user_id else None,
        plan_tier=plan_tier,
    )
    db.add(job)
    await db.flush()

    if not bypass and reservation_status and reservation_status["status"] == "ok":
        await _add_participant(db, job.id, user_id, reference_id, cost, role="original")

    await db.commit()

    job_id = str(job.id)
    await acquire_lock(query_normalized, job_id)

    background_tasks.add_task(run_research_pipeline, job_id, query, query_normalized)

    response_data = {"job_id": job_id, "credits": credits_block}
    if idem_key:
        await set_idempotency(idem_key, response_data)

    return _success(response_data, request)


# ---------------------------------------------------------------------------
# GET /api/v1/research/{job_id}  (unchanged)
# ---------------------------------------------------------------------------

@router.get("/research/{job_id}")
async def get_research_job(
    job_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        _error("INVALID_JOB_ID", "Job ID is not a valid UUID", request, status_code=400)

    job = await db.get(ResearchJob, job_uuid)
    if not job:
        _error("JOB_NOT_FOUND", "Job not found", request, status_code=404)

    result_data = None
    metrics     = None
    chart_data  = None
    enrichments = None

    if job.result:
        result_data = ResultData(
            balance=job.result.balance,
            trend_summary=job.result.trend_summary,
            insights=job.result.insights,
            opportunities=job.result.opportunities or [],
            risks=job.result.risks or [],
            recommendations=[
                FinalRecommendation(**r) if isinstance(r, dict) else r
                for r in (job.result.recommendations or [])
            ],
            tags=job.result.tags,
        )
        metrics, chart_data, enrichments = _shape_response(job.result.raw_data, job.category)

    res = job.result
    return _success(
        {
            "status":                job.status,
            "category":              job.category,
            "source":                job.source,
            "result":                result_data.model_dump() if result_data else None,
            "metrics":               metrics.model_dump() if metrics else None,
            "chart_data":            chart_data.model_dump() if chart_data else None,
            "enrichments":           enrichments.model_dump() if enrichments else None,
            "processing_ms":         job.processing_ms,
            "created_at":            job.created_at.isoformat(),
            "data_confidence":       float(res.data_confidence) if res and res.data_confidence is not None else None,
            "classifier_confidence": float(res.classifier_confidence) if res and res.classifier_confidence is not None else None,
            "fetched_at":            res.fetched_at if res else None,
        },
        request,
    )
