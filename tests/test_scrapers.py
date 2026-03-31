from __future__ import annotations

import pytest

from krx_news_api.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_api.scrapers.base import BaseScraper, make_article_id


class ConcreteScraper(BaseScraper):
    source = NewsSource.NAVER
    base_url = "https://example.com"

    async def scrape_news(self) -> list[NewsArticle]:
        return []


class TestMakeArticleId:
    def test_deterministic(self):
        id1 = make_article_id("naver", "https://example.com/1")
        id2 = make_article_id("naver", "https://example.com/1")
        assert id1 == id2

    def test_different_urls(self):
        id1 = make_article_id("naver", "https://example.com/1")
        id2 = make_article_id("naver", "https://example.com/2")
        assert id1 != id2

    def test_format(self):
        aid = make_article_id("kind", "https://example.com/1")
        assert aid.startswith("kind:")
        assert len(aid) == len("kind:") + 12


class TestBaseScraper:
    def test_make_article(self):
        scraper = ConcreteScraper()
        article = scraper._make_article(
            title="Test Article",
            url="https://example.com/1",
            category=NewsCategory.MARKET,
            content="Some content",
            tickers=["005930"],
        )
        assert isinstance(article, NewsArticle)
        assert article.source == NewsSource.NAVER
        assert article.title == "Test Article"
        assert article.tickers == ["005930"]

    def test_make_disclosure(self):
        scraper = ConcreteScraper()
        disc = scraper._make_disclosure(
            title="공시제목",
            url="https://example.com/disc/1",
            company="삼성전자",
            ticker="005930",
            disclosure_type="주요사항보고서",
        )
        assert disc.source == NewsSource.NAVER
        assert disc.company == "삼성전자"

    @pytest.mark.asyncio
    async def test_scrape_news_interface(self):
        scraper = ConcreteScraper()
        result = await scraper.scrape_news()
        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_disclosures_default(self):
        scraper = ConcreteScraper()
        result = await scraper.scrape_disclosures()
        assert result == []
