import math

import pytest

from app.services.devig import (
    calc_ev,
    consensus_probability,
    devig_market,
    devig_multiplicative,
    devig_power,
    devig_shin,
)


def test_devig_multiplicative_sums_to_one():
    odds = [1.90, 2.10]  # 전형적인 2-way 마켓, 마진 존재
    probs = devig_multiplicative(odds)
    assert math.isclose(sum(probs), 1.0, abs_tol=1e-9)
    # 오즈가 낮을수록(배당 짧을수록) 확률이 높아야 함
    assert probs[0] > probs[1]


def test_devig_multiplicative_no_margin_still_normalizes():
    odds = [2.0, 2.0]
    probs = devig_multiplicative(odds)
    assert math.isclose(probs[0], 0.5, abs_tol=1e-9)
    assert math.isclose(probs[1], 0.5, abs_tol=1e-9)


def test_devig_power_sums_to_one_1x2():
    odds = [2.50, 3.40, 2.90]  # 1X2 전형적인 오즈, overround 존재
    raw = [1 / o for o in odds]
    assert sum(raw) > 1.0  # 마진이 있는지 확인
    probs = devig_power(odds)
    assert math.isclose(sum(probs), 1.0, abs_tol=1e-6)
    # 순위 보존: 오즈가 짧을수록 확률이 높아야 함
    assert probs[0] > probs[2] > probs[1]


def test_devig_power_matches_naive_normalization_when_no_margin():
    odds = [3.0, 3.0, 3.0]
    probs = devig_power(odds)
    for p in probs:
        assert math.isclose(p, 1 / 3, abs_tol=1e-6)


def test_devig_shin_sums_to_one():
    # 정확한 점수류 다결과 마켓 근사 오즈 (마진 큼)
    odds = [7.5, 5.2, 4.2, 6.0, 9.0, 15.0, 8.0, 12.0, 21.0, 34.0]
    probs = devig_shin(odds)
    assert math.isclose(sum(probs), 1.0, abs_tol=1e-6)
    assert all(p > 0 for p in probs)


def test_devig_shin_two_way_sums_to_one():
    odds = [1.85, 1.95]
    probs = devig_shin(odds)
    assert math.isclose(sum(probs), 1.0, abs_tol=1e-6)
    assert probs[0] > probs[1]  # 오즈가 더 짧은(1.85) 쪽의 확률이 더 높아야 함


def test_devig_market_router_dispatch():
    assert devig_market("1x2", [2.5, 3.4, 2.9]) == devig_power([2.5, 3.4, 2.9])
    assert devig_market("ah", [1.9, 1.95]) == devig_multiplicative([1.9, 1.95])
    assert devig_market("ou", [1.9, 1.95]) == devig_multiplicative([1.9, 1.95])
    assert devig_market("dnb", [1.9, 1.95]) == devig_multiplicative([1.9, 1.95])
    assert devig_market("btts", [1.9, 1.95]) == devig_multiplicative([1.9, 1.95])
    assert devig_market("correct_score", [7.5, 5.2, 4.2]) == devig_shin([7.5, 5.2, 4.2])
    assert devig_market("win_margin", [7.5, 5.2, 4.2]) == devig_shin([7.5, 5.2, 4.2])


def test_devig_invalid_odds_raises():
    with pytest.raises(ValueError):
        devig_multiplicative([])
    with pytest.raises(ValueError):
        devig_multiplicative([0.5, 2.0])


def test_consensus_probability_simple_average():
    probs = [0.45, 0.47, 0.44]
    assert math.isclose(consensus_probability(probs), sum(probs) / 3, abs_tol=1e-9)


def test_consensus_probability_weighted_average():
    probs = [0.40, 0.60]
    names = ["book_a", "book_b"]
    weights = {"book_a": 1.0, "book_b": 3.0}
    result = consensus_probability(probs, weights=weights, bookmaker_names=names)
    expected = (0.40 * 1.0 + 0.60 * 3.0) / 4.0
    assert math.isclose(result, expected, abs_tol=1e-9)


def test_calc_ev_positive_and_negative():
    # 배당 2.5, 실제 확률 0.45 -> EV = 100*(2.5*0.45-1) = 12.5 (양수)
    assert math.isclose(calc_ev(100, 2.5, 0.45), 12.5, abs_tol=1e-9)
    # 배당 2.0, 실제 확률 0.40 -> EV = 100*(2.0*0.4-1) = -20 (음수)
    assert math.isclose(calc_ev(100, 2.0, 0.40), -20.0, abs_tol=1e-9)
