from __future__ import annotations

from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
async def mock_redis():
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with (
        patch("krx_news_api.services.cache.get_redis", return_value=fake),
        patch("krx_news_api.services.cache._redis", fake),
    ):
        yield fake
    await fake.aclose()


@pytest.fixture(autouse=True)
def mock_scheduler():
    with (
        patch(
            "krx_news_api.services.scheduler.crawl_all_news",
            new_callable=AsyncMock,
        ),
        patch(
            "krx_news_api.services.scheduler.crawl_all_disclosures",
            new_callable=AsyncMock,
        ),
        patch("krx_news_api.services.scheduler.start_scheduler"),
        patch("krx_news_api.services.scheduler.stop_scheduler"),
        patch("krx_news_api.main.crawl_all_news", new_callable=AsyncMock),
        patch("krx_news_api.main.crawl_all_disclosures", new_callable=AsyncMock),
        patch("krx_news_api.main.start_scheduler"),
        patch("krx_news_api.main.stop_scheduler"),
        patch("krx_news_api.main.close_redis", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture
async def client():
    from krx_news_api.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
