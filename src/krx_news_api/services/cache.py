from __future__ import annotations

import json
import logging
from datetime import datetime

import redis.asyncio as redis

from krx_news_api.config import settings
from krx_news_api.models.schemas import CrawlerStatus, Disclosure, NewsArticle, NewsSource

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None


# --- News Cache ---

NEWS_KEY = "news:{source}"
NEWS_ALL_KEY = "news:all"
NEWS_TTL = 3600  # 1 hour
DISCLOSURE_TTL = 86400  # 24 hours
SEARCH_TTL = 300  # 5 minutes


async def cache_articles(source: NewsSource, articles: list[NewsArticle]) -> int:
    r = await get_redis()
    pipe = r.pipeline()

    serialized = [a.model_dump_json() for a in articles]

    source_key = NEWS_KEY.format(source=source.value)
    pipe.delete(source_key)
    if serialized:
        pipe.rpush(source_key, *serialized)
        pipe.expire(source_key, NEWS_TTL)

    # Also add to the combined feed (sorted set by timestamp)
    for article in articles:
        score = article.published_at.timestamp()
        pipe.zadd(NEWS_ALL_KEY, {article.model_dump_json(): score})
    pipe.expire(NEWS_ALL_KEY, NEWS_TTL)

    await pipe.execute()
    logger.info("Cached %d articles from %s", len(articles), source.value)
    return len(articles)


async def get_articles(
    source: NewsSource | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[NewsArticle], int]:
    r = await get_redis()

    if source:
        key = NEWS_KEY.format(source=source.value)
        total = await r.llen(key)
        start = (page - 1) * page_size
        end = start + page_size - 1
        raw = await r.lrange(key, start, end)
    else:
        total = await r.zcard(NEWS_ALL_KEY)
        start = (page - 1) * page_size
        end = start + page_size - 1
        raw = await r.zrevrange(NEWS_ALL_KEY, start, end)

    articles = [NewsArticle.model_validate_json(item) for item in raw]
    return articles, total


async def search_articles(
    query: str, page: int = 1, page_size: int = 20,
) -> tuple[list[NewsArticle], int]:
    """Simple keyword search across cached articles."""
    r = await get_redis()

    cache_key = f"search:{query}:{page}:{page_size}"
    cached = await r.get(cache_key)
    if cached:
        data = json.loads(cached)
        return [NewsArticle.model_validate(a) for a in data["items"]], data["total"]

    # Scan all articles for matching title/content
    all_raw = await r.zrevrange(NEWS_ALL_KEY, 0, -1)
    matched: list[NewsArticle] = []
    q_lower = query.lower()
    for raw_item in all_raw:
        article = NewsArticle.model_validate_json(raw_item)
        if q_lower in article.title.lower() or q_lower in article.content.lower():
            matched.append(article)

    total = len(matched)
    start = (page - 1) * page_size
    page_items = matched[start : start + page_size]

    # Cache search results
    cache_data = {"items": [a.model_dump(mode="json") for a in page_items], "total": total}
    await r.set(cache_key, json.dumps(cache_data, ensure_ascii=False, default=str), ex=SEARCH_TTL)

    return page_items, total


# --- Disclosure Cache ---

DISCLOSURE_KEY = "disclosure:{source}"
DISCLOSURE_ALL_KEY = "disclosure:all"


async def cache_disclosures(source: NewsSource, disclosures: list[Disclosure]) -> int:
    r = await get_redis()
    pipe = r.pipeline()

    source_key = DISCLOSURE_KEY.format(source=source.value)
    pipe.delete(source_key)

    serialized = [d.model_dump_json() for d in disclosures]
    if serialized:
        pipe.rpush(source_key, *serialized)
        pipe.expire(source_key, DISCLOSURE_TTL)

    for disc in disclosures:
        score = disc.published_at.timestamp()
        pipe.zadd(DISCLOSURE_ALL_KEY, {disc.model_dump_json(): score})
    pipe.expire(DISCLOSURE_ALL_KEY, DISCLOSURE_TTL)

    await pipe.execute()
    logger.info("Cached %d disclosures from %s", len(disclosures), source.value)
    return len(disclosures)


async def get_disclosures(
    source: NewsSource | None = None,
    ticker: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Disclosure], int]:
    r = await get_redis()

    if source:
        key = DISCLOSURE_KEY.format(source=source.value)
        raw = await r.lrange(key, 0, -1)
    else:
        raw = await r.zrevrange(DISCLOSURE_ALL_KEY, 0, -1)

    disclosures = [Disclosure.model_validate_json(item) for item in raw]

    if ticker:
        disclosures = [d for d in disclosures if d.ticker == ticker]

    total = len(disclosures)
    start = (page - 1) * page_size
    page_items = disclosures[start : start + page_size]
    return page_items, total


# --- Crawler Status ---

STATUS_KEY = "crawler:status:{source}"


async def update_crawler_status(
    source: NewsSource,
    articles_count: int = 0,
    error: str | None = None,
) -> None:
    r = await get_redis()
    status = CrawlerStatus(
        source=source,
        last_crawled_at=datetime.now(),
        articles_count=articles_count,
        is_healthy=error is None,
        error=error,
    )
    await r.set(STATUS_KEY.format(source=source.value), status.model_dump_json())


async def get_all_crawler_status() -> list[CrawlerStatus]:
    r = await get_redis()
    statuses = []
    for src in NewsSource:
        raw = await r.get(STATUS_KEY.format(source=src.value))
        if raw:
            statuses.append(CrawlerStatus.model_validate_json(raw))
        else:
            statuses.append(CrawlerStatus(source=src, is_healthy=False, error="Never crawled"))
    return statuses
