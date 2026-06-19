import logging
from typing import Optional

from tavily import AsyncTavilyClient

from app.core.config import settings
from app.schemas.research import WebData, TavilyResult

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 500
MAX_RESULTS = 6


async def fetch_web(query: str) -> WebData:
    if not settings.tavily_api_key:
        raise ValueError("TAVILY_API_KEY is not configured")

    client = AsyncTavilyClient(api_key=settings.tavily_api_key)

    try:
        response = await client.search(
            query=query,
            search_depth="advanced",
            max_results=MAX_RESULTS,
            include_answer=True,
            include_raw_content=False,
        )

        raw_results = response.get("results", [])
        if not raw_results:
            raise ValueError(f"Tavily returned no results for query: '{query}'")

        results = []
        for item in raw_results:
            content = item.get("content", "")
            # Truncate content to 500 chars per spec
            if len(content) > MAX_CONTENT_CHARS:
                content = content[:MAX_CONTENT_CHARS].rsplit(" ", 1)[0] + "..."

            results.append(TavilyResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=content,
                published_date=item.get("published_date"),
            ))

        answer: Optional[str] = response.get("answer")

        logger.info(f"Tavily returned {len(results)} results for query='{query}'")

        return WebData(
            query=query,
            results=results,
            answer=answer,
        )

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Tavily fetch failed for query='{query}': {e}")
        raise ValueError(f"Tavily API error: {e}")
