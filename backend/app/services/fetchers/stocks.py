import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.core.config import settings
from app.schemas.research import AnalystRatingsData, FundamentalsData, StockData

logger = logging.getLogger(__name__)

TIINGO_BASE = "https://api.tiingo.com"
TIINGO_SEMAPHORE = asyncio.Semaphore(10)

COMMODITY_TICKERS: dict[str, str] = {
    "gold":        "GLD", 
    "gold market": "GLD",
    "silver":      "SLV",
    "oil":         "USO",
    "crude":       "USO",
    "crude oil":   "USO",
    "wti":         "USO",
    "brent":       "BNO",
    "brent oil":   "BNO",
    "natural gas": "UNG",
    "copper":      "CPER",
    "platinum":    "PPLT",
    "palladium":   "PALL",
    "wheat":       "WEAT",
    "corn":        "CORN",
    "soybean":     "SOYB",
}

KNOWN_TICKERS: dict[str, str] = {
    "apple":     "AAPL",
    "microsoft": "MSFT",
    "google":    "GOOGL",
    "alphabet":  "GOOGL",
    "amazon":    "AMZN",
    "tesla":     "TSLA",
    "nvidia":    "NVDA",
    "meta":      "META",
    "facebook":  "META",
    "netflix":   "NFLX",
}

def _extract_ticker(query: str, category: str) -> Optional[str]:
    q = query.lower()
    if category == "commodity":
        for k, v in COMMODITY_TICKERS.items():
            if k in q:
                return v
        return None
    for k, v in KNOWN_TICKERS.items():
        if k in q:
            return v
    matches = re.findall(r"\b[A-Z]{1,10}(?:-[A-Z])?\b", query.upper())
    return matches[0] if matches else None

def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")

def _parse_iso(date_str: str) -> int:
    try:
        fmt = "%Y-%m-%dT%H:%M:%S+00:00" if "T" in date_str else "%Y-%m-%d"
        dt = datetime.strptime(date_str[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) \
             if "T" in date_str else \
             datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0

async def _fetch(
    client: httpx.AsyncClient,
    path: str,
    params: dict | None = None,
) -> Optional[dict | list]:
    headers = {
        "Authorization": f"Token {settings.tiingo_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with TIINGO_SEMAPHORE:
            r = await client.get(
                f"{TIINGO_BASE}/{path.lstrip('/')}",
                params=params or {},
                headers=headers,
                timeout=15.0,
            )
        if r.status_code == 403:
            logger.warning(f"Tiingo {path} → 403 (check plan/add-on entitlement)")
            return None
        if r.status_code != 200:
            logger.warning(f"Tiingo {path} → HTTP {r.status_code}")
            return None
        return r.json()
    except Exception as e:
        logger.error(f"Tiingo crash {path}: {e}")
        return None

def _build_fundamentals(
    daily_rows: list,
    statements: list,
    ticker: str,
) -> FundamentalsData:
    def pick(*values):
        for v in values:
            if v is not None and v != 0:
                return v
        return None

    latest_daily = daily_rows[0] if daily_rows else {}
    latest_stmt  = statements[0]  if statements  else {}
    stmt_data   = latest_stmt.get("statementData", {})
    income_rows = stmt_data.get("incomeStatement", [])
    cashflow_rows = stmt_data.get("cashFlow", [])

    def _stmt_val(rows: list, key: str):
        for row in rows:
            if row.get("dataCode") == key:
                return row.get("value")
        return None

    revenue           = _stmt_val(income_rows, "revenue")
    net_income        = _stmt_val(income_rows, "netInc")
    eps               = _stmt_val(income_rows, "eps")
    gross_profit      = _stmt_val(income_rows, "grossProfit")
    operating_cf      = _stmt_val(cashflow_rows, "freeCF") or _stmt_val(cashflow_rows, "operatingCF")
    free_cf           = _stmt_val(cashflow_rows, "freeCF")
    gross_margin = None
    if gross_profit and revenue:
        try:
            gross_margin = round(gross_profit / revenue, 6)
        except ZeroDivisionError:
            pass

    net_margin = None
    if net_income and revenue:
        try:
            net_margin = round(net_income / revenue, 6)
        except ZeroDivisionError:
            pass

    result = FundamentalsData(
        revenue=revenue,
        net_income=net_income,
        eps=eps,
        gross_margin_pct=gross_margin,
        net_margin_pct=net_margin,
        pe_ratio=pick(latest_daily.get("trailingPE"), latest_daily.get("peRatio")),
        pb_ratio=latest_daily.get("pbRatio"),
        debt_to_equity=latest_daily.get("debtEquity"),
        dividend_yield_pct=latest_daily.get("dividendYield"),
        price_to_sales=latest_daily.get("psRatio"),
        enterprise_value=latest_daily.get("enterpriseVal"),
        operating_cash_flow=operating_cf,
        free_cash_flow=free_cf,
    )
    logger.info(
        f"Fundamentals {ticker} | "
        f"pe={result.pe_ratio} eps={result.eps} margin={result.net_margin_pct}"
    )
    return result

async def fetch_stock(query: str, category: str = "stock") -> StockData:
    ticker = _extract_ticker(query, category)
    if not ticker:
        raise ValueError(f"Could not resolve ticker from query: {query}")

    if not settings.tiingo_api_key:
        raise ValueError("TIINGO_API_KEY is not configured")

    now     = datetime.now(timezone.utc)
    start5y = _date_str(now - timedelta(days=365 * 5 + 30))
    today   = _date_str(now)

    async with httpx.AsyncClient(timeout=20) as client:
        (
            meta_res,
            latest_res,
            history_res,
            iex_res,
            fund_daily_res,
            fund_stmts_res,
        ) = await asyncio.gather(
            _fetch(client, f"tiingo/daily/{ticker}"),
            _fetch(client, f"tiingo/daily/{ticker}/prices", {"startDate": today}),
            _fetch(client, f"tiingo/daily/{ticker}/prices", {
                "startDate": start5y,
                "endDate":   today,
                "resampleFreq": "daily",
            }),
            _fetch(client, f"iex/{ticker}"),
            _fetch(client, f"tiingo/fundamentals/{ticker}/daily",      {"startDate": today}),
            _fetch(client, f"tiingo/fundamentals/{ticker}/statements", {"startDate": _date_str(now - timedelta(days=400))}),
        )

    meta = meta_res or {}
    name = meta.get("name") or ticker

    iex      = (iex_res[0] if isinstance(iex_res, list) and iex_res else iex_res) or {}
    eod_list = latest_res if isinstance(latest_res, list) else []
    eod      = eod_list[-1] if eod_list else {}

    current_price  = iex.get("last") or iex.get("tngoLast") or eod.get("close")
    previous_close = eod.get("prevClose") or eod.get("adjClose")
    volume         = iex.get("volume") or eod.get("volume")
    week_52_high   = meta.get("52WeekHigh")   # not always present
    week_52_low    = meta.get("52WeekLow")

    price_change = None
    if current_price and previous_close:
        try:
            price_change = round(
                ((float(current_price) - float(previous_close)) / float(previous_close)) * 100, 4
            )
        except Exception:
            pass

    bars: list[dict] = []
    if isinstance(history_res, list):
        for b in history_res:
            try:
                bars.append({
                    "time":   _parse_iso(b["date"]),
                    "open":   float(b["adjOpen"]  or b["open"]),
                    "high":   float(b["adjHigh"]  or b["high"]),
                    "low":    float(b["adjLow"]   or b["low"]),
                    "close":  float(b["adjClose"] or b["close"]),
                    "volume": int(b.get("adjVolume") or b.get("volume") or 0),
                })
            except Exception:
                continue
    fund_daily = fund_daily_res if isinstance(fund_daily_res, list) else []
    fund_stmts = fund_stmts_res if isinstance(fund_stmts_res, list) else []
    market_cap = None
    if fund_daily:
        market_cap = fund_daily[0].get("marketCap")
    if not market_cap:
        market_cap = iex.get("marketCap")

    fundamentals = _build_fundamentals(fund_daily, fund_stmts, ticker)

    return StockData(
        ticker=ticker,
        name=name,
        current_price=current_price,
        price_change_24h=price_change,
        market_cap=market_cap,
        volume=volume,
        week_52_high=week_52_high,
        week_52_low=week_52_low,
        pe_ratio=fundamentals.pe_ratio,
        last_updated=now.isoformat(),
        ohlc_1d=bars[-24:]   if bars else [],
        ohlc_7d=bars[-168:]  if bars else [],
        ohlc_30d=bars[-720:] if bars else [],
        ohlc_1y=bars[-252:]  if bars else [],
        ohlc_5y=bars[-1260:] if bars else [],
        analyst_ratings=AnalystRatingsData(), 
        fundamentals=fundamentals,
    )