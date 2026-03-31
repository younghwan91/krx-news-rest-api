from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup

from krx_news_api.models.schemas import NewsArticle, NewsCategory, NewsSource
from krx_news_api.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# section_id3 -> NewsCategory mapping
CATEGORY_MAP: dict[str, NewsCategory] = {
    "401": NewsCategory.MARKET,      # 시황/전망
    "402": NewsCategory.STOCK,       # 종목분석/리포트
    "403": NewsCategory.DISCLOSURE,  # 공시/메모
}

NEWS_LIST_URL = (
    "https://finance.naver.com/news/news_list.naver"
    "?mode=LSS3D&section_id=101&section_id2=258"
    "&section_id3={section_id3}&page={page}"
)


class NaverScraper(BaseScraper):
    source = NewsSource.NAVER
    base_url = "https://finance.naver.com"
    min_delay = 1.0
    max_delay = 3.0

    async def scrape_news(self) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for section_id3, category in CATEGORY_MAP.items():
            try:
                page_articles = await self._scrape_category(section_id3, category)
                articles.extend(page_articles)
            except Exception:
                logger.exception(
                    "Failed to scrape Naver category %s", section_id3,
                )
        return articles

    async def _scrape_category(
        self,
        section_id3: str,
        category: NewsCategory,
        max_pages: int = 2,
    ) -> list[NewsArticle]:
        articles: list[NewsArticle] = []
        for page in range(1, max_pages + 1):
            url = NEWS_LIST_URL.format(section_id3=section_id3, page=page)
            try:
                page_articles = await self._parse_news_list(url, category)
                articles.extend(page_articles)
                if not page_articles:
                    break
            except Exception:
                logger.exception(
                    "Failed to scrape Naver page %d for section %s",
                    page,
                    section_id3,
                )
                break
        return articles

    async def _parse_news_list(
        self, url: str, category: NewsCategory,
    ) -> list[NewsArticle]:
        resp = await self.fetch(url)
        soup = BeautifulSoup(
            resp.content.decode("euc-kr", errors="replace"), "lxml",
        )

        articles: list[NewsArticle] = []
        items = soup.select("li.newsList") or soup.select("ul.realtimeNewsList li")
        if not items:
            items = soup.select(".articleSubject a, .block1 dl")

        for item in items:
            try:
                article = self._parse_item(item, category)
                if article:
                    articles.append(article)
            except Exception:
                logger.debug("Failed to parse news item", exc_info=True)

        return articles

    def _parse_item(
        self, item, category: NewsCategory,
    ) -> NewsArticle | None:
        link_tag = item.select_one("a[href]") if item.name != "a" else item
        if not link_tag or not link_tag.get("href"):
            return None

        title = (link_tag.get("title") or link_tag.get_text()).strip()
        if not title:
            return None

        href = link_tag["href"]
        article_url = href if href.startswith("http") else self.base_url + href

        summary = ""
        lead = item.select_one("p.lead")
        if lead:
            summary = lead.get_text(strip=True)

        published_at = self._parse_date(item)

        author = ""
        source_tag = item.select_one(".press, .articleSummary .info span")
        if source_tag:
            author = source_tag.get_text(strip=True)

        return self._make_article(
            title=title,
            url=article_url,
            category=category,
            summary=summary,
            author=author,
            published_at=published_at,
        )

    def _parse_date(self, item) -> datetime | None:
        wdate = item.select_one("span.wdate")
        if wdate:
            return self._str_to_datetime(wdate.get_text(strip=True))

        date_tag = item.select_one(".date, .datetime")
        if date_tag:
            return self._str_to_datetime(date_tag.get_text(strip=True))

        return None

    @staticmethod
    def _str_to_datetime(text: str) -> datetime | None:
        text = text.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y.%m.%d %H:%M"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        m = re.search(r"(\d{4})[\-./](\d{1,2})[\-./](\d{1,2})", text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        return None
