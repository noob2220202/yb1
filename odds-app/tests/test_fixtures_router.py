"""HTTP 레벨 테스트: 경기 상세 페이지의 총 스테이크를 쿼리 파라미터로 유동적으로
바꿀 수 있어야 한다(사이트 내에서 배팅금액을 조정하는 기능)."""
import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from tests.conftest import _TestSessionLocal


def _override_get_db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def _seed_fixture_with_markets(db) -> Fixture:
    fixture = Fixture(
        external_id="fixtures-router-test-1",
        league_id=1,
        league_name="Test League",
        home_team="Stake Home",
        away_team="Stake Away",
        kickoff_utc=datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc),
        source="manual",
    )
    db.add(fixture)
    db.flush()

    def add_market(market_type, line, selections):
        market = Market(fixture_id=fixture.id, market_type=market_type, line=line, bookmaker="TestBook")
        db.add(market)
        db.flush()
        for selection, odds in selections.items():
            db.add(Odds(market_id=market.id, selection=selection, decimal_odds=Decimal(str(odds))))

    add_market("1x2", None, {"home": 1.90, "draw": 3.60, "away": 4.20})
    add_market("dnb", None, {"home": 1.55, "away": 2.60})
    db.commit()
    return fixture


def _extract_visible_total_stake_input(html: str) -> str:
    """상단의 '총 스테이크' 숫자 입력 필드 값(속성 순서에 의존하지 않음).
    픽 저장 폼의 hidden total_stake 필드와 구분하기 위해 type="number"로 앵커링."""
    match = re.search(r'<input type="number" name="total_stake"[^>]*value="([\d.]+)"', html)
    assert match, "총 스테이크 입력 필드를 찾지 못함"
    return match.group(1)


def test_fixture_detail_default_total_stake(db_session):
    fixture = _seed_fixture_with_markets(db_session)

    resp = client.get(f"/fixtures/{fixture.id}")
    assert resp.status_code == 200
    assert _extract_visible_total_stake_input(resp.text) == "30000"  # .env 기본값


def test_fixture_detail_shows_markets_with_null_line(db_session):
    """회귀 테스트: line이 없는 마켓(1X2/DNB/승리마진)이 SQL JOIN에서 NULL=NULL이
    거짓으로 취급돼 누락되던 버그. '전체 마켓 오즈' 테이블에 반드시 나와야 한다."""
    fixture = _seed_fixture_with_markets(db_session)

    resp = client.get(f"/fixtures/{fixture.id}")
    assert resp.status_code == 200
    assert "1x2" in resp.text
    assert "dnb" in resp.text
    assert "home: 1.900" in resp.text or "home: 1.9" in resp.text


def test_fixture_detail_custom_total_stake_rescales_combo_stakes(db_session):
    fixture = _seed_fixture_with_markets(db_session)

    resp_default = client.get(f"/fixtures/{fixture.id}")
    resp_custom = client.get(f"/fixtures/{fixture.id}", params={"total_stake": 60000})

    assert resp_custom.status_code == 200
    assert _extract_visible_total_stake_input(resp_custom.text) == "60000"

    # 60000은 기본 30000의 두 배이므로, 조합 카드의 stake_draw 값도 대략 두 배여야 한다
    def extract_stake_draw(html: str) -> float:
        match = re.search(r'name="stake_leg_a" value="([\d.]+)"', html)
        assert match, "stake_leg_a hidden field를 찾지 못함"
        return float(match.group(1))

    default_stake = extract_stake_draw(resp_default.text)
    custom_stake = extract_stake_draw(resp_custom.text)
    assert custom_stake == pytest.approx(default_stake * 2, rel=1e-6)


def test_fixture_detail_ignores_non_positive_total_stake(db_session):
    fixture = _seed_fixture_with_markets(db_session)

    resp = client.get(f"/fixtures/{fixture.id}", params={"total_stake": -100})
    assert resp.status_code == 200
    assert _extract_visible_total_stake_input(resp.text) == "30000"  # 잘못된 값은 기본값으로 폴백
