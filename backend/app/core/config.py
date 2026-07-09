from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = ""
    db_schema: str = "market_research"
    redis_url: str = "redis://localhost:6379/0"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    tiingo_api_key: str = ""
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    coingecko_api_key: str = ""
    newsapi_key: str = ""
    tavily_api_key: str = ""
    classifier_confidence_threshold: float = 0.75
    classifier_max_groq_retries: int = 2
    cache_ttl_crypto: int = 120
    cache_ttl_stocks: int = 300
    cache_ttl_commodity: int = 300
    cache_ttl_industry: int = 7200
    cache_ttl_general: int = 7200
    job_processing_timeout_seconds: int = 180
    job_result_expiry_seconds: int = 7200
    job_inflight_lock_seconds: int = 30
    job_max_retries: int = 2
    app_env: str = "development"
    log_level: str = "INFO"
    allowed_origins: list[str] = []

    # --- Rate limiting ---
    idempotency_key_ttl_seconds: int = 120
    rate_limit_per_minute: int = 10
    rate_limit_per_hour: int = 100
    # Set True in development to skip entitlement, rate-limit, and credit checks
    bypass_rate_limits: bool = True

    # --- Credits: main GMBTE Postgres DB (separate from this service's own DB) ---
    # SCHEMA CAVEAT: assumed shape, not yet confirmed against the real main-platform
    # schema — user_credits(user_id, credits_balance, credits_reset_at) +
    # credit_transactions(id, user_id, service, amount, status, reference_id, created_at).
    # Isolated to app/core/credits_db.py + app/services/credits_service.py so this is
    # a small change once the real schema is confirmed, not a rewrite.
    credits_database_url: str = ""

    def get_cache_ttl(self, category: str) -> int:
        return {
            "crypto":    self.cache_ttl_crypto,
            "stock":     self.cache_ttl_stocks,
            "commodity": self.cache_ttl_commodity,
            "industry":  self.cache_ttl_industry,
            "general":   self.cache_ttl_general,
        }.get(category, self.cache_ttl_general)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


# ---------------------------------------------------------------------------
# Business logic constants for market_research specifically.
# Mirrors proposal-builder's ENTITLED_PLANS pattern: Research AI is a
# Founder Workspace+ feature per the pricing doc — Student does NOT include it.
# (Student includes Career AI/CV Builder/Interview AI — not Research AI.)
# ---------------------------------------------------------------------------

SERVICE_NAME = "market_research"

ENTITLED_PLANS: set[str] = {"founder_workspace", "founder_pro", "team"}

# Cache hits cost less — no Tiingo/Tavily/Groq spend incurred.
CREDIT_COST_FRESH: int = 8
CREDIT_COST_CACHE: int = 1

# Per-plan burst limits (requests per minute) — infrastructure protection,
# independent of credit balance.
PLAN_BURST_LIMITS_PER_MINUTE: dict[str, int] = {
    "explorer":          5,
    "student":           5,
    "founder_workspace": 10,
    "founder_pro":       20,
    "team":              30,
}
