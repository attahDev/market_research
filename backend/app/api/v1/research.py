import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    acquire_lock, cache_result, get_cached_result,
    get_inflight_job_id, release_lock,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.models.research import ResearchJob, ResearchResult
from app.schemas.research import (
    AnalystRatingsData, ChartData, ClassificationResult,
    EnrichmentPanel, ErrorDetail, FinalRecommendation,
    FundamentalsData, MetricCards, NewsSentimentData,
    OnChainData, ResearchRequest, ResultData,
)
from app.services.aggregator import aggregate
from app.services.classifier import classify_query, normalize_query
from app.services.job_utils import increment_retry_count, update_job_status
from app.services.summarizer import summarize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["research"])



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

        logger.info(f"Pipeline complete: job={job_id} ms={processing_ms}")

    except Exception as e:
        logger.exception(f"Pipeline failed: job={job_id}")
        await update_job_status(job_id, "failed", error=str(e))
    finally:
        await release_lock(query_normalized)

@router.post("/research", status_code=202)
async def create_research_job(
    body: ResearchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    query            = body.query.strip()
    query_normalized = normalize_query(query)

    # 1. Cache hit → write a cache-sourced job row and return immediately
    cached = await get_cached_result(query_normalized)
    if cached:
        job = ResearchJob(
            query=query,
            query_normalized=query_normalized,
            status="complete",
            source="cache",
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
        await db.commit()
        return _success({"job_id": str(job.id)}, request)

    existing_job_id = await get_inflight_job_id(query_normalized)
    if existing_job_id:
        return _success({"job_id": existing_job_id}, request)

    job = ResearchJob(query=query, query_normalized=query_normalized, status="pending", source="fresh")
    db.add(job)
    await db.flush()
    await db.commit()

    job_id = str(job.id)
    await acquire_lock(query_normalized, job_id)
    background_tasks.add_task(run_research_pipeline, job_id, query, query_normalized)

    return _success({"job_id": job_id}, request)


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
