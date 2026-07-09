import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.research import NewsSentimentData, NewsHeadline

logger = logging.getLogger(__name__)
POSITIVE_WORDS = {
    "surge", "surges", "rally", "rallies", "jump", "jumps", "jumped", "gain",
    "gains", "gained", "rise", "rises", "rose", "bullish", "bull", "record",
    "high", "strong", "growth", "grows", "grew", "profit", "profits",
    "beat", "beats", "exceed", "exceeds", "exceeded", "upgrade", "upgrades",
    "buy", "outperform", "positive", "soar", "soars", "soared", "boom",
    "breakthrough", "recovery", "recovers", "recovered", "upside", "optimistic",
}

NEGATIVE_WORDS = {
    "crash", "crashes", "drop", "drops", "dropped", "fall", "falls", "fell",
    "decline", "declines", "declined", "bearish", "bear", "low", "weak",
    "loss", "losses", "miss", "misses", "missed", "downgrade", "downgrades",
    "sell", "underperform", "negative", "plunge", "plunges", "plunged",
    "slump", "slumps", "slumped", "warning", "risk", "concern", "fears",
    "lawsuit", "fine", "penalty", "recession", "inflation", "default",
    "bankrupt", "fraud", "investigation", "probe", "recall",
}

NEWSAPI_BASE = "https://newsapi.org/v2/everything"
FMP_NEWS_URL = "https://financialmodelingprep.com/api/v3/stock_news"
MAX_ARTICLES  = 3
LOOKBACK_DAYS = 7


def _score_sentiment(headlines: list["NewsHeadline"]) -> str:
    """Keyword-based sentiment score over headline titles."""
    pos = neg = 0
    for h in headlines:
        words = set(h.title.lower().split())
        pos  += len(words & POSITIVE_WORDS)
        neg  += len(words & NEGATIVE_WORDS)
    if pos == neg:
        return "neutral"
    return "positive" if pos > neg else "negative"

async def _fetch_from_newsapi(
    query: str,
    client: httpx.AsyncClient,
) -> Optional[list[dict]]:
    if not settings.newsapi_key:
        return None
    from_date = (
        datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d")
    try:
        resp = await client.get(
            NEWSAPI_BASE,
            params={
                "q":        query,
                "from":     from_date,
                "sortBy":   "publishedAt",
                "language": "en",
                "pageSize": MAX_ARTICLES,
                "apiKey":   settings.newsapi_key,
            },
            timeout=12.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok" and data.get("articles"):
            return data["articles"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("NewsAPI rate limit — trying FMP news")
        else:
            logger.warning(f"NewsAPI HTTP {e.response.status_code}")
    except Exception as e:
        logger.warning(f"NewsAPI failed: {e}")
    return None

async def _fetch_from_fmp_news(
    tickers: str,
    client: httpx.AsyncClient,
) -> Optional[list[dict]]:
    if not settings.fmp_api_key:
        return None
    try:
        resp = await client.get(
            FMP_NEWS_URL,
            params={
                "tickers": tickers,
                "limit":   MAX_ARTICLES,
                "apikey":  settings.fmp_api_key,
            },
            timeout=12.0,
        )
        if resp.status_code != 200:
            logger.warning(f"FMP news HTTP {resp.status_code}")
            return None
        data = resp.json()
        if isinstance(data, list) and data:
            
            normalised = []
            for item in data:
                normalised.append({
                    "title":       item.get("title", ""),
                    "source":      {"name": item.get("site", "FMP")},
                    "publishedAt": item.get("publishedDate", ""),
                    "url":         item.get("url", ""),
                })
            return normalised
    except Exception as e:
        logger.warning(f"FMP news failed: {e}")
    return None

async def _fetch_from_tavily_news(query: str) -> list[dict]:
    if not settings.tavily_api_key:
        return []
    try:
        from tavily import AsyncTavilyClient
        tv = AsyncTavilyClient(api_key=settings.tavily_api_key)
        response = await tv.search(
            query=f"{query} news recent",
            search_depth="basic",
            max_results=MAX_ARTICLES,
            include_answer=False,
            topic="news",
        )
        articles = []
        for item in response.get("results", []):
            articles.append({
                "title":       item.get("title", ""),
                "source":      {"name": item.get("url", "").split("/")[2] if item.get("url") else "Unknown"},
                "publishedAt": item.get("published_date", ""),
                "url":         item.get("url", ""),
            })
        return articles
    except Exception as e:
        logger.warning(f"Tavily news failed: {e}")
        return []

def _parse_articles(
    raw_articles: list[dict],
    source_label: str,
) -> list["NewsHeadline"]:
    headlines = []
    for art in raw_articles[:MAX_ARTICLES]:
        title = art.get("title") or art.get("name") or ""
        if not title or title == "[Removed]":
            continue
        source_name = art.get("source", {}).get("name") or source_label
        published_at = art.get("publishedAt") or art.get("published_date") or ""
        url = art.get("url") or ""
        headlines.append(NewsHeadline(
            title=title.strip(),
            source=source_name,
            published_at=published_at,
            url=url,
        ))
    return headlines

async def fetch_news_sentiment(
    query: str,
    ticker: str = "",
) -> "NewsSentimentData":
    async with httpx.AsyncClient(timeout=15.0) as client:

        # 1 – NewsAPI
        raw = await _fetch_from_newsapi(query, client)
        source_used = "newsapi"

        # 2 – FMP news (use ticker if available, else query string)
        if not raw:
            fmp_key = ticker.upper() if ticker else query
            raw = await _fetch_from_fmp_news(fmp_key, client)
            source_used = "fmp"

    # 3 – Tavily
    if not raw:
        raw = await _fetch_from_tavily_news(query)
        source_used = "tavily"

    headlines = _parse_articles(raw or [], source_used)

    if not headlines:
        logger.warning(f"No news found for query='{query}'")
        return NewsSentimentData(
            headlines=[],
            sentiment="neutral",
            article_count=0,
            source_used=source_used,
        )

    sentiment = _score_sentiment(headlines)
    logger.info(
        f"News OK: {len(headlines)} articles | "
        f"sentiment={sentiment} | source={source_used}"
    )

    return NewsSentimentData(
        headlines=headlines,
        sentiment=sentiment,
        article_count=len(headlines),
        source_used=source_used,
    )
