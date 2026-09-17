import math

import pytest

from app.services.staking import (
    STAKING_DISCLAIMER,
    calc_ahplus1_margin1_stakes,
    calc_ahplus2_margin2_stakes,
    calc_draw_ah05_stakes,
    calc_draw_dnb0_stakes,
    equal_profit_stakes,
)


def test_equal_profit_stakes_basic_dutching():
    odds = [2.0, 4.0]
    stakes = equal_profit_stakes(odds, 300)
    # 1/2=0.5, 1/4=0.25, sum=0.75 -> stake0=300*0.5/0.75=200, stake1=100
    assert math.isclose(stakes[0], 200.0, abs_tol=1e-6)
    assert math.isclose(stakes[1], 100.0, abs_tol=1e-6)
    # 어느 결과든 동일 지급액인지 검증
    payout0 = stakes[0] * odds[0]
    payout1 = stakes[1] * odds[1]
    assert math.isclose(payout0, payout1, abs_tol=1e-6)


def test_equal_profit_stakes_three_way():
    odds = [3.0, 3.0, 3.0]
    stakes = equal_profit_stakes(odds, 300)
    for s in stakes:
        assert math.isclose(s, 100.0, abs_tol=1e-6)


def test_equal_profit_stakes_validation():
    with pytest.raises(ValueError):
        equal_profit_stakes([], 100)
    with pytest.raises(ValueError):
        equal_profit_stakes([2.0], 0)


def test_draw_dnb0_regression_from_spec():
    """SPEC.md 12절 회귀 테스트 케이스: odds_draw=3.46, odds_dnb=1.854, target_profit≈10076."""
    result = calc_draw_dnb0_stakes(odds_draw=3.46, odds_dnb=1.854, target_profit=10076)

    assert math.isclose(result["stake_draw"], 4100, rel_tol=0.02)
    assert math.isclose(result["stake_dnb"], 16600, rel_tol=0.02)

    # 구성상 두 이익 시나리오는 정확히 target_profit과 일치해야 한다
    assert math.isclose(result["profit_draw"], 10076, rel_tol=1e-9)
    assert math.isclose(result["profit_home_win"], 10076, rel_tol=1e-9)
    assert result["loss_away_win"] < 0
    assert 0 < result["breakeven_prob"] < 1
    assert set(result["all_scenarios"].keys()) == {"draw", "home_win", "away_win"}


def test_draw_dnb0_push_scenario_math():
    result = calc_draw_dnb0_stakes(odds_draw=3.0, odds_dnb=1.5, target_profit=1000)
    stake_draw = result["stake_draw"]
    stake_dnb = result["stake_dnb"]
    # 무승부: A 적중(odds 3.0), B push
    assert math.isclose(stake_draw * (3.0 - 1), 1000, rel_tol=1e-9)
    # 정배승: A 실패, B 적중 (odds 1.5) 순이익 = target_profit
    assert math.isclose(stake_dnb * (1.5 - 1) - stake_draw, 1000, rel_tol=1e-9)
    # 역배승: 둘 다 실패
    assert math.isclose(result["loss_away_win"], -(stake_draw + stake_dnb), rel_tol=1e-9)


def test_draw_ah05_no_push():
    result = calc_draw_ah05_stakes(odds_draw=3.4, odds_ah05=1.9, target_profit=1000)
    assert result["stake_draw"] > 0
    assert result["stake_ah05"] > 0
    assert math.isclose(
        result["stake_draw"] * (3.4 - 1), 1000, rel_tol=1e-9
    )  # 단독 적중 기준 target_profit
    assert math.isclose(result["stake_ah05"] * (1.9 - 1), 1000, rel_tol=1e-9)
    assert result["loss_away_win"] < 0


def test_ahplus1_margin1_regression_from_spec():
    """SPEC.md 12절 회귀 테스트 케이스: odds_ahplus1=1.93, odds_margin1=3.8, target_profit≈10071~10080."""
    result = calc_ahplus1_margin1_stakes(
        odds_ahplus1=1.93, odds_margin1=3.8, target_profit=10076
    )

    assert math.isclose(result["stake_ahplus1"], 14700, rel_tol=0.02)
    assert math.isclose(result["stake_margin1"], 3600, rel_tol=0.02)

    assert math.isclose(result["profit_underdog_or_draw"], 10076, rel_tol=1e-9)
    assert math.isclose(result["profit_fav_margin1"], 10076, rel_tol=1e-9)
    assert result["loss_fav_margin2plus"] < 0
    assert 0 < result["breakeven_prob"] < 1
    assert set(result["all_scenarios"].keys()) == {
        "underdog_win_or_draw",
        "favorite_margin1",
        "favorite_margin2plus",
    }


def test_disclaimer_constant_present():
    assert "손익 분산" in STAKING_DISCLAIMER
    assert "기대값을 개선하지 않습니다" in STAKING_DISCLAIMER


def test_ahplus2_margin2_scenario_math():
    """ahplus1_margin1과 같은 원리로 한 골 넓힌 버전 — 두 이익 시나리오 모두
    정확히 target_profit과 일치해야 하고, 3골차+만 손실이어야 한다."""
    result = calc_ahplus2_margin2_stakes(odds_ahplus2=1.50, odds_margin2=4.5, target_profit=5000)

    assert math.isclose(result["profit_underdog_draw_or_margin1"], 5000, rel_tol=1e-9)
    assert math.isclose(result["profit_fav_margin2"], 5000, rel_tol=1e-9)
    assert result["loss_fav_margin3plus"] < 0
    assert 0 < result["breakeven_prob"] < 1
    assert set(result["all_scenarios"].keys()) == {
        "underdog_draw_or_margin1",
        "favorite_margin2",
        "favorite_margin3plus",
    }

    # 시나리오별 leg 결과 라벨이 push/win/lose 규칙과 일치하는지 확인
    assert result["all_scenarios"]["underdog_draw_or_margin1"]["leg_a"] == "win"
    assert result["all_scenarios"]["favorite_margin2"]["leg_a"] == "push"
    assert result["all_scenarios"]["favorite_margin3plus"]["leg_a"] == "lose"
