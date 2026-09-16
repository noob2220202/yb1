"""API-Football(API-Sports) v3 클라이언트.

주의: 이 클라이언트는 API-Football v3의 공식 문서 구조를 기반으로 작성됐다.
실제 API 키가 준비되면 `scripts/inspect_api_response.py`를 한 번 실행해
실제 응답 구조를 캡처하고, `app/services/market_type_mapping.py`의 매핑표를
검증/보정할 것 (SPEC.md 5.2절 요구사항).
"""
from __future__ import annotations

import logging
import time
from datetime import date

import httpx

from app.config import settings

logger = logging.getLogger("oddsapp.odds_api_client")

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0


class ApiFootballError(RuntimeError):
    pass


class OddsApiClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.api_football_key
        self.base_url = base_url or settings.api_football_base_url

    def _headers(self) -> dict:
        return {"x-apisports-key": self.api_key}

    def _get(self, path: str, params: dict) -> dict:
        if not self.api_key:
            raise ApiFootballError(
                "API_FOOTBALL_KEY가 설정되지 않았습니다. .env에 키를 추가하세요."
            )

        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = httpx.get(url, params=params, headers=self._headers(), timeout=15.0)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise ApiFootballError(f"일시적 오류 (status={resp.status_code})")
                resp.raise_for_status()
                data = resp.json()
                if data.get("errors"):
                    raise ApiFootballError(f"API 오류: {data['errors']}")
                return data
            except (httpx.HTTPError, ApiFootballError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    sleep_s = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "API-Football 요청 실패(%s/%s), %.1fs 후 재시도: %s",
                        attempt,
                        MAX_RETRIES,
                        sleep_s,
                        exc,
                    )
                    time.sleep(sleep_s)
                else:
                    logger.error("API-Football 요청 최종 실패, 스킵: %s", exc)
        assert last_exc is not None
        raise last_exc

    def get_fixtures_between(self, date_from: date, date_to: date) -> list[dict]:
        """지정 기간의 예정 경기 목록 조회 (status=NS, 프리매치).

        API-Football은 /fixtures?from=&to=&status=NS 형태를 지원한다.
        """
        data = self._get(
            "/fixtures",
            {
                "from": date_from.isoformat(),
                "to": date_to.isoformat(),
                "status": "NS",
            },
        )
        return data.get("response", [])

    def get_odds_for_fixture(self, fixture_external_id: str) -> list[dict]:
        """특정 fixture의 북메이커 오즈 조회 (/odds?fixture=)."""
        data = self._get("/odds", {"fixture": fixture_external_id})
        return data.get("response", [])
