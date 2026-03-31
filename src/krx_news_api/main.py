from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from krx_news_api.config import settings
from krx_news_api.routes.news import router as news_router
from krx_news_api.services.cache import close_redis
from krx_news_api.services.scheduler import (
    crawl_all_disclosures,
    crawl_all_news,
    start_scheduler,
    stop_scheduler,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting KRX News API")

    # Run initial crawl at startup
    asyncio.create_task(crawl_all_disclosures())
    asyncio.create_task(crawl_all_news())

    start_scheduler()

    yield

    stop_scheduler()
    await close_redis()
    logger.info("KRX News API stopped")


app = FastAPI(
    title="KRX News REST API",
    description="한국 주식시장 뉴스 수집 REST API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        logger.info(
            "%s %s → %d (%.2fs)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)

app.include_router(news_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    return {"status": "ok"}
