
import logging
from typing import Optional

import httpx

from app.schemas.research import OnChainData

logger = logging.getLogger(__name__)

DEFILLAMA_CHAIN_URL    = "https://api.llama.fi/v2/historicalChainTvl/{chain}"
DEFILLAMA_PROTOCOL_URL = "https://api.llama.fi/tvl/{protocol}"
GLASSNODE_BASE         = "https://api.glassnode.com/v1/metrics"

CHAIN_MAP: dict[str, tuple[str, Optional[str]]] = {
    "bitcoin":   ("bitcoin",  None),
    "btc":       ("bitcoin",  None),
    "ethereum":  ("ethereum", "ethereum"),
    "eth":       ("ethereum", "ethereum"),
    "solana":    ("solana",   "solana"),
    "sol":       ("solana",   "solana"),
    "avalanche": ("avax",     "avalanche"),
    "avax":      ("avax",     "avalanche"),
    "polygon":   ("polygon",  "polygon"),
    "matic":     ("polygon",  "polygon"),
    "bnb":       ("bsc",      "pancakeswap"),
    "binance":   ("bsc",      "pancakeswap"),
    "cardano":   ("cardano",  None),
    "ada":       ("cardano",  None),
}

GLASSNODE_ASSET_MAP: dict[str, str] = {
    "bitcoin":  "BTC",
    "btc":      "BTC",
    "ethereum": "ETH",
    "eth":      "ETH",
    "litecoin": "LTC",
    "ltc":      "LTC",
}


def _resolve(coin_id: str) -> tuple[Optional[str], Optional[str]]:
    key = coin_id.lower()
    if key in CHAIN_MAP:
        return CHAIN_MAP[key]
    for k, v in CHAIN_MAP.items():
        if k in key or key in k:
            return v
    return None, None


async def _defillama_tvl(chain: str, protocol: Optional[str], client: httpx.AsyncClient) -> dict:
    result: dict = {}

    try:
        resp = await client.get(DEFILLAMA_CHAIN_URL.format(chain=chain), timeout=10.0)
        resp.raise_for_status()
        history = resp.json()
        if history and isinstance(history, list):
            tvl_now   = history[-1].get("tvl")
            tvl_7d    = history[-7].get("tvl") if len(history) >= 7 else history[0].get("tvl")
            result["chain_tvl_usd"] = tvl_now
            if tvl_now and tvl_7d and tvl_7d > 0:
                result["chain_tvl_7d_change_pct"] = round(
                    (tvl_now - tvl_7d) / tvl_7d * 100, 2
                )
    except Exception as e:
        logger.debug(f"DefiLlama chain TVL failed ({chain}): {e}")

    if protocol:
        try:
            resp = await client.get(DEFILLAMA_PROTOCOL_URL.format(protocol=protocol), timeout=8.0)
            resp.raise_for_status()
            result["protocol_tvl_usd"] = resp.json()
        except Exception as e:
            logger.debug(f"DefiLlama protocol TVL failed ({protocol}): {e}")

    return result


async def _glassnode(asset: str, api_key: str, client: httpx.AsyncClient) -> dict:
    result: dict = {}
    params = {"a": asset, "api_key": api_key, "i": "24h", "limit": 1}

    try:
        resp = await client.get(f"{GLASSNODE_BASE}/addresses/active_count", params=params, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        if data:
            result["active_addresses_24h"] = data[-1].get("v")
    except Exception as e:
        logger.debug(f"Glassnode active addresses failed ({asset}): {e}")

    try:
        resp = await client.get(
            f"{GLASSNODE_BASE}/transactions/transfers_volume_exchanges_net",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            result["exchange_netflow_24h_usd"] = data[-1].get("v")
    except Exception as e:
        logger.debug(f"Glassnode netflow failed ({asset}): {e}")

    return result


async def fetch_onchain_data(coin_id: str) -> OnChainData:
    chain, protocol   = _resolve(coin_id)
    glassnode_asset   = GLASSNODE_ASSET_MAP.get(coin_id.lower())

    # Import here to avoid circular import; config not needed at module level
    from app.core.config import settings
    glassnode_key = getattr(settings, "glassnode_api_key", None)

    defillama_data: dict = {}
    glassnode_data: dict = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        if chain:
            defillama_data = await _defillama_tvl(chain, protocol, client)
        if glassnode_asset and glassnode_key:
            glassnode_data = await _glassnode(glassnode_asset, glassnode_key, client)

    sources = ["defillama"] + (["glassnode"] if glassnode_data else [])

    onchain = OnChainData(
        chain_tvl_usd=defillama_data.get("chain_tvl_usd"),
        chain_tvl_7d_change_pct=defillama_data.get("chain_tvl_7d_change_pct"),
        protocol_tvl_usd=defillama_data.get("protocol_tvl_usd"),
        active_addresses_24h=glassnode_data.get("active_addresses_24h"),
        exchange_netflow_24h_usd=glassnode_data.get("exchange_netflow_24h_usd"),
        data_sources=sources,
    )
    logger.info(
        f"Onchain fetched | coin={coin_id} "
        f"chain_tvl={onchain.chain_tvl_usd} "
        f"active_addr={onchain.active_addresses_24h}"
    )
    return onchain
