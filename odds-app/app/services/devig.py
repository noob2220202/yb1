"""마진 제거(devig) 엔진.

북메이커의 십진 오즈에는 마진(오버라운드)이 포함돼 있어, 역배당을 그대로 더하면
1보다 커진다. 이 모듈은 마켓 유형에 맞는 방법으로 마진을 제거해 "실제 확률"을
역산한다.
"""
from __future__ import annotations

import math

MIN_ODDS = 1.0001


def _validate_odds(odds: list[float]) -> None:
    if not odds:
        raise ValueError("odds 리스트가 비어 있습니다")
    for o in odds:
        if o < MIN_ODDS:
            raise ValueError(f"오즈는 {MIN_ODDS} 이상이어야 합니다: {o}")


def devig_multiplicative(odds: list[float]) -> list[float]:
    """2-way(또는 다중) 시장의 기본 devig. 각 역배당을 합으로 정규화한다.

    AH, O/U, DNB, BTTS 등 마진이 대체로 균등하게 분포된 시장에 적합.
    """
    _validate_odds(odds)
    raw = [1.0 / o for o in odds]
    total = sum(raw)
    return [r / total for r in raw]


def devig_power(odds: list[float]) -> list[float]:
    """1X2(3-way) 기본 devig. 지수 k를 이분탐색으로 찾아 sum(r_i^k) = 1이 되게 한다.

    r_i = 1/odds_i (원시 내재확률). true_prob_i = r_i^k.
    """
    _validate_odds(odds)
    raw = [1.0 / o for o in odds]
    total = sum(raw)

    if total <= 1.0:
        # 마진이 없거나 음수(아비트라지) — 그대로 정규화만 수행
        return [r / total for r in raw]

    def sum_at(k: float) -> float:
        return sum(r**k for r in raw)

    lo, hi = 1.0, 2.0
    # sum_at(k)는 k에 대해 단조 감소. hi를 sum_at(hi) < 1 이 될 때까지 키운다.
    while sum_at(hi) > 1.0:
        hi *= 2
        if hi > 1e6:
            break

    for _ in range(200):
        mid = (lo + hi) / 2
        if sum_at(mid) > 1.0:
            lo = mid
        else:
            hi = mid

    k = (lo + hi) / 2
    probs = [r**k for r in raw]
    s = sum(probs)
    return [p / s for p in probs]


def devig_shin(odds: list[float]) -> list[float]:
    """다결과(정확한 점수, 승리마진) 기본 devig. Shin's method.

    내부자 거래 비율 z를 반복법(이분탐색)으로 추정한다.
    p_i = (sqrt(z^2 + 4*(1-z)*r_i^2/R) - z) / (2*(1-z)),  R = sum(r_i)
    """
    _validate_odds(odds)
    raw = [1.0 / o for o in odds]
    R = sum(raw)

    if R <= 1.0:
        return [r / R for r in raw]

    def probs_for_z(z: float) -> list[float]:
        if z <= 0.0:
            return [r / R for r in raw]
        return [
            (math.sqrt(z * z + 4 * (1 - z) * (r * r) / R) - z) / (2 * (1 - z))
            for r in raw
        ]

    lo, hi = 0.0, 0.999999
    for _ in range(200):
        mid = (lo + hi) / 2
        s = sum(probs_for_z(mid))
        if s > 1.0:
            lo = mid
        else:
            hi = mid

    z = (lo + hi) / 2
    probs = probs_for_z(z)
    s = sum(probs)
    return [p / s for p in probs]


_MARKET_METHOD = {
    "1x2": devig_power,
    "ah": devig_multiplicative,
    "ou": devig_multiplicative,
    "dnb": devig_multiplicative,
    "btts": devig_multiplicative,
    "correct_score": devig_shin,
    "win_margin": devig_shin,
}


def devig_market(market_type: str, odds: list[float]) -> list[float]:
    """market_type에 따라 적절한 devig 함수를 자동 선택해 호출하는 라우터."""
    method = _MARKET_METHOD.get(market_type, devig_multiplicative)
    return method(odds)


def consensus_probability(
    bookmaker_probs: list[float],
    weights: dict[str, float] | None = None,
    bookmaker_names: list[str] | None = None,
) -> float:
    """여러 북메이커의 devig 확률을 평균낸다.

    1차 MVP는 단순 평균. weights가 주어지면(북메이커명 -> 가중치) 가중평균으로
    전환할 수 있도록 시그니처를 열어둔다.
    """
    if not bookmaker_probs:
        raise ValueError("bookmaker_probs가 비어 있습니다")

    if weights is None or bookmaker_names is None:
        return sum(bookmaker_probs) / len(bookmaker_probs)

    total_weight = 0.0
    weighted_sum = 0.0
    for name, prob in zip(bookmaker_names, bookmaker_probs):
        w = weights.get(name, 1.0)
        weighted_sum += w * prob
        total_weight += w
    if total_weight == 0:
        return sum(bookmaker_probs) / len(bookmaker_probs)
    return weighted_sum / total_weight


def calc_ev(stake: float, decimal_odds: float, true_prob: float) -> float:
    """EV = stake * (decimal_odds * true_prob - 1)"""
    return stake * (decimal_odds * true_prob - 1)
