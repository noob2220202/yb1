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
        # Pick 저장(save)이 의존하는 필드들이 항상 채워져 있어야 함
        assert c["favorite_side"] == "home"
        assert c["odds_leg_a"] > 1.0
        assert c["odds_leg_b"] > 1.0
        assert c["stake_leg_a"] > 0
        assert c["stake_leg_b"] > 0

    dnb_candidate = next(c for c in candidates if c["combo_type"] == "draw_dnb0")
    assert dnb_candidate["leg_b_selection"] == "home"  # 홈팀이 favorite이므로 DNB는 홈팀 쪽
    assert "홈팀" in dnb_candidate["description"]

    margin_candidate = next(c for c in candidates if c["combo_type"] == "ahplus1_margin1")
    assert margin_candidate["leg_a_selection"] == "away"  # 원정팀이 underdog
    assert margin_candidate["leg_b_selection"] == "home_by_1"


def test_implied_hit_rate_never_exceeds_one_even_with_inconsistent_markets(db_session):
    """회귀 테스트: 1X2 마켓과 승리마진 마켓을 각각 독립적으로 devig해서 더하면
    100%를 넘는 경우가 실제로 있었다(사용자가 수동입력에서 재현: 109.5%).
    두 마켓의 확률에 서로 다른 북메이커 마진이 섞여 있으면 합이 1을 넘을 수
    있다 — 승리마진 마켓 하나의 분포만으로 계산하도록 고쳤으므로 항상 1
    이하여야 한다(옛 공식으로는 이 데이터에서 106.6%가 나와 실패했음)."""
    fixture = _build_fixture(db_session)
    # 1X2: 홈이 근소 우위(약 44% 확률)
    _add_market(db_session, fixture.id, "1x2", None, "TestBook", {"home": 2.20, "draw": 3.30, "away": 3.40})
    _add_market(db_session, fixture.id, "ah", Decimal("-1.0"), "TestBook", {"home": 1.30, "away": 3.20})
    # home_by_1이 비정상적으로 짧은 오즈(1.80) — 승리마진 마켓에서 devig한
    # "홈 1골차 승" 확률(약 50%)이 1X2 마켓의 "홈 승" 확률(약 44%)보다 커지는
    # 마켓간 불일치를 재현 (현실에서는 불가능하지만 손입력 데이터에서는 발생)
    _add_market(
        db_session, fixture.id, "win_margin", None, "TestBook",
        {"home_by_1": 1.80, "home_by_2plus": 8.0, "draw": 4.5, "away_by_1": 6.0, "away_by_2plus": 10.0},
    )
    db_session.commit()

    candidates = generate_combo_candidates(db_session, fixture, total_stake=30000)
    margin_candidate = next(c for c in candidates if c["combo_type"] == "ahplus1_margin1")

    assert 0.0 <= margin_candidate["implied_hit_rate"] <= 1.0


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
