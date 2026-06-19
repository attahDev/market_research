
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

COMMODITY_MAP: dict[str, str] = {
    "gold": "GOLD",
    "silver": "SILVER",
    "copper": "COPPER",
    "platinum": "PLATINUM",
    "palladium": "PALLADIUM",
    "oil": "CRUDE_OIL",
    "crude oil": "CRUDE_OIL",
    "crude": "CRUDE_OIL",
    "wti": "CRUDE_OIL",
    "brent": "BRENT_OIL",
    "natural gas": "NATURAL_GAS",
    "gas": "NATURAL_GAS",
    "wheat": "WHEAT",
    "corn": "CORN",
    "soybean": "SOYBEAN",
    "soybeans": "SOYBEAN",
    "coffee": "COFFEE",
    "sugar": "SUGAR",
    "cotton": "COTTON",
}

CRYPTO_MAP: dict[str, str] = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "cardano": "ADA",
    "ada": "ADA",
    "ripple": "XRP",
    "xrp": "XRP",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "binance coin": "BNB",
    "bnb": "BNB",
    "litecoin": "LTC",
    "ltc": "LTC",
    "polygon": "MATIC",
    "matic": "MATIC",
    "avalanche": "AVAX",
    "avax": "AVAX",
    "chainlink": "LINK",
    "link": "LINK",
    "polkadot": "DOT",
    "dot": "DOT",
    "shiba inu": "SHIB",
    "shib": "SHIB",
    "uniswap": "UNI",
    "uni": "UNI",
    "tron": "TRX",
    "trx": "TRX",
}

STOCK_MAP: dict[str, str] = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "berkshire": "BRK-B",
    "visa": "V",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "johnson": "JNJ",
    "walmart": "WMT",
    "mastercard": "MA",
    "procter": "PG",
    "exxon": "XOM",
    "chevron": "CVX",
    "abbvie": "ABBV",
    "eli lilly": "LLY",
    "lilly": "LLY",
    "broadcom": "AVGO",
    "costco": "COST",
    "asml": "ASML",
    "tsmc": "TSM",
    "alibaba": "BABA",
    "uber": "UBER",
    "lyft": "LYFT",
    "palantir": "PLTR",
    "coinbase": "COIN",
    "shopify": "SHOP",
    "airbnb": "ABNB",
    "doordash": "DASH",
    "snap": "SNAP",
    "spotify": "SPOT",
    "zoom": "ZM",
    "peloton": "PTON",
    "robinhood": "HOOD",
    "block": "SQ",
    "square": "SQ",
}

_NOISE = re.compile(
    r"\b("
    r"trend|analysis|forecast|price|market|commodity|stock|research|"
    r"outlook|invest|investing|should i buy|tell me about|what is|"
    r"earnings|shares|company|corporation|inc|ticker"
    r")\b",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")

_TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:-[A-Z])?)\b")


def _clean(query: str) -> str:
    q = query.lower().strip()

    q = _NOISE.sub(" ", q)

    q = _WHITESPACE.sub(" ", q)

    return q.strip()

def _tables_for_category(category: str):

    if category == "commodity":
        return [COMMODITY_MAP]

    if category == "crypto":
        return [CRYPTO_MAP]

    if category == "stock":
        return [STOCK_MAP]

    return [
        COMMODITY_MAP,
        CRYPTO_MAP,
        STOCK_MAP,
    ]

@lru_cache(maxsize=1024)
def _cached_resolve(
    cleaned_query: str,
    category: str,
) -> Optional[str]:

    for table in _tables_for_category(category):

        for alias in sorted(
            table.keys(),
            key=len,
            reverse=True,
        ):

            if alias in cleaned_query:
                return table[alias]

    matches = _TICKER_PATTERN.findall(
        cleaned_query.upper()
    )

    if matches:
        return matches[0]

    return None

def resolve_symbol(
    query: str,
    category: str = "",
) -> str:

    cleaned = _clean(query)

    result = _cached_resolve(
        cleaned,
        category,
    )

    if result:

        logger.debug(
            f"Resolved '{query}' -> '{result}'"
        )

        return result

    raw_matches = _TICKER_PATTERN.findall(
        query.upper()
    )

    if raw_matches:
        return raw_matches[0]

    return cleaned.upper() or query.upper()

def resolve_multi(
    query: str,
    category: str = "",
) -> list[str]:

    cleaned = _clean(query)

    found: list[str] = []

    seen: set[str] = set()

    for table in _tables_for_category(category):

        for alias in sorted(
            table.keys(),
            key=len,
            reverse=True,
        ):

            if alias in cleaned:

                ticker = table[alias]

                if ticker not in seen:

                    found.append(ticker)

                    seen.add(ticker)

                cleaned = cleaned.replace(
                    alias,
                    " ",
                    1,
                )

    raw_tickers = _TICKER_PATTERN.findall(
        query.upper()
    )

    for ticker in raw_tickers:

        ticker = ticker.upper()

        if ticker not in seen:

            found.append(ticker)

            seen.add(ticker)

    if found:
        return found

    return [resolve_symbol(query, category)]

class EntityExtractionResult:

    __slots__ = (
        "entity",
        "ticker",
        "intent",
        "category",
    )

    def __init__(
        self,
        entity: str,
        ticker: str,
        intent: str,
        category: str,
    ) -> None:

        self.entity = entity
        self.ticker = ticker
        self.intent = intent
        self.category = category

    def __repr__(self) -> str:

        return (
            f"EntityExtractionResult("
            f"entity={self.entity!r}, "
            f"ticker={self.ticker!r}, "
            f"intent={self.intent!r}, "
            f"category={self.category!r})"
        )


async def extract_entity_ai(
    query: str,
) -> EntityExtractionResult:

    cleaned = _clean(query)

    static_match = _cached_resolve(
        cleaned,
        "",
    )

    if static_match:

        return EntityExtractionResult(
            entity=_extract_entity_name_heuristic(query),
            ticker=static_match,
            intent=_infer_intent(query),
            category=_infer_category_from_ticker(static_match),
        )

    try:

        from groq import AsyncGroq
        from app.core.config import settings

        client = AsyncGroq(
            api_key=settings.groq_api_key
        )

        prompt = f"""
Extract financial entity information.

Query:
"{query}"

Return ONLY valid JSON:

{{
  "entity": "",
  "ticker": "",
  "intent": "",
  "category": ""
}}
"""

        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0.1,
            max_tokens=120,
            response_format={
                "type": "json_object"
            },
        )

        data = json.loads(
            response.choices[0].message.content
        )

        entity = data.get("entity") or query

        ticker = data.get("ticker")

        category = data.get("category") or "general"

        if not ticker:

            ticker = resolve_symbol(
                entity,
                category,
            )

        return EntityExtractionResult(
            entity=entity,
            ticker=ticker,
            intent=data.get("intent", "general"),
            category=category,
        )

    except Exception as e:

        logger.warning(
            f"AI extraction failed: {e}"
        )

        return EntityExtractionResult(
            entity=_extract_entity_name_heuristic(query),
            ticker=resolve_symbol(query),
            intent=_infer_intent(query),
            category="general",
        )

async def search_symbol_fallback(
    query: str,
) -> Optional[str]:

    from app.core.config import settings

    if not settings.fmp_api_key:

        logger.warning(
            "FMP API key missing"
        )

        return None

    url = (
        f"{settings.fmp_base_url}"
        f"/v3/search-symbol"
    )

    params = {
        "query": query.strip(),
        "limit": 5,
        "apikey": settings.fmp_api_key,
    }

    try:

        async with httpx.AsyncClient(
            timeout=8.0
        ) as client:

            response = await client.get(
                url,
                params=params,
            )

            response.raise_for_status()

            results = response.json()

            if (
                results
                and isinstance(results, list)
            ):

                best = results[0]

                symbol = best.get("symbol")

                if symbol:

                    logger.info(
                        f"FMP fallback matched "
                        f"'{query}' -> '{symbol}'"
                    )

                    return symbol.upper()

    except Exception as e:

        logger.error(
            f"FMP fallback failed "
            f"for '{query}': {e}"
        )

    return None

def _infer_category_from_ticker(
    ticker: str,
) -> str:

    if ticker in COMMODITY_MAP.values():
        return "commodity"

    if ticker in CRYPTO_MAP.values():
        return "crypto"

    return "stock"

def _extract_entity_name_heuristic(
    query: str,
) -> str:

    q = query.lower()

    for table in [
        STOCK_MAP,
        CRYPTO_MAP,
        COMMODITY_MAP,
    ]:

        for alias in sorted(
            table.keys(),
            key=len,
            reverse=True,
        ):

            if alias in q:
                return alias.title()

    caps = re.findall(
        r"\b[A-Z][a-zA-Z]{1,}\b",
        query,
    )

    if caps:
        return caps[0]

    return (
        query.split()[0].title()
        if query
        else query
    )

def _infer_intent(
    query: str,
) -> str:

    q = query.lower()

    if any(
        w in q
        for w in (
            "invest",
            "buy",
            "sell",
            "should i",
        )
    ):
        return "investment research"

    if any(
        w in q
        for w in (
            "price",
            "worth",
            "cost",
            "trading at",
        )
    ):
        return "price check"

    if any(
        w in q
        for w in (
            "compare",
            "vs",
            "versus",
            "better",
        )
    ):
        return "comparison"

    if any(
        w in q
        for w in (
            "news",
            "latest",
            "recent",
            "today",
        )
    ):
        return "news"

    return "general"