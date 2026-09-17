"""HTTP 레벨 회귀 테스트: 수동 입력 폼에서 선택 필드를 비워둬도 (브라우저가
빈 문자열 ""을 보내는 경우) 422가 나지 않고 정상 저장되어야 한다."""
from fastapi.testclient import TestClient

from app.db import get_db
from app.main import app
from tests.conftest import _TestSessionLocal


def _override_get_db():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def test_manual_new_with_blank_optional_fields_does_not_422(db_session):
    resp = client.post(
        "/manual/new",
        data={
            "home_team": "Blank United",
            "away_team": "Blank City",
            "league_name": "",
            "kickoff_utc": "2026-09-20T15:00",
            "odds_1x2_home": "1.90",
            "odds_1x2_draw": "3.60",
            "odds_1x2_away": "4.20",
            # 선택 필드는 브라우저가 빈 문자열로 보낸다고 가정 — 전부 비워둠
            "odds_dnb_home": "",
            "odds_dnb_away": "",
            "favorite_team": "home",
            "odds_ah05_favorite": "",
            "odds_ah05_underdog": "",
            "odds_ah1_favorite": "",
            "odds_ah1_underdog": "",
            "margin_home_by1": "",
            "margin_home_by4plus": "",
            "margin_draw": "",
            "margin_away_by1": "",
            "margin_away_by4plus": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"].startswith("/fixtures/")


def test_manual_new_with_partial_fields_filled_does_not_422(db_session):
    resp = client.post(
        "/manual/new",
        data={
            "home_team": "Partial United",
            "away_team": "Partial City",
            "league_name": "Test",
            "kickoff_utc": "2026-09-20T15:00",
            "odds_1x2_home": "1.90",
            "odds_1x2_draw": "3.60",
            "odds_1x2_away": "4.20",
            "odds_dnb_home": "1.55",
            "odds_dnb_away": "2.60",
            "favorite_team": "home",
            "odds_ah05_favorite": "",
            "odds_ah05_underdog": "",
            "odds_ah1_favorite": "",
            "odds_ah1_underdog": "",
            "margin_home_by1": "",
            "margin_home_by4plus": "",
            "margin_draw": "",
            "margin_away_by1": "",
            "margin_away_by4plus": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
