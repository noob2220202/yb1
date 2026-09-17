from datetime import datetime, timezone

from app.models.fixture import Fixture
from app.services.combo_engine import compute_and_cache_combos, generate_combo_candidates
from app.services.manual_entry import (
    ManualOddsInput,
    create_manual_fixture,
    load_manual_form_data,
    save_manual_odds,
    update_manual_fixture_info,
)


def test_create_manual_fixture_sets_source_and_external_id(db_session):
    fixture = create_manual_fixture(
        db_session, "Home FC", "Away FC", "테스트리그", datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    db_session.commit()

    assert fixture.source == "manual"
    assert fixture.external_id.startswith("manual-")
    assert fixture.status == "scheduled"


def test_save_and_load_manual_odds_roundtrip_home_favorite(db_session):
    fixture = create_manual_fixture(
        db_session, "Home FC", "Away FC", None, datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    db_session.commit()

    data = ManualOddsInput(
        odds_1x2_home=1.90, odds_1x2_draw=3.60, odds_1x2_away=4.20,
        odds_dnb_home=1.55, odds_dnb_away=2.60,
        favorite_team="home",
        odds_ah05_favorite=1.95, odds_ah05_underdog=1.85,
        odds_ah1_favorite=1.30, odds_ah1_underdog=3.20,
        margin_home_by1=3.5, margin_home_by4plus=2.5, margin_draw=3.4,
        margin_away_by1=7.0, margin_away_by4plus=15.0,
    )
    save_manual_odds(db_session, fixture.id, data)

    loaded = load_manual_form_data(db_session, fixture.id)
    assert loaded["odds_1x2_home"] == 1.90
    assert loaded["odds_dnb_away"] == 2.60
    assert loaded["favorite_team"] == "home"
    assert loaded["odds_ah05_favorite"] == 1.95
    assert loaded["odds_ah1_underdog"] == 3.20
    assert loaded["margin_away_by4plus"] == 15.0


def test_save_manual_odds_overwrites_not_accumulates(db_session):
    fixture = create_manual_fixture(
        db_session, "Home FC", "Away FC", None, datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    db_session.commit()

    data_v1 = ManualOddsInput(odds_1x2_home=1.90, odds_1x2_draw=3.60, odds_1x2_away=4.20)
    save_manual_odds(db_session, fixture.id, data_v1)

    data_v2 = ManualOddsInput(odds_1x2_home=1.80, odds_1x2_draw=3.70, odds_1x2_away=4.50)
    save_manual_odds(db_session, fixture.id, data_v2)

    loaded = load_manual_form_data(db_session, fixture.id)
    assert loaded["odds_1x2_home"] == 1.80  # 최신 값으로 덮어써짐

    from app.models.market import Market
    markets = db_session.query(Market).filter(Market.fixture_id == fixture.id, Market.market_type == "1x2").all()
    assert len(markets) == 1  # 누적되지 않고 하나만 존재


def test_save_manual_odds_after_combo_cache_does_not_violate_fk(db_session):
    """/fixtures/{id}를 방문해 combo_recommendations가 캐시된 뒤 오즈를 수정해도
    FK 위반 없이 기존 market row를 지우고 새로 저장할 수 있어야 한다."""
    fixture = create_manual_fixture(
        db_session, "Home FC", "Away FC", None, datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    db_session.commit()

    data = ManualOddsInput(
        odds_1x2_home=1.90, odds_1x2_draw=3.60, odds_1x2_away=4.20,
        odds_dnb_home=1.55, odds_dnb_away=2.60,
        favorite_team="home",
        odds_ah05_favorite=1.95, odds_ah05_underdog=1.85,
        odds_ah1_favorite=1.30, odds_ah1_underdog=3.20,
        margin_home_by1=3.5, margin_home_by4plus=2.5, margin_draw=3.4,
        margin_away_by1=7.0, margin_away_by4plus=15.0,
    )
    save_manual_odds(db_session, fixture.id, data)

    compute_and_cache_combos(db_session, fixture)  # combo_recommendations가 market을 FK 참조

    data.odds_1x2_home = 2.10  # 값만 바꿔서 재저장 (덮어쓰기)
    save_manual_odds(db_session, fixture.id, data)  # IntegrityError가 나면 안 됨

    loaded = load_manual_form_data(db_session, fixture.id)
    assert loaded["odds_1x2_home"] == 2.10


def test_update_manual_fixture_info_changes_fields(db_session):
    fixture = create_manual_fixture(
        db_session, "Home FC", "Away FC", None, datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    db_session.commit()

    update_manual_fixture_info(fixture, "New Home", "New Away", "New League", datetime(2026, 9, 21, tzinfo=timezone.utc))
    db_session.commit()

    refreshed = db_session.query(Fixture).filter(Fixture.id == fixture.id).one()
    assert refreshed.home_team == "New Home"
    assert refreshed.league_name == "New League"


def test_manual_entry_combo_engine_works_with_away_favorite(db_session):
    """away가 정배인 경우에도 핸디캡 라인 부호가 올바르게 저장/조회되는지 확인
    (홈이 항상 -0.5/-1이라고 가정하면 발생했을 버그의 회귀 테스트)."""
    fixture = create_manual_fixture(
        db_session, "Underdog Home", "Strong Away", None, datetime(2026, 9, 20, tzinfo=timezone.utc)
    )
    db_session.commit()

    data = ManualOddsInput(
        odds_1x2_home=4.20, odds_1x2_draw=3.60, odds_1x2_away=1.90,  # 원정팀이 정배
        odds_dnb_home=2.60, odds_dnb_away=1.55,
        favorite_team="away",
        odds_ah05_favorite=1.95, odds_ah05_underdog=1.85,
        odds_ah1_favorite=1.30, odds_ah1_underdog=3.20,
        margin_home_by1=7.0, margin_home_by4plus=15.0, margin_draw=3.4,
        margin_away_by1=3.5, margin_away_by4plus=2.5,
    )
    save_manual_odds(db_session, fixture.id, data)

    candidates = generate_combo_candidates(db_session, fixture, total_stake=30000)
    combo_types = {c["combo_type"] for c in candidates}
    assert combo_types == {"draw_dnb0", "draw_ah05", "ahplus1_margin1"}

    dnb_candidate = next(c for c in candidates if c["combo_type"] == "draw_dnb0")
    assert dnb_candidate["leg_b_selection"] == "away"  # 원정팀이 favorite

    margin_candidate = next(c for c in candidates if c["combo_type"] == "ahplus1_margin1")
    assert margin_candidate["leg_a_selection"] == "home"  # 홈팀이 underdog
    assert margin_candidate["leg_b_selection"] == "away_by_1"
