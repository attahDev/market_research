import json
import logging
import string
from typing import Optional

from groq import AsyncGroq

from app.core.config import settings
from app.schemas.research import ClassificationResult

logger = logging.getLogger(__name__)

try:
    import spacy
    _SPACY_AVAILABLE = True
except ImportError:
    spacy = None  # type: ignore
    _SPACY_AVAILABLE = False
    logger.warning(
        "spaCy not installed — using keyword-only classification. "
        "Run: pip install spacy && python -m spacy download en_core_web_md"
    )

_nlp = None


def _get_nlp():
    global _nlp
    if not _SPACY_AVAILABLE:
        return None
    if _nlp is None:
        logger.info("Loading spaCy model en_core_web_md...")
        _nlp = spacy.load("en_core_web_md")
        logger.info("spaCy model loaded")
    return _nlp

CRYPTO_KEYWORDS = {
    "bitcoin", "btc", "ethereum", "eth", "crypto", "cryptocurrency",
    "blockchain", "defi", "nft", "altcoin", "solana", "sol", "cardano",
    "ada", "ripple", "xrp", "dogecoin", "doge", "binance", "bnb",
    "litecoin", "ltc", "polygon", "matic", "avalanche", "avax", "coin",
    "token", "web3", "mining", "staking", "wallet", "hodl",
    "btc-usd", "eth-usd", "sol-usd", "bnb-usd", "xrp-usd",
}

STOCK_KEYWORDS = {
    "stock", "stocks", "equity", "share", "shares", "nasdaq", "nyse",
    "s&p", "sp500", "dow", "earnings", "ipo", "dividend", "portfolio",
    "ticker", "apple", "aapl", "microsoft", "msft", "google", "googl",
    "amazon", "amzn", "tesla", "tsla", "nvidia", "nvda", "meta",
    "pe ratio", "market cap", "bull market", "bear market", "short selling",
}

COMMODITY_KEYWORDS = {
    "gold", "silver", "oil", "crude", "brent", "wti", "natural gas",
    "copper", "platinum", "palladium", "wheat", "corn", "soybean",
    "coffee", "sugar", "cotton", "lumber", "commodity", "commodities",
    "futures", "spot price", "iron ore",
    "gc=f", "si=f", "cl=f", "ng=f", "hg=f", "pl=f", "pa=f",
}

INDUSTRY_KEYWORDS = {
    "industry", "sector", "market", "fintech", "saas", "startup",
    "enterprise", "b2b", "b2c", "ecommerce", "retail", "healthcare",
    "pharma", "biotech", "automotive", "real estate", "manufacturing",
    "logistics", "supply chain", "ai market", "cloud computing",
    "semiconductor", "renewable energy", "ev market", "electric vehicle",
}

_ALL_KEYWORD_SETS = {
    "crypto":    CRYPTO_KEYWORDS,
    "stock":     STOCK_KEYWORDS,
    "commodity": COMMODITY_KEYWORDS,
    "industry":  INDUSTRY_KEYWORDS,
}

def normalize_query(query: str) -> str:
    q = query.lower().strip()
    q = q.translate(str.maketrans("", "", string.punctuation))
    return " ".join(q.split())

def _keyword_classify(query_lower: str) -> tuple[Optional[str], float]:
    words = set(query_lower.split())
    scores: dict[str, float] = {
        cat: float(len(words & kws))
        for cat, kws in _ALL_KEYWORD_SETS.items()
    }

    for cat, kws in _ALL_KEYWORD_SETS.items():
        for kw in kws:
            if " " in kw and kw in query_lower:
                scores[cat] += 1.5

    best_cat = max(scores, key=lambda k: scores[k])
    best_score = scores[best_cat]
    if best_score == 0:
        return None, 0.0

    total = sum(scores.values())
    non_zero = sum(1 for v in scores.values() if v > 0)
    if non_zero == 1:
        confidence = 0.92
    else:
        confidence = min((best_score / total) + 0.2, 0.95) if total > 0 else 0.0

    return best_cat, confidence

def _spacy_classify(query: str) -> tuple[Optional[str], float]:
    nlp = _get_nlp()
    if nlp is None:
        return _keyword_classify(query.lower())

    doc = nlp(query)
    entity_labels = {ent.label_ for ent in doc.ents}
    query_lower = query.lower()

    boosts: dict[str, float] = {cat: 0.0 for cat in _ALL_KEYWORD_SETS}
    if {"MONEY", "PERCENT"} & entity_labels:
        boosts["stock"] += 0.1
    if "ORG" in entity_labels:
        boosts["stock"]    += 0.05
        boosts["industry"] += 0.05
    if "PRODUCT" in entity_labels:
        boosts["crypto"] += 0.05

    kw_cat, kw_conf = _keyword_classify(query_lower)
    if kw_cat:
        return kw_cat, min(kw_conf + boosts.get(kw_cat, 0.0), 0.98)
    return None, 0.0

async def _groq_classify(query: str) -> tuple[Optional[str], list[str]]:
    client = AsyncGroq(api_key=settings.groq_api_key)
    prompt = f"""Classify the following market research query into exactly one category.

Query: "{query}"

Categories:
- crypto: cryptocurrencies, blockchain, DeFi, NFTs, coins/tokens
- stock: equities, shares, companies, stock indices, earnings
- commodity: physical goods like gold, oil, natural gas, agricultural products
- industry: business sectors, market trends, competitive landscapes
- general: anything else

Return ONLY valid JSON, no markdown:
{{"category": "crypto|stock|commodity|industry|general", "confidence": 0.9, "keywords": ["kw1", "kw2"]}}"""

    try:
        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        category = data.get("category", "general")
        if category not in _ALL_KEYWORD_SETS and category != "general":
            category = "general"
        return category, data.get("keywords", [])
    except Exception as e:
        logger.warning(f"Groq classification failed: {e}")
        return None, []

async def classify_query(query: str) -> ClassificationResult:
    spacy_cat, spacy_conf = _spacy_classify(query)
    logger.info(f"Keyword/spaCy result: category={spacy_cat} confidence={spacy_conf:.3f}")

    if spacy_cat and spacy_conf >= settings.classifier_confidence_threshold:
        return ClassificationResult(
            category=spacy_cat,
            confidence=spacy_conf,
            source="spacy",
            keywords=[],
        )

    logger.info(
        f"Confidence {spacy_conf:.3f} below threshold "
        f"({settings.classifier_confidence_threshold}), trying Groq..."
    )

    last_keywords: list[str] = []
    for attempt in range(settings.classifier_max_groq_retries):
        groq_cat, keywords = await _groq_classify(query)
        if groq_cat:
            logger.info(f"Groq classified as '{groq_cat}' (attempt {attempt + 1})")
            return ClassificationResult(
                category=groq_cat,
                confidence=0.85,
                source="groq",
                keywords=keywords,
            )
        logger.warning(f"Groq attempt {attempt + 1} failed")
        last_keywords = keywords

    fallback = spacy_cat or "general"
    logger.warning(f"All classification attempts exhausted — falling back to '{fallback}'")
    return ClassificationResult(
        category=fallback,
        confidence=0.0,
        source="groq",
        keywords=last_keywords,
    )
