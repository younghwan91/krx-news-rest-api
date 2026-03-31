"""종목 알림 예제.

관심 종목의 뉴스/공시를 감시하고 새 항목이 발견되면 알림을 출력합니다.
실제 서비스에서는 Slack, Telegram, Discord 웹훅으로 교체하세요.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

BASE_URL = "http://localhost:8000/api/v1"


@dataclass
class WatchItem:
    name: str
    ticker: str
    keywords: list[str] = field(default_factory=list)


# 관심 종목 설정
WATCHLIST: list[WatchItem] = [
    WatchItem(name="삼성전자", ticker="005930", keywords=["삼성전자", "삼성", "반도체"]),
    WatchItem(name="SK하이닉스", ticker="000660", keywords=["SK하이닉스", "하이닉스", "HBM"]),
    WatchItem(name="LG에너지솔루션", ticker="373220", keywords=["LG에너지", "배터리", "2차전지"]),
    WatchItem(name="현대차", ticker="005380", keywords=["현대차", "현대자동차", "전기차"]),
    WatchItem(name="NAVER", ticker="035420", keywords=["네이버", "NAVER", "AI"]),
]


async def check_disclosures(client: httpx.AsyncClient, item: WatchItem) -> list[dict]:
    """종목 공시 확인."""
    resp = await client.get(f"/disclosure/{item.ticker}", params={"page_size": 5})
    if resp.status_code == 200:
        return resp.json().get("items", [])
    return []


async def check_news(client: httpx.AsyncClient, item: WatchItem) -> list[dict]:
    """종목 관련 뉴스 검색."""
    all_results = []
    for kw in item.keywords:
        resp = await client.get("/news/search", params={"q": kw, "page_size": 5})
        if resp.status_code == 200:
            all_results.extend(resp.json().get("items", []))

    # 중복 제거
    seen = set()
    unique = []
    for article in all_results:
        if article["id"] not in seen:
            seen.add(article["id"])
            unique.append(article)
    return unique


def send_alert(item_name: str, alert_type: str, title: str, url: str) -> None:
    """알림 전송 (콘솔 출력). 실제로는 Slack/Telegram 웹훅으로 교체."""
    emoji = "📋" if alert_type == "공시" else "📰"
    print(f"{emoji} [{item_name}] {alert_type}: {title}")
    print(f"   🔗 {url}\n")


async def run_alert_loop(interval: int = 60) -> None:
    """메인 감시 루프."""
    seen_ids: set[str] = set()
    names = ", ".join(w.name for w in WATCHLIST)
    print(f"📡 종목 알림 시작: {names}")
    print(f"   갱신 주기: {interval}초 | Ctrl+C로 종료\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10) as client:
        while True:
            for item in WATCHLIST:
                try:
                    # 공시 확인
                    disclosures = await check_disclosures(client, item)
                    for d in disclosures:
                        if d["id"] not in seen_ids:
                            seen_ids.add(d["id"])
                            send_alert(item.name, "공시", d["title"], d["url"])

                    # 뉴스 확인
                    news = await check_news(client, item)
                    for n in news:
                        if n["id"] not in seen_ids:
                            seen_ids.add(n["id"])
                            send_alert(item.name, "뉴스", n["title"], n["url"])

                except httpx.HTTPError as e:
                    print(f"⚠️  {item.name} 조회 실패: {e}")

            await asyncio.sleep(interval)


if __name__ == "__main__":
    try:
        asyncio.run(run_alert_loop(interval=60))
    except KeyboardInterrupt:
        print("\n종목 알림 종료.")
