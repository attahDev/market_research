import uuid
from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator


CategoryType = Literal["crypto", "stock", "commodity", "industry", "general"]
StatusType = Literal["pending", "processing", "complete", "failed", "cancelled"]
SourceType = Literal["fresh", "cache"]
ClassifierSourceType = Literal["spacy", "groq"]
PeriodType = Literal["1d", "7d", "30d", "1y", "5y"]
SentimentLabel = Literal["positive", "negative", "neutral"]


class FinalRecommendation(BaseModel):
    action: str       # BUY / SELL / HOLD / WATCH
    rationale: str    # why — 1-2 sentences
    timeframe: str    # e.g. "Short-term (1-4 weeks)"
    risk_level: str   # Low / Medium / High


class LLMSummary(BaseModel):
    balance: str = Field(..., min_length=10, max_length=500)
    trend_summary: str = Field(..., min_length=20, max_length=1000)
    insights: list[str] = Field(..., min_length=3, max_length=3)
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[FinalRecommendation] = Field(default_factory=list)
    tags: list[str] = Field(..., min_length=2, max_length=4)

    @field_validator("insights")
    @classmethod
    def validate_insights(cls, v: list[str]) -> list[str]:
        if len(v) != 3:
            raise ValueError(f"insights must have exactly 3 items, got {len(v)}")
        for i, insight in enumerate(v):
            if len(insight.strip()) < 10:
                raise ValueError(f"insights[{i}] is too short")
        return [s.strip() for s in v]

    @field_validator("opportunities", "risks")
    @classmethod
    def validate_opps_risks(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if len(s.strip()) >= 10]

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        if not (2 <= len(v) <= 4):
            raise ValueError(f"tags must have 2-4 items, got {len(v)}")
        return [s.strip().lower() for s in v]

    @field_validator("balance", "trend_summary")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class OHLCPoint(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None

class NewsHeadline(BaseModel):
    title: str
    source: str
    published_at: Optional[str] = None
    url: Optional[str] = None


class NewsSentimentData(BaseModel):
    headlines: list[NewsHeadline] = Field(default_factory=list)
    sentiment: SentimentLabel = "neutral"
    article_count: int = 0
    source_used: Optional[str] = None

class OnChainData(BaseModel):
    chain_tvl_usd: Optional[float] = None
    chain_tvl_7d_change_pct: Optional[float] = None
    protocol_tvl_usd: Optional[float] = None
    active_addresses_24h: Optional[float] = None
    exchange_netflow_24h_usd: Optional[float] = None
    data_sources: list[str] = Field(default_factory=list)

class FundamentalsData(BaseModel):
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    dividend_yield_pct: Optional[float] = None
    price_to_sales: Optional[float] = None
    enterprise_value: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    period: Optional[str] = None
    fiscal_year: Optional[str] = None

class AnalystRatingsData(BaseModel):
    consensus_rating: Optional[str] = None
    buy_count: Optional[int] = None
    hold_count: Optional[int] = None
    sell_count: Optional[int] = None
    total_analysts: Optional[int] = None
    target_price_consensus: Optional[float] = None
    target_price_high: Optional[float] = None
    target_price_low: Optional[float] = None
    recent_upgrades: Optional[int] = None
    recent_downgrades: Optional[int] = None

class CryptoData(BaseModel):
    name: str
    symbol: str
    current_price: Optional[float] = None
    price_change_24h: Optional[float] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    last_updated: Optional[str] = None
    coin_id: Optional[str] = None
    ohlc_1d: list[dict] = Field(default_factory=list)
    ohlc_7d: list[dict] = Field(default_factory=list)
    ohlc_30d: list[dict] = Field(default_factory=list)
    ohlc_1y: list[dict] = Field(default_factory=list)
    ohlc_5y: list[dict] = Field(default_factory=list)
    news_sentiment: Optional[NewsSentimentData] = None
    onchain: Optional[OnChainData] = None


class StockData(BaseModel):
    ticker: str
    name: str
    current_price: Optional[float] = None
    price_change_24h: Optional[float] = None
    market_cap: Optional[float] = None
    volume: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    pe_ratio: Optional[float] = None
    last_updated: Optional[str] = None
    ohlc_1d: list[dict] = Field(default_factory=list)
    ohlc_7d: list[dict] = Field(default_factory=list)
    ohlc_30d: list[dict] = Field(default_factory=list)
    ohlc_1y: list[dict] = Field(default_factory=list)
    ohlc_5y: list[dict] = Field(default_factory=list)
    news_sentiment: Optional[NewsSentimentData] = None
    fundamentals: Optional[FundamentalsData] = None
    analyst_ratings: Optional[AnalystRatingsData] = None


class TavilyResult(BaseModel):
    title: str
    url: str
    content: str
    published_date: Optional[str] = None


class WebData(BaseModel):
    query: str
    results: list[TavilyResult] = Field(default_factory=list)
    answer: Optional[str] = None
    news_sentiment: Optional[NewsSentimentData] = None


class MarketData(BaseModel):
    category: str
    topic: str
    primary_data: Any
    data_source: str
    fetched_at: str
    partial: bool = False
    data_confidence: float = 0.5  # 0.0–1.0, computed by aggregator


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, strip_whitespace=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    detail: Optional[Any] = None


class ClassificationResult(BaseModel):
    category: CategoryType
    confidence: float
    source: ClassifierSourceType
    keywords: list[str] = Field(default_factory=list)

class ResultData(BaseModel):
    balance: str
    trend_summary: str
    insights: list[str]
    opportunities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[FinalRecommendation] = Field(default_factory=list)
    tags: list[str]


class MetricCards(BaseModel):
    name: Optional[str] = None
    ticker: Optional[str] = None
    symbol: Optional[str] = None
    current_price: Optional[float] = None
    price_change_24h: Optional[float] = None
    market_cap: Optional[float] = None
    volume: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    pe_ratio: Optional[float] = None
    analyst_consensus: Optional[str] = None
    analyst_target_price: Optional[float] = None
    analyst_total: Optional[int] = None


class ChartData(BaseModel):
    ohlc_1d: list[dict] = Field(default_factory=list)
    ohlc_7d: list[dict] = Field(default_factory=list)
    ohlc_30d: list[dict] = Field(default_factory=list)
    ohlc_1y: list[dict] = Field(default_factory=list)
    ohlc_5y: list[dict] = Field(default_factory=list)


class EnrichmentPanel(BaseModel):
    news: Optional[NewsSentimentData] = None
    onchain: Optional[OnChainData] = None
    fundamentals: Optional[FundamentalsData] = None
    analyst_ratings: Optional[AnalystRatingsData] = None
