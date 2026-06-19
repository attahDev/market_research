import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.research import CryptoData

logger = logging.getLogger(__name__)

COINGECKO_SEARCH_URL       = f"{settings.coingecko_base_url}/search"
COINGECKO_COINS_URL        = f"{settings.coingecko_base_url}/coins/markets"
COINGECKO_OHLC_URL         = f"{settings.coingecko_base_url}/coins/{{coin_id}}/ohlc"
COINGECKO_MARKET_CHART_URL = f"{settings.coingecko_base_url}/coins/{{coin_id}}/market_chart"

COINGECKO_SEMAPHORE = asyncio.Semaphore(8)

KNOWN_COIN_IDS: dict[str, str] = {
    "bitcoin":   "bitcoin",
    "btc":       "bitcoin",
    "ethereum":  "ethereum",
    "eth":       "ethereum",
    "solana":    "solana",
    "sol":       "solana",
    "cardano":   "cardano",
    "ada":       "cardano",
    "ripple":    "ripple",
    "xrp":       "ripple",
    "dogecoin":  "dogecoin",
    "doge":      "dogecoin",
    "binance":   "binancecoin",
    "bnb":       "binancecoin",
    "litecoin":  "litecoin",
    "ltc":       "litecoin",
    "polygon":   "matic-network",
    "matic":     "matic-network",
    "avalanche": "avalanche-2",
    "avax":      "avalanche-2",
    "chainlink": "chainlink",
    "link":      "chainlink",
    "uniswap":   "uniswap",
    "uni":       "uniswap",
    "polkadot":  "polkadot",
    "dot":       "polkadot",
    "shiba":     "shiba-inu",
    "shib":      "shiba-inu",
    "tron":      "tron",
    "trx":       "tron",
}

PERIOD_TO_DAYS: dict[str, int] = {
    "1d":  2,
    "7d":  7,
    "30d": 30,
    "1y":  365,
    "5y":  1825,
}


def _build_headers() -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": "market-research-ai/1.0",
    }
    if settings.coingecko_api_key:
        headers["x-cg-demo-api-key"] = settings.coingecko_api_key
    return headers


async def _search_coin_id(query: str, client: httpx.AsyncClient) -> Optional[str]:
    query_lower = query.lower().strip()

    for keyword, coin_id in KNOWN_COIN_IDS.items():
        if keyword in query_lower:
            return coin_id

    try:
        async with COINGECKO_SEMAPHORE:
            resp = await client.get(
                COINGECKO_SEARCH_URL,
                params={"query": query_lower},
                timeout=10.0,
            )
        resp.raise_for_status()
        coins = resp.json().get("coins", [])
        if coins:
            return coins[0]["id"]
    except Exception as e:
        logger.warning(f"CoinGecko search failed query='{query}' error={e}")

    return None


async def _fetch_ohlc_for_period(
    period_key: str,
    coin_id: str,
    days: int,
    client: httpx.AsyncClient,
) -> tuple[str, list]:

    # Primary: OHLC endpoint
    for attempt in range(2):
        try:
            async with COINGECKO_SEMAPHORE:
                resp = await client.get(
                    COINGECKO_OHLC_URL.format(coin_id=coin_id),
                    params={"vs_currency": "usd", "days": days},
                    timeout=10.0,
                )
            resp.raise_for_status()
            raw = resp.json()
            if raw:
                formatted = []
                for row in raw:
                    try:
                        formatted.append({
                            "time":  row[0],
                            "open":  round(float(row[1]), 8),
                            "high":  round(float(row[2]), 8),
                            "low":   round(float(row[3]), 8),
                            "close": round(float(row[4]), 8),
                        })
                    except Exception:
                        continue
                return period_key, formatted
        except Exception as e:
            logger.warning(
                f"OHLC fetch failed coin={coin_id} "
                f"period={period_key} attempt={attempt + 1} error={e}"
            )

    # Fallback: market_chart endpoint
    try:
        params: dict = {"vs_currency": "usd", "days": days}
        if days > 1:
            params["interval"] = "hourly"
        async with COINGECKO_SEMAPHORE:
            resp = await client.get(
                COINGECKO_MARKET_CHART_URL.format(coin_id=coin_id),
                params=params,
                timeout=10.0,
            )
        resp.raise_for_status()
        prices = resp.json().get("prices", [])
        if prices:
            formatted = []
            for p in prices:
                try:
                    price = round(float(p[1]), 8)
                    formatted.append({
                        "time": p[0], "open": price,
                        "high": price, "low": price, "close": price,
                    })
                except Exception:
                    continue
            return period_key, formatted
    except Exception as e:
        logger.warning(
            f"History unavailable coin={coin_id} period={period_key} error={e}"
        )

    return period_key, []


async def fetch_crypto(query: str) -> CryptoData:
    async with httpx.AsyncClient(headers=_build_headers(), timeout=15.0) as client:

        coin_id = await _search_coin_id(query, client)
        if not coin_id:
            raise ValueError(f"Could not identify cryptocurrency from query='{query}'")

        try:
            async def _market_request():
                async with COINGECKO_SEMAPHORE:
                    return await client.get(
                        COINGECKO_COINS_URL,
                        params={
                            "vs_currency": "usd",
                            "ids": coin_id,
                            "order": "market_cap_desc",
                            "per_page": 1,
                            "page": 1,
                            "sparkline": False,
                            "price_change_percentage": "24h",
                        },
                    )

            results = await asyncio.gather(
                _market_request(),
                *[
                    _fetch_ohlc_for_period(period, coin_id, days, client)
                    for period, days in PERIOD_TO_DAYS.items()
                ],
                return_exceptions=True,
            )

            market_resp = results[0]
            if isinstance(market_resp, Exception):
                raise market_resp
            market_resp.raise_for_status()

            coins = market_resp.json()
            if not coins:
                raise ValueError(f"No CoinGecko market data for coin='{coin_id}'")

            coin = coins[0]
            if coin.get("current_price") is None:
                raise ValueError(f"CoinGecko returned empty pricing for '{coin_id}'")

            ohlc: dict[str, list] = {"1d": [], "7d": [], "30d": [], "1y": [], "5y": []}
            for hist_result in results[1:]:
                if isinstance(hist_result, tuple):
                    period_key, data_list = hist_result
                    ohlc[period_key] = data_list

            return CryptoData(
                name=coin.get("name", coin_id),
                symbol=coin.get("symbol", "").upper(),
                current_price=coin.get("current_price"),
                price_change_24h=coin.get("price_change_percentage_24h"),
                market_cap=coin.get("market_cap"),
                volume_24h=coin.get("total_volume"),
                high_24h=coin.get("high_24h"),
                low_24h=coin.get("low_24h"),
                last_updated=coin.get("last_updated") or datetime.now(timezone.utc).isoformat(),
                ohlc_1d=ohlc["1d"],
                ohlc_7d=ohlc["7d"],
                ohlc_30d=ohlc["30d"],
                ohlc_1y=ohlc["1y"],
                ohlc_5y=ohlc["5y"],
                coin_id=coin_id,
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise ValueError("CoinGecko rate limit hit — retry shortly")
            raise ValueError(f"CoinGecko API error HTTP {e.response.status_code}")

        except httpx.TimeoutException:
            raise ValueError("CoinGecko request timed out")

        except Exception as e:
            logger.error(f"CoinGecko fetch failed coin={coin_id} error={e}")
            raise ValueError(f"CoinGecko fetch error: {e}")