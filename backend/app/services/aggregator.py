import asyncio
import logging
from datetime import datetime, timezone

from app.schemas.research import ClassificationResult, MarketData
from app.services.fetchers.crypto import fetch_crypto
from app.services.fetchers.stocks import fetch_stock
from app.services.fetchers.web import fetch_web
from app.services.fetchers.news import fetch_news_sentiment
from app.services.fetchers.onchain import fetch_onchain_data
from app.services.symbol_mapper import resolve_symbol, resolve_multi

logger = logging.getLogger(__name__)

_COMMODITY_NEWS_QUERIES: dict[str, str] = {
    "GLD":  "gold price market",
    "SLV":  "silver price market",
    "USO":  "crude oil price market",
    "BNO":  "brent oil price",
    "UNG":  "natural gas price",
    "CPER": "copper price market",
    "PPLT": "platinum price market",
    "PALL": "palladium price market",
    "WEAT": "wheat price market",
    "CORN": "corn price market",
    "SOYB": "soybean price market",
    "GC=F": "gold price market",
    "SI=F": "silver price market",
    "CL=F": "crude oil price market",
    "BZ=F": "brent oil price",
    "NG=F": "natural gas price",
    "HG=F": "copper price market",
    "PL=F": "platinum price market",
    "PA=F": "palladium price market",
    "ZW=F": "wheat price market",
    "ZC=F": "corn price market",
    "ZS=F": "soybean price market",
}

async def _safe(coro, label: str):
    try:
        return await coro
    except Exception as e:
        logger.warning(f"Provider '{label}' failed (non-fatal): {e}")
        return None


def _is_valid_payload(data) -> bool:
    if data is None:
        return False
    if isinstance(data, dict):
        if "error" in data and "current_price" not in data and "results" not in data:
            return False
    return True


def _compute_confidence(category: str, primary_data, partial: bool) -> float:
    if partial or primary_data is None:
        return 0.3

    score = 0.0
    try:
        d = primary_data if isinstance(primary_data, dict) else vars(primary_data)

        def _sub(key: str) -> dict:
            v = d.get(key) or {}
            return v if isinstance(v, dict) else vars(v)

        if category == "crypto":
            if d.get("current_price"):             score += 0.40
            if d.get("market_cap"):                score += 0.20
            if d.get("volume_24h"):                score += 0.15
            oc = _sub("onchain")
            if oc.get("chain_tvl_usd"):            score += 0.15
            if oc.get("active_addresses_24h"):     score += 0.10

        elif category in ("stock", "commodity"):
            if d.get("current_price"):             score += 0.40
            if d.get("pe_ratio"):                  score += 0.15
            if d.get("volume"):                    score += 0.10
            fd = _sub("fundamentals")
            if fd.get("net_margin_pct") or fd.get("pe_ratio"): score += 0.20
            ns = _sub("news_sentiment")
            if ns.get("article_count", 0) >= 1:   score += 0.15

        elif category in ("industry", "general"):
            results = d.get("results", [])
            if len(results) >= 3:                  score += 0.60
            elif results:                          score += 0.35
            ns = _sub("news_sentiment")
            count = ns.get("article_count", 0)
            if count >= 3:                         score += 0.40
            elif count >= 1:                       score += 0.20

    except Exception:
        return 0.5

    return round(min(score, 1.0), 3)

async def _aggregate_crypto(query: str) -> tuple[dict | None, bool]:
    logger.info(f"Crypto pipeline: query='{query}'")
    crypto_data = await _safe(fetch_crypto(query), "crypto")

    if not crypto_data:
        logger.warning(f"Crypto fetch failed for '{query}'")
        return {"error": "Crypto provider fetch failed", "query": query}, True

    coin_id     = getattr(crypto_data, "coin_id", None) or query
    ticker_hint = getattr(crypto_data, "name", None)    or query

    news_data, onchain_data = await asyncio.gather(
        _safe(fetch_news_sentiment(ticker_hint), "news"),
        _safe(fetch_onchain_data(coin_id),       "onchain"),
    )

    crypto_data.news_sentiment = news_data
    crypto_data.onchain        = onchain_data
    logger.info(f"Crypto OK: {crypto_data.name} ({crypto_data.symbol})")
    return crypto_data.model_dump(), False


async def _aggregate_stock(query: str, category: str) -> tuple[dict | None, bool]:
    logger.info(f"Stock/commodity pipeline: query='{query}' category='{category}'")
    entities        = resolve_multi(query, category)
    resolved_symbol = entities[0] if entities else resolve_symbol(query, category)
    logger.info(f"Resolved '{query}' → '{resolved_symbol}' (used for news only)")

    news_query = (
        _COMMODITY_NEWS_QUERIES.get(resolved_symbol, f"{query} price commodity")
        if category == "commodity"
        else query
    )

    stock_data, news_data = await asyncio.gather(
        _safe(fetch_stock(query, category=category), "stock"),
        _safe(fetch_news_sentiment(news_query),      "news"),
    )

    if not stock_data:
        logger.warning(f"Stock fetch failed for '{query}' (resolved: '{resolved_symbol}')")
        return {
            "error":           "Stock provider fetch failed",
            "query":           query,
            "resolved_symbol": resolved_symbol,
            "news_sentiment":  news_data.model_dump() if news_data else None,
        }, True

    stock_data.news_sentiment = news_data
    logger.info(f"Stock OK: {stock_data.name} ({stock_data.ticker})")
    return stock_data.model_dump(), False


async def _aggregate_web(query: str) -> tuple[dict | None, bool]:
    logger.info(f"Web pipeline: query='{query}'")

    web_data, news_data = await asyncio.gather(
        _safe(fetch_web(query),            "web"),
        _safe(fetch_news_sentiment(query), "news"),
    )

    if not web_data:
        logger.warning(f"Web fetch failed for '{query}'")
        return {
            "error":          "Web provider fetch failed",
            "query":          query,
            "news_sentiment": news_data.model_dump() if news_data else None,
        }, True

    web_data.news_sentiment = news_data
    logger.info(f"Web OK: {len(web_data.results)} results")
    return web_data.model_dump(), False

async def aggregate(query: str, classification: ClassificationResult) -> MarketData:
    category = classification.category
    topic    = query.strip()

    dispatch = {
        "crypto":    lambda: _aggregate_crypto(query),
        "stock":     lambda: _aggregate_stock(query, "stock"),
        "commodity": lambda: _aggregate_stock(query, "commodity"),
        "industry":  lambda: _aggregate_web(query),
        "general":   lambda: _aggregate_web(query),
    }

    handler = dispatch.get(category)
    if not handler:
        raise ValueError(f"Unknown category: {category}")

    primary_data, partial = await handler()

    if not _is_valid_payload(primary_data):
        raise RuntimeError(
            f"FETCH_FAILED: No usable data for category='{category}', query='{query}'"
        )

    data_source_map = {
        "crypto":    "coingecko",
        "stock":     "tiingo",
        "commodity": "tiingo",
        "industry":  "tavily",
        "general":   "tavily",
    }

    logger.info(f"Aggregation complete | category={category} partial={partial}")

    return MarketData(
        category=category,
        topic=topic,
        primary_data=primary_data,
        data_source=data_source_map[category],
        fetched_at=datetime.now(timezone.utc).isoformat(),
        partial=partial,
        data_confidence=_compute_confidence(category, primary_data, partial),
    )