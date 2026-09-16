"""오즈 수집 파이프라인.

- fixtures: external_id 기준으로 upsert (동일 경기 정보를 최신화).
- markets/odds: 항상 새 row로 insert(시계열 이력 보존). 대시보드/조합 엔진은
  각 (market_type, line, bookmaker, selection) 조합에서 가장 최근 fetched_at만
  사용한다.
- API 요청 실패는 클라이언트(OddsApiClient)가 지수 백오프로 최대 3회 재시도하고,
  그래도 실패하면 예외를 던진다 — 이 모듈에서 fixture 단위로 잡아 로그만 남기고
  스킵한다(파이프라인 전체가 죽지 않도록).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from itertools import groupby

from sqlalchemy.orm import Session

from app.clients.odds_api_client import ApiFootballError, OddsApiClient
from app.config import settings
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from app.services.market_type_mapping import normalize_bet

logger = logging.getLogger("oddsapp.ingest")

_STATUS_MAP = {"NS": "scheduled", "FT": "finished", "CANC": "cancelled", "PST": "cancelled"}


def _map_status(api_status_short: str) -> str:
    return _STATUS_MAP.get(api_status_short, "scheduled")


def upsert_fixture(db: Session, raw: dict) -> Fixture:
    fixture_data = raw["fixture"]
    league_data = raw["league"]
    teams_data = raw["teams"]

    external_id = str(fixture_data["id"])
    kickoff_utc = datetime.fromisoformat(fixture_data["date"].replace("Z", "+00:00"))

    fixture = db.query(Fixture).filter(Fixture.external_id == external_id).one_or_none()
    if fixture is None:
        fixture = Fixture(external_id=external_id)
        db.add(fixture)

    fixture.league_id = league_data["id"]
    fixture.league_name = league_data["name"]
    fixture.country = league_data.get("country")
    fixture.home_team = teams_data["home"]["name"]
    fixture.away_team = teams_data["away"]["name"]
    fixture.kickoff_utc = kickoff_utc
    fixture.status = _map_status(fixture_data.get("status", {}).get("short", "NS"))

    goals = raw.get("goals") or {}
    fixture.home_score = goals.get("home")
    fixture.away_score = goals.get("away")

    return fixture


def ingest_fixtures(db: Session, client: OddsApiClient, lookahead_hours: int | None = None) -> list[Fixture]:
    """다음 N시간 내 예정된 경기 목록을 가져와 fixtures 테이블에 upsert."""
    lookahead_hours = lookahead_hours or settings.ingest_lookahead_hours
    today = date.today()
    date_to = today + timedelta(hours=lookahead_hours)

    try:
        raw_fixtures = client.get_fixtures_between(today, date_to)
    except ApiFootballError as exc:
        logger.error("fixture 목록 조회 실패, 이번 사이클 스킵: %s", exc)
        return []

    fixtures: list[Fixture] = []
    for raw in raw_fixtures:
        try:
            fixtures.append(upsert_fixture(db, raw))
        except (KeyError, ValueError) as exc:
            logger.warning("fixture 파싱 실패, 스킵: %s (%s)", exc, raw.get("fixture", {}).get("id"))
    db.commit()
    return fixtures


def ingest_odds_for_fixture(db: Session, client: OddsApiClient, fixture: Fixture) -> int:
    """한 fixture의 최신 오즈를 가져와 markets/odds 테이블에 새 row로 insert.

    반환값: insert된 odds row 개수.
    """
    try:
        raw_odds_response = client.get_odds_for_fixture(fixture.external_id)
    except ApiFootballError as exc:
        logger.error("fixture %s 오즈 조회 실패, 스킵: %s", fixture.external_id, exc)
        return 0

    inserted = 0
    for entry in raw_odds_response:
        for bookmaker in entry.get("bookmakers", []):
            bookmaker_name = bookmaker.get("name", "unknown")
            for bet in bookmaker.get("bets", []):
                normalized = normalize_bet(bet.get("name", ""), bet.get("values", []))
                if normalized is None:
                    continue
                market_type, parsed_values = normalized

                key_fn = lambda item: item[1]  # noqa: E731 (line)
                sorted_values = sorted(parsed_values, key=lambda item: (item[1] is None, item[1]))
                for line, group in groupby(sorted_values, key=key_fn):
                    group_list = list(group)
                    market = Market(
                        fixture_id=fixture.id,
                        market_type=market_type,
                        line=line,
                        bookmaker=bookmaker_name,
                    )
                    db.add(market)
                    db.flush()  # market.id 확보

                    for selection, _line, decimal_odds in group_list:
                        db.add(
                            Odds(
                                market_id=market.id,
                                selection=selection,
                                decimal_odds=decimal_odds,
                            )
                        )
                        inserted += 1

    db.commit()
    return inserted


def run_ingest_cycle(db: Session, client: OddsApiClient | None = None, urgent_only: bool = False) -> dict:
    """전체 수집 사이클 실행.

    urgent_only=True면 이미 저장된 fixtures 중 킥오프까지 ingest_urgent_window_hours
    이내인 경기만 오즈를 재수집한다(fixture 목록 자체는 다시 가져오지 않음).
    """
    client = client or OddsApiClient()
    summary = {"fixtures_upserted": 0, "fixtures_processed": 0, "odds_inserted": 0}

    if urgent_only:
        cutoff = datetime.now(timezone.utc) + timedelta(hours=settings.ingest_urgent_window_hours)
        fixtures = (
            db.query(Fixture)
            .filter(Fixture.status == "scheduled", Fixture.kickoff_utc <= cutoff)
            .all()
        )
    else:
        fixtures = ingest_fixtures(db, client)
        summary["fixtures_upserted"] = len(fixtures)

    for fixture in fixtures:
        try:
            inserted = ingest_odds_for_fixture(db, client, fixture)
            summary["odds_inserted"] += inserted
            summary["fixtures_processed"] += 1
        except Exception:
            logger.exception("fixture %s 오즈 수집 중 예외 발생, 스킵", fixture.external_id)

    return summary


def cleanup_past_combo_recommendations(db: Session) -> int:
    """킥오프가 지난 경기의 combo_recommendations 캐시 정리."""
    from app.models.combo import ComboRecommendation

    past_fixture_ids = (
        db.query(Fixture.id).filter(Fixture.kickoff_utc < datetime.now(timezone.utc)).subquery()
    )
    deleted = (
        db.query(ComboRecommendation)
        .filter(ComboRecommendation.fixture_id.in_(past_fixture_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
