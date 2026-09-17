import math
from decimal import Decimal

from app.models.pick import Pick
from app.services.grading import determine_scenario, grade_pick
from app.services.staking import (
    calc_ahplus1_margin1_stakes,
    calc_ahplus2_margin2_stakes,
    calc_draw_dnb0_stakes,
)


def _make_pick(**overrides) -> Pick:
    defaults = dict(
        home_team="Home FC",
        away_team="Away FC",
        combo_type="draw_dnb0",
        description="무승부 + 홈팀 DNB",
        leg_a_selection="draw",
        leg_b_selection="home",
        favorite_side="home",
        odds_leg_a=Decimal("3.46"),
        odds_leg_b=Decimal("1.854"),
        stake_leg_a=Decimal("4100"),
        stake_leg_b=Decimal("16600"),
        total_stake=Decimal("20700"),
        target_profit=Decimal("10076"),
    )
    defaults.update(overrides)
    return Pick(**defaults)


def test_draw_dnb0_home_favorite_draw_scenario():
    pick = _make_pick(favorite_side="home")
    assert determine_scenario(pick, 1, 1) == "draw"
    assert determine_scenario(pick, 2, 0) == "home_win"  # 홈(정배) 승
    assert determine_scenario(pick, 0, 1) == "away_win"  # 원정(역배) 승


def test_draw_dnb0_away_favorite_flips_home_win_meaning():
    """favorite_side=away면 leg_b는 원정팀 DNB이므로, 원정팀이 이겨야 'home_win'
    (정배 적중) 버킷이 되어야 한다 — 물리적 팀이 아니라 역할(정배/역배) 기준."""
    pick = _make_pick(favorite_side="away", leg_b_selection="away")
    assert determine_scenario(pick, 1, 1) == "draw"
    assert determine_scenario(pick, 0, 2) == "home_win"  # 원정(정배) 승
    assert determine_scenario(pick, 1, 0) == "away_win"  # 홈(역배) 승


def test_grade_pick_draw_dnb0_matches_staking_regression_numbers():
    """SPEC.md 12절 검증 수치와 동일한 픽을 각 시나리오별로 채점."""
    pick = _make_pick(
        odds_leg_a=Decimal("3.46"), odds_leg_b=Decimal("1.854"),
        target_profit=Decimal("10076"), favorite_side="home",
    )
    expected = calc_draw_dnb0_stakes(3.46, 1.854, 10076)

    draw_result = grade_pick(pick, 1, 1)
    assert draw_result["scenario"] == "draw"
    assert math.isclose(draw_result["net_profit"], expected["profit_draw"], rel_tol=1e-9)

    home_win_result = grade_pick(pick, 2, 0)
    assert home_win_result["scenario"] == "home_win"
    assert math.isclose(home_win_result["net_profit"], expected["profit_home_win"], rel_tol=1e-9)

    away_win_result = grade_pick(pick, 0, 1)
    assert away_win_result["scenario"] == "away_win"
    assert math.isclose(away_win_result["net_profit"], expected["loss_away_win"], rel_tol=1e-9)
    assert away_win_result["net_profit"] < 0


def test_grade_pick_ahplus1_margin1():
    pick = _make_pick(
        combo_type="ahplus1_margin1",
        leg_a_selection="away",
        leg_b_selection="home_by_1",
        favorite_side="home",
        odds_leg_a=Decimal("1.93"), odds_leg_b=Decimal("3.8"),
        target_profit=Decimal("10076"),
    )
    expected = calc_ahplus1_margin1_stakes(1.93, 3.8, 10076)

    underdog_or_draw = grade_pick(pick, 1, 1)  # 무승부
    assert underdog_or_draw["scenario"] == "underdog_win_or_draw"
    assert math.isclose(underdog_or_draw["net_profit"], expected["profit_underdog_or_draw"], rel_tol=1e-9)

    away_win = grade_pick(pick, 0, 2)  # 역배(원정) 승
    assert away_win["scenario"] == "underdog_win_or_draw"

    margin1 = grade_pick(pick, 2, 1)  # 정배 1골차
    assert margin1["scenario"] == "favorite_margin1"
    assert math.isclose(margin1["net_profit"], expected["profit_fav_margin1"], rel_tol=1e-9)

    margin2plus = grade_pick(pick, 3, 0)  # 정배 2골차+
    assert margin2plus["scenario"] == "favorite_margin2plus"
    assert margin2plus["net_profit"] < 0
    assert math.isclose(margin2plus["net_profit"], expected["loss_fav_margin2plus"], rel_tol=1e-9)


def test_draw_ah15_requires_two_goal_margin_for_home_win():
    """AH-1.5는 1골차 승으로는 다리 B가 적중하지 않는다 — draw_ah05(margin>=1)와
    달리 margin>=2가 필요하다. 이 차이를 놓치면 1골차 승을 잘못 '적중'으로
    채점하는 버그가 생긴다."""
    pick = _make_pick(combo_type="draw_ah15", favorite_side="home")

    assert determine_scenario(pick, 1, 1) == "draw"
    assert determine_scenario(pick, 1, 0) == "away_win"  # 1골차 승 — AH-1.5는 실패
    assert determine_scenario(pick, 2, 0) == "home_win"  # 2골차 승 — AH-1.5 적중
    assert determine_scenario(pick, 3, 0) == "home_win"


def test_grade_pick_ahplus2_margin2():
    pick = _make_pick(
        combo_type="ahplus2_margin2",
        leg_a_selection="away",
        leg_b_selection="home_by_2",
        favorite_side="home",
        odds_leg_a=Decimal("1.50"), odds_leg_b=Decimal("4.5"),
        target_profit=Decimal("5000"),
    )
    expected = calc_ahplus2_margin2_stakes(1.50, 4.5, 5000)

    underdog_draw_or_margin1 = grade_pick(pick, 2, 1)  # 정배 1골차 — AH+2가 커버
    assert underdog_draw_or_margin1["scenario"] == "underdog_draw_or_margin1"
    assert math.isclose(
        underdog_draw_or_margin1["net_profit"], expected["profit_underdog_draw_or_margin1"], rel_tol=1e-9
    )

    margin2 = grade_pick(pick, 3, 1)  # 정배 정확히 2골차
    assert margin2["scenario"] == "favorite_margin2"
    assert math.isclose(margin2["net_profit"], expected["profit_fav_margin2"], rel_tol=1e-9)

    margin3plus = grade_pick(pick, 4, 0)  # 정배 3골차+
    assert margin3plus["scenario"] == "favorite_margin3plus"
    assert margin3plus["net_profit"] < 0
    assert math.isclose(margin3plus["net_profit"], expected["loss_fav_margin3plus"], rel_tol=1e-9)
