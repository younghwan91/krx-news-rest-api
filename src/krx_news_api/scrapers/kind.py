"""KIND (한국거래소 공시정보) scraper.

Collects corporate disclosure listings from https://kind.krx.co.kr.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from krx_news_api.models.schemas import Disclosure, NewsArticle, NewsSource
from krx_news_api.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

DISCLOSURE_LIST_URL = (
    "https://kind.krx.co.kr/disclosure/todaydisclosure.do"
)
DISCLOSURE_DETAIL_BASE = (
    "https://kind.krx.co.kr/disclosure/todaydisclosure.do"
)

# 6-digit ticker pattern
_TICKER_RE = re.compile(r"^[0-9A-Z]{6}$")


class KindScraper(BaseScraper):
    """Scrapes today's disclosure list from KIND (kind.krx.co.kr)."""

    source = NewsSource.KIND
    base_url = "https://kind.krx.co.kr"

    async def scrape_news(self) -> list[NewsArticle]:
        """KIND only provides disclosures, not general news."""
        return []

    async def scrape_disclosures(self) -> list[Disclosure]:
        """Fetch and parse today's disclosure list from KIND."""
        html = await self._fetch_disclosure_list()
        return self._parse_disclosures(html)

    async def _fetch_disclosure_list(self) -> str:
        """POST to the KIND disclosure search endpoint and return raw HTML."""
        resp = await self.fetch_post(
            DISCLOSURE_LIST_URL,
            data={
                "method": "searchTodayDisclosureSub",
                "currentPageSize": "100",
                "marketType": "",
                "searchType": "today",
            },
            headers={
                "Referer": "https://kind.krx.co.kr",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        return resp.text

    def _parse_disclosures(self, html: str) -> list[Disclosure]:
        """Parse the HTML table returned by KIND into Disclosure objects."""
        soup = BeautifulSoup(html, "lxml")
        rows = soup.select("table tbody tr")
        if not rows:
            # Fallback: try all <tr> that contain <td>
            rows = [tr for tr in soup.find_all("tr") if tr.find("td")]

        disclosures: list[Disclosure] = []
        today = date.today()

        for row in rows:
            try:
                disclosure = self._parse_row(row, today)
                if disclosure is not None:
                    disclosures.append(disclosure)
            except Exception:
                logger.debug("Failed to parse KIND row", exc_info=True)
                continue

        logger.info("KIND: parsed %d disclosures", len(disclosures))
        return disclosures

    def _parse_row(self, row: BeautifulSoup, today: date) -> Disclosure | None:
        """Extract a single Disclosure from a table row.

        Expected columns: 시간 | 회사명 | 보고서명 | 제출인 | ...
        """
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        # --- time ---
        time_text = cells[0].get_text(strip=True)
        published_at = self._parse_time(time_text, today)

        # --- company name & ticker ---
        company_cell = cells[1]
        company = company_cell.get_text(strip=True)

        # Ticker is often embedded in an onclick or href attribute
        ticker = self._extract_ticker(company_cell)

        # --- disclosure title & URL ---
        title_cell = cells[2]
        title_link = title_cell.find("a")
        title = title_cell.get_text(strip=True)
        url = self._build_disclosure_url(title_link)

        if not title:
            return None

        # --- disclosure type (optional, from title prefix or extra column) ---
        disclosure_type = ""
        if len(cells) >= 4:
            disclosure_type = cells[3].get_text(strip=True)

        return self._make_disclosure(
            title=title,
            url=url,
            company=company,
            ticker=ticker,
            disclosure_type=disclosure_type,
            published_at=published_at,
        )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_time(time_text: str, today: date) -> datetime:
        """Parse a time string like '14:30' into a datetime for *today*."""
        match = re.search(r"(\d{1,2}):(\d{2})", time_text)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            return datetime(today.year, today.month, today.day, hour, minute)
        return datetime(today.year, today.month, today.day)

    @staticmethod
    def _extract_ticker(cell: BeautifulSoup) -> str:
        """Try to pull a 6-character ticker from onclick/href attributes."""
        for tag in cell.find_all("a"):
            for attr in ("onclick", "href"):
                value = tag.get(attr, "")
                # Look for 6-digit stock code in the attribute
                codes = re.findall(r"[0-9A-Z]{6}", value)
                for code in codes:
                    if _TICKER_RE.match(code):
                        return code
        return ""

    def _build_disclosure_url(self, link_tag) -> str:
        """Construct full URL from an <a> tag, if available."""
        if link_tag is None:
            return self.base_url
        href = link_tag.get("href", "")
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return f"{self.base_url}{href}"
        # onclick-based navigation: extract rcpNo or similar params
        onclick = link_tag.get("onclick", "")
        doc_match = re.search(r"rcpNo=([^&'\"]+)", onclick)
        if doc_match:
            return (
                f"{self.base_url}/disclosure/todaydisclosure.do"
                f"?method=searchTodayDisclosureDetail&rcpNo={doc_match.group(1)}"
            )
        doc_match = re.search(r"'(/[^']+)'", onclick)
        if doc_match:
            return f"{self.base_url}{doc_match.group(1)}"
        return self.base_url
