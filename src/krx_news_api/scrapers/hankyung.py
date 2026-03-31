"""한국경제(Hankyung) 뉴스 스크레이퍼."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from krx_news_api.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_api.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

_SECTIONS: list[tuple[str, NewsCategory]] = [
    ("/stock", NewsCategory.STOCK),
    ("/economy", NewsCategory.ECONOMY),
    ("/finance/market", NewsCategory.MARKET),
]


class HankyungScraper(BaseScraper):
    """한국경제 증권·경제·마켓 뉴스 스크레이퍼."""

    source = NewsSource.HANKYUNG
    base_url = "https://www.hankyung.com"
    min_delay = 0.8
    max_delay = 1.5

    async def scrape_news(self) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for path, category in _SECTIONS:
            try:
                section_articles = await self._scrape_section(path, category)
                articles.extend(section_articles)
                logger.info(
                    "Hankyung %s: collected %d articles",
                    path,
                    len(section_articles),
                )
            except Exception:
                logger.exception("Hankyung %s: failed to scrape", path)
        return articles

    async def _scrape_section(
        self,
        path: str,
        category: NewsCategory,
    ) -> list[NewsArticle]:
        """Try JSON API first, fall back to HTML scraping."""
        # The API category slug is the last segment of the path.
        api_category = path.strip("/").split("/")[-1]
        try:
            return await self._scrape_section_api(api_category, category)
        except Exception:
            logger.debug(
                "Hankyung API unavailable for %s, falling back to HTML",
                path,
            )
            return await self._scrape_section_html(path, category)

    # ------------------------------------------------------------------
    # JSON API approach
    # ------------------------------------------------------------------

    async def _scrape_section_api(
        self,
        api_category: str,
        category: NewsCategory,
    ) -> list[NewsArticle]:
        url = (
            f"{self.base_url}/api/v1/article/list"
            f"?category={api_category}&page=1&limit=20"
        )
        resp = await self.fetch(url)
        data = resp.json()

        raw_articles: list[dict] = []
        if isinstance(data, list):
            raw_articles = data
        elif isinstance(data, dict):
            raw_articles = (
                data.get("data")
                or data.get("articles")
                or data.get("items")
                or data.get("list")
                or []
            )
        if not raw_articles:
            raise ValueError("Empty or unrecognised API response")

        articles: list[NewsArticle] = []
        for item in raw_articles:
            title = (
                item.get("title") or item.get("headline") or ""
            ).strip()
            article_url = item.get("url") or item.get("link") or ""
            if not title or not article_url:
                continue
            if not article_url.startswith("http"):
                article_url = f"{self.base_url}{article_url}"

            summary = (
                item.get("summary")
                or item.get("lead")
                or item.get("description")
                or ""
            ).strip()
            author = (item.get("author") or item.get("writer") or "").strip()
            published_at = self._parse_datetime(
                item.get("published_at")
                or item.get("publishedAt")
                or item.get("date")
                or item.get("created_at")
            )

            articles.append(
                self._make_article(
                    title=title,
                    url=article_url,
                    category=category,
                    summary=summary,
                    author=author,
                    published_at=published_at,
                )
            )
        return articles

    # ------------------------------------------------------------------
    # HTML scraping fallback
    # ------------------------------------------------------------------

    async def _scrape_section_html(
        self,
        path: str,
        category: NewsCategory,
    ) -> list[NewsArticle]:
        url = f"{self.base_url}{path}"
        resp = await self.fetch(url)
        soup = BeautifulSoup(resp.text, "lxml")

        articles: list[NewsArticle] = []
        seen_urls: set[str] = set()

        # Hankyung uses several list layouts; try common selectors.
        items = (
            soup.select("ul.news_list li")
            or soup.select("div.news_item")
            or soup.select("div.article-list-content div.article-item")
            or soup.select("div.list_basic li")
            or soup.select("div.news-list div.news-item")
        )

        if items:
            for item in items:
                article = self._parse_list_item(item, category, seen_urls)
                if article:
                    articles.append(article)
        else:
            # Generic fallback: look for any <a> with an article-like href.
            articles.extend(
                self._extract_article_links(soup, category, seen_urls)
            )

        return articles

    def _parse_list_item(
        self,
        item: BeautifulSoup,
        category: NewsCategory,
        seen_urls: set[str],
    ) -> NewsArticle | None:
        link_tag = item.select_one("a[href]")
        if link_tag is None:
            return None

        article_url = link_tag["href"]
        if not article_url.startswith("http"):
            article_url = f"{self.base_url}{article_url}"
        if article_url in seen_urls:
            return None
        seen_urls.add(article_url)

        # Title: dedicated element first, then link text.
        title_tag = item.select_one(
            "h2, h3, .tit, .news_tit, .article-title, .title"
        )
        title = (
            (title_tag.get_text(strip=True) if title_tag else None)
            or link_tag.get_text(strip=True)
        )
        if not title:
            return None

        # Summary / lead text
        summary_tag = item.select_one(
            ".lead, .summary, .desc, .news_txt, .article-summary, p"
        )
        summary = summary_tag.get_text(strip=True) if summary_tag else ""

        # Date
        date_tag = item.select_one(
            ".date, .time, .txt_time, .article-date, time"
        )
        date_text = (
            date_tag.get("datetime")
            or date_tag.get_text(strip=True)
            if date_tag
            else ""
        )
        published_at = self._parse_datetime(date_text)

        return self._make_article(
            title=title,
            url=article_url,
            category=category,
            summary=summary,
            published_at=published_at,
        )

    def _extract_article_links(
        self,
        soup: BeautifulSoup,
        category: NewsCategory,
        seen_urls: set[str],
    ) -> list[NewsArticle]:
        """Last-resort extraction of article links from the page."""
        articles: list[NewsArticle] = []
        article_pattern = re.compile(
            r"^https?://www\.hankyung\.com/article/\d+",
        )
        for a_tag in soup.select("a[href]"):
            href: str = a_tag["href"]
            if not href.startswith("http"):
                href = f"{self.base_url}{href}"
            if not article_pattern.match(href):
                continue
            if href in seen_urls:
                continue
            seen_urls.add(href)

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            articles.append(
                self._make_article(
                    title=title,
                    url=href,
                    category=category,
                )
            )
        return articles

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        value = value.strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y.%m.%d",
            "%Y-%m-%d",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None
