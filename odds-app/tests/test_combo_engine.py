from datetime import datetime, timezone
from decimal import Decimal

from app.models.combo import ComboRecommendation
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from app.services.combo_engine import compute_and_cache_combos, generate_combo_candidates
from app.services.staking import STAKING_DISCLAIMER


def _add_market(db, fixture_id, market_type, line, bookmaker, selections_odds):
    market = Market(fixture_id=fixture_id, market_type=market_type, line=line, bookmaker=bookmaker)
    db.add(market)
    db.flush()
    for selection, odds in selections_odds.items():
        db.add(Odds(market_id=market.id, selection=selection, decimal_odds=Decimal(str(odds))))
    return market


def _build_fixture(db):
    fixture = Fixture(
        external_id="combo-test-1",
        league_id=1,
        league_name="Test League",
        home_team="Home FC",
        away_team="Away FC",
        kickoff_utc=datetime(2026, 9, 20, 15, 0, 0, tzinfo=timezone.utc),
    )
    db.add(fixture)
    db.flush()
    return fixture


def _seed_full_market_data(db, fixture):
    # 홈팀이 뚜렷한 정배(favorite)인 시나리오
    _add_market(db, fixture.id, "1x2", None, "TestBook", {"home": 1.90, "draw": 3.60, "away": 4.20})
    _add_market(db, fixture.id, "dnb", None, "TestBook", {"home": 1.55, "away": 2.60})
    _add_market(db, fixture.id, "ah", Decimal("-0.5"), "TestBook", {"home": 1.95, "away": 1.85})
    _add_market(db, fixture.id, "ah", Decimal("-1.0"), "TestBook", {"home": 1.30, "away": 3.20})
    _add_market(
        db, fixture.id, "win_margin", None, "TestBook",
        {"home_by_1": 3.5, "home_by_2": 6.0, "draw": 3.4, "away_by_1": 7.0},
    )
    db.commit()


def test_generate_combo_candidates_full_data(db_session):
    fixture = _build_fixture(db_session)
    _seed_full_market_data(db_session, fixture)

    candidates = generate_combo_candidates(db_session, fixture, total_stake=30000)

    combo_types = {c["combo_type"] for c in candidates}
    assert combo_types == {"draw_dnb0", "draw_ah05", "ahplus1_margin1"}

    for c in candidates:
        assert c["disclaimer"] == STAKING_DISCLAIMER
        assert c["total_stake"] > 0
        assert 0 <= c["implied_hit_rate"] <= 1
        assert isinstance(c["ev_negative"], bool)
        assert c["ev_negative"] == (c["estimated_ev_pct"] < 0)

    dnb_candidate = next(c for c in candidates if c["combo_type"] == "draw_dnb0")
    assert dnb_candidate["leg_b_selection"] == "home"  # 홈팀이 favorite이므로 DNB는 홈팀 쪽
    assert "홈팀" in dnb_candidate["description"]

    margin_candidate = next(c for c in candidates if c["combo_type"] == "ahplus1_margin1")
    assert margin_candidate["leg_a_selection"] == "away"  # 원정팀이 underdog
    assert margin_candidate["leg_b_selection"] == "home_by_1"


def test_generate_combo_candidates_returns_empty_without_1x2(db_session):
    fixture = _build_fixture(db_session)
    db_session.commit()
    candidates = generate_combo_candidates(db_session, fixture, total_stake=30000)
    assert candidates == []


def test_generate_combo_candidates_partial_data_skips_missing_combo(db_session):
    fixture = _build_fixture(db_session)
    _add_market(db_session, fixture.id, "1x2", None, "TestBook", {"home": 1.90, "draw": 3.60, "away": 4.20})
    _add_market(db_session, fixture.id, "dnb", None, "TestBook", {"home": 1.55, "away": 2.60})
    db_session.commit()

    candidates = generate_combo_candidates(db_session, fixture, total_stake=30000)
    combo_types = {c["combo_type"] for c in candidates}
    assert combo_types == {"draw_dnb0"}  # ah/win_margin 데이터가 없으므로 나머지는 생성 안 됨


def test_compute_and_cache_combos_persists_rows(db_session):
    fixture = _build_fixture(db_session)
    _seed_full_market_data(db_session, fixture)

    candidates = compute_and_cache_combos(db_session, fixture, total_stake=30000)

    rows = db_session.query(ComboRecommendation).filter(ComboRecommendation.fixture_id == fixture.id).all()
    assert len(rows) == len(candidates) == 3

    # 재계산 시 기존 캐시가 갱신(중복 누적 아님)되는지 확인
    compute_and_cache_combos(db_session, fixture, total_stake=30000)
    rows_after = db_session.query(ComboRecommendation).filter(ComboRecommendation.fixture_id == fixture.id).all()
    assert len(rows_after) == 3
