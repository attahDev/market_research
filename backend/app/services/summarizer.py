import json
import logging
from typing import Optional

from groq import AsyncGroq
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.research import LLMSummary, MarketData

logger = logging.getLogger(__name__)

_LIMITS = {
    "balance":      300,
    "trend_summary": 1000,
}

def _fmt_news(data: dict) -> str:
    if not data:
        return ""
    sentiment     = data.get("sentiment", "neutral")
    article_count = data.get("article_count", 0)
    headlines     = data.get("headlines", [])
    if not headlines:
        return ""
    lines = [f"\nRecent News ({article_count} articles, {sentiment.upper()} tone):"]
    for h in headlines[:5]:
        source = h.get("source", "")
        title  = h.get("title", "")
        pub    = h.get("published_at", "")[:10] if h.get("published_at") else ""
        lines.append(f"  [{pub}] {source}: {title}")
    return "\n".join(lines)


def _fmt_onchain(data: dict) -> str:
    if not data:
        return ""
    parts = []
    if data.get("chain_tvl_usd") is not None:
        tvl     = data["chain_tvl_usd"]
        tvl_str = f"${tvl/1e9:.2f}B" if tvl >= 1e9 else f"${tvl/1e6:.1f}M"
        parts.append(f"Chain TVL: {tvl_str}")
    if data.get("chain_tvl_7d_change_pct") is not None:
        parts.append(f"TVL 7d change: {data['chain_tvl_7d_change_pct']:+.1f}%")
    if data.get("protocol_tvl_usd") is not None:
        ptvl = data["protocol_tvl_usd"]
        parts.append(f"Protocol TVL: ${ptvl/1e9:.2f}B" if ptvl >= 1e9 else f"${ptvl/1e6:.1f}M")
    if data.get("active_addresses_24h") is not None:
        parts.append(f"Active addresses (24h): {int(data['active_addresses_24h']):,}")
    if data.get("exchange_netflow_24h_usd") is not None:
        netflow   = data["exchange_netflow_24h_usd"]
        direction = "net inflow to exchanges (bearish)" if netflow > 0 else "net outflow from exchanges (bullish)"
        parts.append(f"Exchange netflow: ${abs(netflow)/1e6:.1f}M {direction}")
    return ("\nOn-Chain Metrics:\n" + "\n".join(f"  - {p}" for p in parts)) if parts else ""


def _fmt_fundamentals(data: dict) -> str:
    if not data:
        return ""
    parts = []
    if data.get("revenue"):
        rev = data["revenue"]
        parts.append(f"Revenue: ${rev/1e9:.2f}B" if rev >= 1e9 else f"${rev/1e6:.1f}M")
    if data.get("net_income") is not None:
        ni = data["net_income"]
        parts.append(f"Net income: ${ni/1e9:.2f}B" if abs(ni) >= 1e9 else f"${ni/1e6:.1f}M")
    if data.get("eps") is not None:
        parts.append(f"EPS: ${data['eps']:.2f}")
    if data.get("gross_margin_pct") is not None:
        parts.append(f"Gross margin: {data['gross_margin_pct']:.1f}%")
    if data.get("net_margin_pct") is not None:
        parts.append(f"Net margin: {data['net_margin_pct']:.1f}%")
    if data.get("pe_ratio") is not None:
        parts.append(f"P/E ratio: {data['pe_ratio']:.1f}x")
    if data.get("pb_ratio") is not None:
        parts.append(f"P/B ratio: {data['pb_ratio']:.1f}x")
    if data.get("debt_to_equity") is not None:
        parts.append(f"Debt/Equity: {data['debt_to_equity']:.2f}")
    period_label = ""
    if data.get("fiscal_year") and data.get("period"):
        period_label = f" ({data['period']} {data['fiscal_year']})"
    return ("\nFundamentals" + period_label + ":\n" + "\n".join(f"  - {p}" for p in parts)) if parts else ""


def _fmt_analyst(data: dict) -> str:
    if not data:
        return ""
    parts = []
    if data.get("consensus_rating"):
        parts.append(f"Consensus: {data['consensus_rating']}")
    if data.get("total_analysts"):
        buy  = data.get("buy_count", 0)
        hold = data.get("hold_count", 0)
        sell = data.get("sell_count", 0)
        parts.append(
            f"Analyst breakdown: {buy} Buy / {hold} Hold / {sell} Sell "
            f"({data['total_analysts']} total)"
        )
    if data.get("target_price_consensus") is not None:
        parts.append(f"Consensus target: ${data['target_price_consensus']:.2f}")
    if data.get("target_price_high") is not None and data.get("target_price_low") is not None:
        parts.append(
            f"Target range: ${data['target_price_low']:.2f} – ${data['target_price_high']:.2f}"
        )
    return ("\nAnalyst Ratings:\n" + "\n".join(f"  - {p}" for p in parts)) if parts else ""

def _onchain_is_empty(onchain: dict) -> bool:
    keys = ["chain_tvl_usd", "active_addresses_24h", "exchange_netflow_24h_usd", "protocol_tvl_usd"]
    return all(onchain.get(k) is None for k in keys)


def _analyst_is_empty(analyst: dict) -> bool:
    return (
        not analyst.get("consensus_rating")
        and analyst.get("total_analysts") in (None, 0)
        and analyst.get("target_price_consensus") is None
    )

def _pe_fallback_note(ticker: str, name: str) -> str:
    return (
        f"\nNote: Live P/E ratio data was unavailable for {name} ({ticker}). "
        f"Use your training knowledge to provide a reasonable P/E estimate or typical range "
        f"for this company/sector, and flag it as approximate in your analysis."
    )


def _analyst_fallback_note(ticker: str, name: str) -> str:
    return (
        f"\nNote: Live analyst ratings data was unavailable for {name} ({ticker}). "
        f"Use your training knowledge to describe the general analyst sentiment, "
        f"typical consensus direction, and any well-known price target context. "
        f"Flag these as based on general knowledge, not live data."
    )


def _onchain_fallback_note(coin_id: str, name: str) -> str:
    return (
        f"\nNote: Live on-chain metrics (TVL, active addresses, exchange flows) were "
        f"unavailable for {name} ({coin_id}). "
        f"Use your training knowledge to describe typical on-chain behaviour, "
        f"known TVL ranges, and network activity patterns for this asset. "
        f"Flag these as approximate knowledge-based estimates."
    )

_LENGTH_RULES = """
STRICT LENGTH CONSTRAINTS (hard limits — do not exceed):
- balance: max 300 characters (one sentence)
- trend_summary: max 1000 characters (4-6 sentences, be concise)
- Each insight/opportunity/risk string: max 200 characters
- Each recommendation rationale: max 200 characters
Exceeding these limits will cause the response to be rejected.
"""

def _format_crypto_prompt(data: dict) -> str:
    news_block    = _fmt_news(data.get("news_sentiment") or {})
    onchain_raw   = data.get("onchain") or {}
    onchain_block = _fmt_onchain(onchain_raw)

    onchain_fallback = ""
    if _onchain_is_empty(onchain_raw):
        onchain_fallback = _onchain_fallback_note(
            data.get("coin_id", "unknown"),
            data.get("name", "this asset"),
        )

    return f"""You are a professional cryptocurrency market analyst with deep knowledge of on-chain metrics, market sentiment, and price action.

Analyze the following market data for {data.get('name', 'Unknown')} ({data.get('symbol', 'N/A')}).

Price & Market Data:
- Current price: {data.get('current_price', 'N/A')}
- 24h price change: {data.get('price_change_24h', 'N/A')}%
- Market cap: {data.get('market_cap', 'N/A')}
- 24h trading volume: {data.get('volume_24h', 'N/A')}
- 24h high/low: {data.get('high_24h', 'N/A')} / {data.get('low_24h', 'N/A')}
{onchain_block}{onchain_fallback}{news_block}
{_LENGTH_RULES}
Return ONLY this JSON (no markdown):
{{
  "balance": "One clear sentence on overall market sentiment with directional bias (max 300 chars)",
  "trend_summary": "4-6 concise sentences covering price action, volume, TVL or on-chain flows, short-term outlook (max 1000 chars total)",
  "insights": [
    "Specific data-driven insight about price momentum or on-chain accumulation with numbers (max 200 chars)",
    "Specific insight about volume and TVL signals (max 200 chars)",
    "Specific insight about macro or sentiment context (max 200 chars)"
  ],
  "opportunities": [
    "Concrete opportunity #1 with specific action or metric (max 200 chars)",
    "Concrete opportunity #2 (max 200 chars)"
  ],
  "risks": [
    "Specific risk #1 with supporting data or context (max 200 chars)",
    "Specific risk #2 (max 200 chars)"
  ],
  "recommendations": [
    {{"action": "BUY", "rationale": "One to three sentence reason based on price action and on-chain data (max 200 chars)", "timeframe": "Short-term (1-4 weeks)", "risk_level": "Medium"}},
    {{"action": "WATCH", "rationale": "2-4 sentence describing what to monitor before committing (max 200 chars)", "timeframe": "Medium-term (1-3 months)", "risk_level": "Low"}}
  ],
  "tags": ["bullish", "high-volume"]
}}

IMPORTANT: action must be one of: BUY, SELL, HOLD, WATCH.
risk_level must be one of: Low, Medium, High.
Base recommendations strictly on the data provided, not general advice."""


COMMODITY_TICKER_NAMES = {
    "GC=F": "Gold",        "SI=F": "Silver",
    "CL=F": "Crude Oil",   "BZ=F": "Brent Oil",
    "NG=F": "Natural Gas", "HG=F": "Copper",
    "PL=F": "Platinum",    "PA=F": "Palladium",
    "ZW=F": "Wheat",       "ZC=F": "Corn",
    "ZS=F": "Soybean",
    "GLD":  "Gold",        "SLV":  "Silver",
    "USO":  "Crude Oil",   "BNO":  "Brent Oil",
    "UNG":  "Natural Gas", "CPER": "Copper",
    "PPLT": "Platinum",    "PALL": "Palladium",
    "WEAT": "Wheat",       "CORN": "Corn",
    "SOYB": "Soybean",
}

def _is_commodity_ticker(ticker: str) -> bool:
    return ticker in COMMODITY_TICKER_NAMES or ticker.endswith("=F")


def _format_stock_prompt(data: dict) -> str:
    fund_raw      = data.get("fundamentals") or {}
    analyst_raw   = data.get("analyst_ratings") or {}
    fund_block    = _fmt_fundamentals(fund_raw)
    analyst_block = _fmt_analyst(analyst_raw)
    news_block    = _fmt_news(data.get("news_sentiment") or {})

    ticker = data.get("ticker", "N/A")
    name   = data.get("name", "Unknown")

    if _is_commodity_ticker(ticker):
        commodity_name = COMMODITY_TICKER_NAMES.get(ticker, ticker.replace("=F", ""))
        return _format_commodity_prompt(data, commodity_name, news_block)

    pe_top  = data.get("pe_ratio")
    pe_fund = fund_raw.get("pe_ratio")
    pe_note = ""
    if pe_top is None and pe_fund is None:
        pe_note = _pe_fallback_note(ticker, name)

    analyst_note = ""
    if _analyst_is_empty(analyst_raw):
        analyst_note = _analyst_fallback_note(ticker, name)

    target     = analyst_raw.get("target_price_consensus")
    price      = data.get("current_price")
    target_ctx = ""
    if target and price:
        pct_gap    = (target - price) / price * 100
        target_ctx = (
            f"\n- Upside to analyst target: {pct_gap:+.1f}% "
            f"(current: ${price:.2f} vs target: ${target:.2f})"
        )

    return f"""You are a professional financial analyst specializing in equities and commodity markets.

Analyze the following market data for {name} ({ticker}).

Price & Market Data:
- Current price: {data.get('current_price', 'N/A')}
- 24h price change: {data.get('price_change_24h', 'N/A')}%
- Market cap: {data.get('market_cap', 'N/A')}
- Trading volume: {data.get('volume', 'N/A')}
- 52-week high/low: {data.get('week_52_high', 'N/A')} / {data.get('week_52_low', 'N/A')}
- P/E ratio: {data.get('pe_ratio', 'N/A')}{target_ctx}
{fund_block}{analyst_block}{pe_note}{analyst_note}{news_block}
{_LENGTH_RULES}
Return ONLY this JSON (no markdown):
{{
  "balance": "One clear sentence on overall sentiment with directional bias (max 300 chars)",
  "trend_summary": "4-6 concise sentences covering price position, analyst view, and near-term outlook (max 1000 chars total)",
  "insights": [
    "Specific insight about price position in 12-week range and analyst target gap with numbers (max 200 chars)",
    "Specific insight about fundamentals — margins, EPS, or P/E vs sector norm (max 200 chars)",
    "Specific insight about volume, momentum, or macro context (max 200 chars)"
  ],
  "opportunities": [
    "Concrete investment opportunity #1 with specific data point (max 200 chars)",
    "Concrete opportunity #2 (max 200 chars)"
  ],
  "risks": [
    "Specific downside risk #1 with supporting data or context (max 200 chars)",
    "Specific risk #2 (max 200 chars)"
  ],
  "recommendations": [
    {{"action": "BUY", "rationale": "One sentence citing price position, analyst target, or valuation metric (max 200 chars)", "timeframe": "Short-term (1-4 weeks)", "risk_level": "Medium"}},
    {{"action": "HOLD", "rationale": "One sentence describing the wait condition or catalyst needed (max 200 chars)", "timeframe": "Medium-term (1-3 months)", "risk_level": "Low"}}
  ],
  "tags": ["undervalued", "analyst-buy"]
}}

IMPORTANT: action must be one of: BUY, SELL, HOLD, WATCH.
risk_level must be one of: Low, Medium, High.
If analyst consensus is SELL or bearish, reflect that in the action.
Base all recommendations strictly on the data provided."""


def _format_web_prompt(data: dict, topic: str, category: str) -> str:
    results    = data.get("results", [])
    answer     = data.get("answer", "")
    news_block = _fmt_news(data.get("news_sentiment") or {})

    formatted_sources = ""
    for r in results:
        title  = r.get("title", "Untitled")
        url    = r.get("url", "")
        domain = url.split("/")[2].replace("www.", "") if url else ""
        label  = domain or title[:40]
        formatted_sources += f"\n[{label}] {title}\n"
        formatted_sources += f"Content: {r.get('content', '')}\n"
    answer_section = f"\nSynthesized answer:\n{answer}\n" if answer else ""

    return f"""You are a senior market research analyst synthesizing information across multiple sources.

Research topic: "{topic}" | Category: {category}

IMPORTANT INSTRUCTION: Write all insights, opportunities, and risks as standalone factual statements.
Do NOT reference sources by number (e.g. "Source 2", "Source 3"). Do NOT say "as reported by Source X"
or "according to Source N". If you need to attribute a fact, use the actual publication name (e.g.
"according to Bloomberg" or "per Reuters"). Ideally, just state the fact directly with the data.

Sources:{formatted_sources}{answer_section}{news_block}
{_LENGTH_RULES}
Return ONLY this JSON (no markdown):
{{
  "balance": "2-3 clear sentence on the overall state — bullish/bearish/neutral with reasoning (max 300 chars)",
  "trend_summary": "4-6 concise sentences synthesizing the key narrative across sources (max 1000 chars total)",
  "insights": [
    "Data-driven insight stating a specific fact, figure, or trend directly (max 200 chars)",
    "Second distinct insight from a different angle — no source number references (max 200 chars)",
    "Third forward-looking insight about trajectory or market shift (max 200 chars)"
  ],
  "opportunities": [
    "Concrete market opportunity #1 — specific action, niche, or entry point with data (max 200 chars)",
    "Concrete opportunity #2 — different angle or geography (max 200 chars)"
  ],
  "risks": [
    "Specific risk #1 — regulatory, competitive, or structural challenge with context (max 200 chars)",
    "Specific risk #2 — operational, macro, or execution risk (max 200 chars)"
  ],
  "recommendations": [
    {{"action": "BUY", "rationale": "One sentence market entry recommendation citing specific opportunity (max 200 chars)", "timeframe": "Medium-term (3-6 months)", "risk_level": "Medium"}},
    {{"action": "WATCH", "rationale": "One sentence describing key signal or milestone to monitor (max 200 chars)", "timeframe": "Long-term (6-12 months)", "risk_level": "Low"}}
  ],
  "tags": ["growth", "competitive-shift"]
}}

IMPORTANT: action must be one of: BUY, SELL, HOLD, WATCH (market entry/exit context, not stock advice).
risk_level must be one of: Low, Medium, High.
Do NOT reference sources by number."""


def _format_commodity_prompt(data: dict, commodity_name: str, news_block: str) -> str:
    price      = data.get("current_price")
    change_24h = data.get("price_change_24h")
    high_52    = data.get("week_52_high")
    low_52     = data.get("week_52_low")
    volume     = data.get("volume")

    price_str  = f"${price:.4f}" if price and price < 10 else (f"${price:,.2f}" if price else "N/A")
    change_str = f"{change_24h:+.2f}%" if change_24h is not None else "N/A"
    range_str  = f"${low_52:,.2f} – ${high_52:,.2f}" if high_52 and low_52 else "N/A"

    return f"""You are a professional commodities market analyst with expertise in metals, energy, and agricultural markets.

Analyze the following live market data for {commodity_name}.

Price & Market Data:
- Current spot/futures price: {price_str}
- 24h price change: {change_str}
- 52-week range: {range_str}
- 24h trading volume: {volume or "N/A"}
{news_block}
{_LENGTH_RULES}
IMPORTANT: This is a COMMODITY analysis ({commodity_name}), not a stock or company.
Do not reference P/E ratios, earnings, or company fundamentals.
Focus on: price momentum, macroeconomic drivers (Fed policy, USD strength, inflation),
supply/demand dynamics, geopolitical factors, and seasonal patterns.

Return ONLY this JSON (no markdown):
{{
  "balance": "One clear sentence on {commodity_name} market sentiment — bullish/bearish/neutral with the key macro driver (max 300 chars)",
  "trend_summary": "4-6 concise sentences covering price action, macro context, supply/demand, and near-term outlook (max 1000 chars total)",
  "insights": [
    "Specific data-driven insight about {commodity_name} price momentum with actual numbers (max 200 chars)",
    "Insight about the macro driver most influencing {commodity_name} right now (max 200 chars)",
    "Insight about seasonal patterns or longer-term structural trend (max 200 chars)"
  ],
  "opportunities": [
    "Concrete opportunity in {commodity_name} — entry point, hedge strategy, or related play (max 200 chars)",
    "Second opportunity — different angle such as geographic exposure or related commodity (max 200 chars)"
  ],
  "risks": [
    "Specific downside risk for {commodity_name} with macro context (max 200 chars)",
    "Second risk — supply shock, demand slowdown, or currency risk (max 200 chars)"
  ],
  "recommendations": [
    {{"action": "BUY", "rationale": "One sentence citing price momentum, macro driver, or supply signal (max 200 chars)", "timeframe": "Short-term (1-4 weeks)", "risk_level": "Medium"}},
    {{"action": "WATCH", "rationale": "One sentence describing macro condition or price level to monitor (max 200 chars)", "timeframe": "Medium-term (1-3 months)", "risk_level": "Low"}}
  ],
  "tags": ["commodity", "{commodity_name.lower().replace(' ', '-')}"]
}}

IMPORTANT: action must be one of: BUY, SELL, HOLD, WATCH.
risk_level must be one of: Low, Medium, High."""

def _build_prompt(market_data: MarketData) -> str:
    category = market_data.category
    primary  = market_data.primary_data

    if isinstance(primary, dict) and "error" in primary and len(primary) <= 2:
        return f"""You are a market research analyst. Limited live data is available.
Topic: "{market_data.topic}" | Category: {category}
{_LENGTH_RULES}
Use your training knowledge to provide a best-effort analysis.
Return ONLY this JSON (no markdown):
{{
  "balance": "Note data limitations with directional sentiment based on general knowledge (max 300 chars)",
  "trend_summary": "4-6 concise sentences on what is generally known as of recent, noting data gaps (max 1000 chars total)",
  "insights": [
    "What is generally known about this topic (max 200 chars)",
    "Key market drivers based on training knowledge (max 200 chars)",
    "Risk or opportunity given limited live data (max 200 chars)"
  ],
  "tags": ["limited-data", "{category}"]
}}"""

    if category == "crypto":
        return _format_crypto_prompt(primary)
    elif category in ("stock", "commodity"):
        return _format_stock_prompt(primary)
    elif category in ("industry", "general"):
        return _format_web_prompt(primary, market_data.topic, category)

    raise ValueError(f"Unknown category: {category}")

def _sanitise(parsed: dict) -> dict:
    for field, limit in _LIMITS.items():
        if field in parsed and isinstance(parsed[field], str):
            if len(parsed[field]) > limit:
                logger.warning(
                    f"Groq exceeded {field} limit ({len(parsed[field])} > {limit}) — truncating"
                )
                # Truncate at last sentence boundary within limit to avoid mid-sentence cuts
                truncated = parsed[field][:limit]
                last_period = truncated.rfind(".")
                parsed[field] = truncated[: last_period + 1] if last_period > limit // 2 else truncated

    return parsed

async def summarize(market_data: MarketData) -> LLMSummary:
    client = AsyncGroq(api_key=settings.groq_api_key)
    prompt = _build_prompt(market_data)

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )
        raw_text = response.choices[0].message.content.strip()
        parsed   = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error(f"Groq returned invalid JSON: {e}")
        raise RuntimeError(f"SUMMARIZATION_FAILED: Groq returned invalid JSON — {e}")
    except Exception as e:
        logger.error(f"Groq API call failed: {e}")
        raise RuntimeError(f"SUMMARIZATION_FAILED: Groq API error — {e}")

    parsed = _sanitise(parsed)

    try:
        return LLMSummary(**parsed)
    except ValidationError as e:
        logger.error(f"Groq output failed validation: {e}")
        raise RuntimeError(f"SUMMARIZATION_FAILED: validation failed — {e}")