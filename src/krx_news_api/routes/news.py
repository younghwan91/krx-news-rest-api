from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from redis.exceptions import RedisError

from krx_news_api.models.schemas import (
    CrawlerStatus,
    NewsSource,
    PaginatedResponse,
)
from krx_news_api.services.cache import (
    get_all_crawler_status,
    get_articles,
    get_disclosures,
    search_articles,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")


@router.get("/news", response_model=PaginatedResponse)
async def list_news(
    source: NewsSource | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """최신 뉴스 목록 조회. 소스별 필터 가능."""
    try:
        articles, total = await get_articles(source=source, page=page, page_size=page_size)
        return PaginatedResponse(
            items=articles,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception:
        logger.exception("Unexpected error in list_news")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/news/search", response_model=PaginatedResponse)
async def search_news(
    q: str = Query(..., min_length=1, description="검색 키워드"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """키워드로 뉴스 검색."""
    try:
        articles, total = await search_articles(query=q, page=page, page_size=page_size)
        return PaginatedResponse(
            items=articles,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception:
        logger.exception("Unexpected error in search_news")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/news/{source}", response_model=PaginatedResponse)
async def list_news_by_source(
    source: NewsSource,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """특정 소스의 뉴스 목록 조회."""
    try:
        articles, total = await get_articles(source=source, page=page, page_size=page_size)
        return PaginatedResponse(
            items=articles,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception:
        logger.exception("Unexpected error in list_news_by_source")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/disclosure", response_model=PaginatedResponse)
async def list_disclosures(
    source: NewsSource | None = None,
    ticker: str | None = Query(None, description="종목코드 (e.g. 005930)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """공시 목록 조회. 소스/종목별 필터 가능."""
    try:
        disclosures, total = await get_disclosures(
            source=source, ticker=ticker, page=page, page_size=page_size
        )
        return PaginatedResponse(
            items=disclosures,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception:
        logger.exception("Unexpected error in list_disclosures")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/disclosure/{ticker}", response_model=PaginatedResponse)
async def list_disclosures_by_ticker(
    ticker: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """특정 종목의 공시 목록."""
    try:
        disclosures, total = await get_disclosures(
            ticker=ticker, page=page, page_size=page_size
        )
        return PaginatedResponse(
            items=disclosures,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception:
        logger.exception("Unexpected error in list_disclosures_by_ticker")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status", response_model=list[CrawlerStatus])
async def crawler_status():
    """크롤러 상태 확인."""
    try:
        return await get_all_crawler_status()
    except RedisError:
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    except Exception:
        logger.exception("Unexpected error in crawler_status")
        raise HTTPException(status_code=500, detail="Internal server error")
