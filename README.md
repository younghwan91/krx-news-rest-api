# KRX News REST API

한국 주식시장 뉴스와 공시 정보를 다양한 매체에서 자동 수집하여 제공하는 REST API입니다.

백그라운드 스케줄러가 주기적으로 뉴스를 크롤링하여 Redis에 캐싱하고, API 요청 시 캐시에서 즉시 응답하는 **캐시 우선(cache-first)** 아키텍처로 설계되었습니다.

## 주요 기능

- 📰 **5개 뉴스/공시 소스** 자동 수집 (KIND, DART, 네이버 금융, 한국경제, 더벨)
- ⚡ **저지연 응답** — Redis 캐시에서 즉시 조회
- 🔄 **백그라운드 크롤링** — 공시 60초, 뉴스 5분 간격 자동 갱신
- 🔍 **키워드/종목 검색** 지원
- 📊 **크롤러 상태 모니터링** 엔드포인트 제공

## 빠른 시작

### Docker로 실행 (권장)

```bash
cp .env.example .env          # 환경변수 설정 (DART_API_KEY 등)
docker compose up -d           # API 서버 + Redis 시작
curl http://localhost:8000/health
```

### 로컬 개발 환경

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Redis 실행 (Docker)
docker compose up -d redis

# 개발 서버 실행
uvicorn krx_news_api.main:app --reload
```

## API 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /api/v1/news` | 전체 뉴스 목록 (페이지네이션, 소스 필터) |
| `GET /api/v1/news/search?q=삼성전자` | 키워드 검색 |
| `GET /api/v1/news/{source}` | 소스별 뉴스 조회 (`naver`, `hankyung`, `thebell`) |
| `GET /api/v1/disclosure` | 공시 목록 (KIND + DART) |
| `GET /api/v1/disclosure/{ticker}` | 종목별 공시 (예: `005930`) |
| `GET /api/v1/status` | 크롤러 상태 모니터링 |
| `GET /health` | 헬스체크 |

### 요청 예시

```bash
# 최신 뉴스 20건 조회
curl "http://localhost:8000/api/v1/news?page=1&page_size=20"

# 삼성전자 관련 뉴스 검색
curl "http://localhost:8000/api/v1/news/search?q=삼성전자"

# 네이버 금융 뉴스만 조회
curl "http://localhost:8000/api/v1/news/naver"

# 삼성전자 공시 조회
curl "http://localhost:8000/api/v1/disclosure/005930"

# 크롤러 상태 확인
curl "http://localhost:8000/api/v1/status"
```

## 뉴스 소스

| 소스 | 유형 | 수집 주기 | 설명 |
|-----|------|----------|------|
| **KIND** | 공시 | 60초 | 한국거래소 기업공시 (kind.krx.co.kr) |
| **DART** | 공시 | 60초 | 금융감독원 전자공시 (dart.fss.or.kr) |
| **네이버 금융** | 뉴스 | 5분 | 시황/전망, 종목분석, 공시 뉴스 |
| **한국경제** | 뉴스 | 5분 | 증권, 경제, 마켓 섹션 |
| **더벨** | 뉴스 | 5분 | 금융 심층 분석 기사 |

## 아키텍처

```
┌──────────────────────────────────────────────────────┐
│                    FastAPI 서버                        │
│                                                       │
│   클라이언트 ──→ Routes ──→ Cache Service ──→ Redis    │
│                                                ↑      │
│   APScheduler ──→ Scrapers ──→ Cache Service ──┘      │
│                                                       │
│   KIND ┐                                              │
│   DART ├── BaseScraper ──→ Redis 저장                  │
│   네이버 ┤                                             │
│   한경  ┤                                              │
│   더벨  ┘                                              │
└──────────────────────────────────────────────────────┘
```

## 환경변수

`.env` 파일 또는 환경변수로 설정합니다. `.env.example`을 참고하세요.

| 변수 | 기본값 | 설명 |
|-----|-------|------|
| `REDIS_URL` | `redis://localhost:6379` | Redis 연결 URL |
| `DART_API_KEY` | — | DART Open API 키 ([발급](https://opendart.fss.or.kr)) |
| `CRAWL_INTERVAL_NEWS` | `300` | 뉴스 크롤링 주기 (초) |
| `CRAWL_INTERVAL_DISCLOSURE` | `60` | 공시 크롤링 주기 (초) |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |
| `CORS_ORIGINS` | `["*"]` | CORS 허용 origin 목록 |

## 개발

```bash
# 전체 테스트
pytest

# 단일 테스트 실행
pytest tests/test_api.py::test_health -v

# 린트
ruff check src/ tests/

# 포맷팅
ruff format src/ tests/
```

## 라이선스

MIT
