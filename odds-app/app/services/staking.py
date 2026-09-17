"""스테이크 이퀄라이제이션(이익균등화) 계산기.

한 경기 내에서 서로 다른 두 개의 단폴더(단일 베팅)를 조합할 때, 각 결과에 대한
스테이크를 배분해 목표 이익을 계산한다. push(환급) 규칙이 있는 마켓 조합은
그 규칙을 반영한 변형식을 사용한다.

이 모듈은 배당 분산(variance reduction)만 수행할 뿐 기대값(EV)을 개선하지
않는다 — 실제 EV 판단은 devig 엔진의 실제 확률을 함께 봐야 한다.
"""
from __future__ import annotations

STAKING_DISCLAIMER = "이 배분은 손익 분산만 줄일 뿐 기대값을 개선하지 않습니다"

# 시나리오 dict의 key는 내부 로직(grading.py 등)에서 그대로 매칭에 쓰이므로 바꾸지 않고,
# 화면/텔레그램 표시용 한국어 라벨만 별도로 둔다.
SCENARIO_LABELS_KO = {
    "draw": "무승부",
    "home_win": "정배팀 승",
    "away_win": "역배팀 승 (양쪽 다리 실패)",
    "underdog_win_or_draw": "역배승 또는 무승부",
    "favorite_margin1": "정배 1골차 승",
    "favorite_margin2plus": "정배 2골차+ 승 (양쪽 다리 실패)",
    "underdog_draw_or_margin1": "역배승/무승부/정배 1골차 승",
    "favorite_margin2": "정배 2골차 승",
    "favorite_margin3plus": "정배 3골차+ 승 (양쪽 다리 실패)",
}

LEG_RESULT_LABELS_KO = {
    "win": "적중",
    "lose": "실패",
    "push": "환급(적중/실패 아님)",
}

COMBO_TYPE_LABELS_KO = {
    "draw_dnb0": "무승부 + 정배팀 DNB(AH0)",
    "draw_ah05": "무승부 + 정배팀 AH-0.5",
    "draw_ah15": "무승부 + 정배팀 AH-1.5",
    "ahplus1_margin1": "역배팀 AH+1 + 정배팀 정확히 1골차 승",
    "ahplus2_margin2": "역배팀 AH+2 + 정배팀 정확히 2골차 승",
}

QUALITY_GRADE_LABELS_KO = {
    "S": "S (최우수)",
    "A": "A (우수)",
    "B": "B (보통)",
    "C": "C (주의)",
    "D": "D (비추천)",
}


def compute_quality_grade(
    estimated_ev_pct: float | None, implied_hit_rate: float | None, breakeven_prob: float | None
) -> str | None:
    """조합의 사전 품질 등급(S/A/B/C/D)을 매긴다.

    두 가지 객관적 지표를 더한다:
    - 추정 EV%: 베팅의 기대 수익성 자체.
    - 여유분(margin, %p): (적중확률 추정 - 손익분기확률). 확률 추정이 다소
      부정확해도 버틸 수 있는 안전 마진을 뜻한다.

    devig 기반 실제 확률(implied_hit_rate/estimated_ev_pct)이 없는 픽
    (계산기에서 오즈만 넣고 저장한 경우 등)은 등급을 매길 근거가 없으므로
    None을 반환한다.
    """
    if estimated_ev_pct is None or implied_hit_rate is None or breakeven_prob is None:
        return None

    margin_pct = (implied_hit_rate - breakeven_prob) * 100
    score = estimated_ev_pct + margin_pct

    if score >= 8:
        return "S"
    if score >= 3:
        return "A"
    if score >= 0:
        return "B"
    if score >= -5:
        return "C"
    return "D"


def equal_profit_stakes(odds_list: list[float], total_stake: float) -> list[float]:
    """일반화된 다중 결과 균등이익 배분 (push 없음, 기본 dutching).

    s_i = total_stake * (1/o_i) / sum(1/o_j for all j)
    어느 결과가 적중해도 동일 지급액(payout)이 되도록 배분한다.
    """
    if not odds_list:
        raise ValueError("odds_list가 비어 있습니다")
    if total_stake <= 0:
        raise ValueError("total_stake는 0보다 커야 합니다")

    inv_odds = [1.0 / o for o in odds_list]
    total_inv = sum(inv_odds)
    return [total_stake * inv / total_inv for inv in inv_odds]


def _breakeven_prob(profit_scenarios: list[float], loss_magnitude: float) -> float:
    """손실 시나리오가 일어나지 않아야 하는 최소 결합확률.

    가장 보수적인(최악의) 이익 시나리오 금액을 기준으로,
    p*min_profit - (1-p)*loss_magnitude = 0 을 만족하는 p를 구한다.
    """
    if not profit_scenarios:
        raise ValueError("profit_scenarios가 비어 있습니다")
    worst_profit = min(profit_scenarios)
    if worst_profit <= 0:
        # 최악의 이익 시나리오조차 이익이 아니면(구조 오류), 100% 필요하다고 간주
        return 1.0
    return loss_magnitude / (worst_profit + loss_magnitude)


def calc_draw_dnb0_stakes(odds_draw: float, odds_dnb: float, target_profit: float) -> dict:
    """조합: 무승부(A) + 정배팀 DNB/AH0(B). 무승부 시 B는 push(환급).

    - 무승부: A 적중, B push → 순이익 = target_profit (구성상 정확히 일치)
    - 정배승: A 실패(-stake_A), B 적중 → 순이익 = target_profit (구성상 정확히 일치)
    - 역배승: A, B 모두 실패 → 손실 = -(stake_A + stake_B)
    """
    if odds_draw <= 1 or odds_dnb <= 1:
        raise ValueError("오즈는 1보다 커야 합니다")
    if target_profit <= 0:
        raise ValueError("target_profit은 0보다 커야 합니다")

    stake_draw = target_profit / (odds_draw - 1)
    stake_dnb = (target_profit + stake_draw) / (odds_dnb - 1)
    total_stake = stake_draw + stake_dnb

    profit_draw = stake_draw * (odds_draw - 1)
    profit_home_win = stake_dnb * (odds_dnb - 1) - stake_draw
    loss_away_win = -(stake_draw + stake_dnb)

    breakeven_prob = _breakeven_prob([profit_draw, profit_home_win], total_stake)

    return {
        "combo_type": "draw_dnb0",
        "stake_draw": stake_draw,
        "stake_dnb": stake_dnb,
        "total_stake": total_stake,
        "target_profit": target_profit,
        "profit_draw": profit_draw,
        "profit_home_win": profit_home_win,
        "loss_away_win": loss_away_win,
        "breakeven_prob": breakeven_prob,
        "all_scenarios": {
            "draw": {"leg_a": "win", "leg_b": "push", "net_profit": profit_draw},
            "home_win": {"leg_a": "lose", "leg_b": "win", "net_profit": profit_home_win},
            "away_win": {"leg_a": "lose", "leg_b": "lose", "net_profit": loss_away_win},
        },
    }


def calc_draw_ah05_stakes(odds_draw: float, odds_ah05: float, target_profit: float) -> dict:
    """조합: 무승부(A) + 정배팀 AH-0.5(B). push 없음(반골 라인).

    두 다리 모두 상대 다리의 손실을 상쇄해주지 않는 순수 헤지이므로,
    각 다리는 "자신이 적중했을 때" target_profit을 얻도록 독립적으로 배분된다
    (실제 순이익은 상대 다리 손실이 반영되어 시나리오별로 다를 수 있다 — all_scenarios 참고).
    """
    if odds_draw <= 1 or odds_ah05 <= 1:
        raise ValueError("오즈는 1보다 커야 합니다")
    if target_profit <= 0:
        raise ValueError("target_profit은 0보다 커야 합니다")

    stake_draw = target_profit / (odds_draw - 1)
    stake_ah05 = target_profit / (odds_ah05 - 1)
    total_stake = stake_draw + stake_ah05

    profit_draw = stake_draw * (odds_draw - 1) - stake_ah05
    profit_home_win = stake_ah05 * (odds_ah05 - 1) - stake_draw
    loss_away_win = -(stake_draw + stake_ah05)

    breakeven_prob = _breakeven_prob([profit_draw, profit_home_win], total_stake)

    return {
        "combo_type": "draw_ah05",
        "stake_draw": stake_draw,
        "stake_ah05": stake_ah05,
        "total_stake": total_stake,
        "target_profit": target_profit,
        "profit_draw": profit_draw,
        "profit_home_win": profit_home_win,
        "loss_away_win": loss_away_win,
        "breakeven_prob": breakeven_prob,
        "all_scenarios": {
            "draw": {"leg_a": "win", "leg_b": "lose", "net_profit": profit_draw},
            "home_win": {"leg_a": "lose", "leg_b": "win", "net_profit": profit_home_win},
            "away_win": {"leg_a": "lose", "leg_b": "lose", "net_profit": loss_away_win},
        },
    }


def calc_ahplus1_margin1_stakes(odds_ahplus1: float, odds_margin1: float, target_profit: float) -> dict:
    """조합: 역배팀 AH+1(A) + 정배팀 정확히 1골차 승(B).

    - 역배승/무승부: A 적중, B 실패 → 순이익 = target_profit (구성상 정확히 일치)
    - 정배 1골차승: A push(환급), B 적중 → 순이익 = target_profit (구성상 정확히 일치)
    - 정배 2골차+승: A, B 모두 실패 → 손실 = -(stake_A + stake_B)
    """
    if odds_ahplus1 <= 1 or odds_margin1 <= 1:
        raise ValueError("오즈는 1보다 커야 합니다")
    if target_profit <= 0:
        raise ValueError("target_profit은 0보다 커야 합니다")

    stake_margin1 = target_profit / (odds_margin1 - 1)
    stake_ahplus1 = (target_profit + stake_margin1) / (odds_ahplus1 - 1)
    total_stake = stake_ahplus1 + stake_margin1

    profit_underdog_or_draw = stake_ahplus1 * (odds_ahplus1 - 1) - stake_margin1
    profit_fav_margin1 = stake_margin1 * (odds_margin1 - 1)
    loss_fav_margin2plus = -(stake_ahplus1 + stake_margin1)

    breakeven_prob = _breakeven_prob(
        [profit_underdog_or_draw, profit_fav_margin1], total_stake
    )

    return {
        "combo_type": "ahplus1_margin1",
        "stake_ahplus1": stake_ahplus1,
        "stake_margin1": stake_margin1,
        "total_stake": total_stake,
        "target_profit": target_profit,
        "profit_underdog_or_draw": profit_underdog_or_draw,
        "profit_fav_margin1": profit_fav_margin1,
        "loss_fav_margin2plus": loss_fav_margin2plus,
        "breakeven_prob": breakeven_prob,
        "all_scenarios": {
            "underdog_win_or_draw": {
                "leg_a": "win",
                "leg_b": "lose",
                "net_profit": profit_underdog_or_draw,
            },
            "favorite_margin1": {
                "leg_a": "push",
                "leg_b": "win",
                "net_profit": profit_fav_margin1,
            },
            "favorite_margin2plus": {
                "leg_a": "lose",
                "leg_b": "lose",
                "net_profit": loss_fav_margin2plus,
            },
        },
    }


def calc_ahplus2_margin2_stakes(odds_ahplus2: float, odds_margin2: float, target_profit: float) -> dict:
    """조합: 역배팀 AH+2(A) + 정배팀 정확히 2골차 승(B). ahplus1_margin1과 같은 구조를
    한 골 더 넓힌 버전 — AH+2는 정배 1골차승까지도 커버하므로 이익 시나리오 폭이 더 넓다.

    - 역배승/무승부/정배 1골차승: A 적중(마진<=1은 모두 AH+2가 커버), B 실패 → 순이익 = target_profit
    - 정배 2골차승: A push(환급), B 적중 → 순이익 = target_profit
    - 정배 3골차+승: A, B 모두 실패 → 손실 = -(stake_A + stake_B)
    """
    if odds_ahplus2 <= 1 or odds_margin2 <= 1:
        raise ValueError("오즈는 1보다 커야 합니다")
    if target_profit <= 0:
        raise ValueError("target_profit은 0보다 커야 합니다")

    stake_margin2 = target_profit / (odds_margin2 - 1)
    stake_ahplus2 = (target_profit + stake_margin2) / (odds_ahplus2 - 1)
    total_stake = stake_ahplus2 + stake_margin2

    profit_underdog_draw_or_margin1 = stake_ahplus2 * (odds_ahplus2 - 1) - stake_margin2
    profit_fav_margin2 = stake_margin2 * (odds_margin2 - 1)
    loss_fav_margin3plus = -(stake_ahplus2 + stake_margin2)

    breakeven_prob = _breakeven_prob(
        [profit_underdog_draw_or_margin1, profit_fav_margin2], total_stake
    )

    return {
        "combo_type": "ahplus2_margin2",
        "stake_ahplus2": stake_ahplus2,
        "stake_margin2": stake_margin2,
        "total_stake": total_stake,
        "target_profit": target_profit,
        "profit_underdog_draw_or_margin1": profit_underdog_draw_or_margin1,
        "profit_fav_margin2": profit_fav_margin2,
        "loss_fav_margin3plus": loss_fav_margin3plus,
        "breakeven_prob": breakeven_prob,
        "all_scenarios": {
            "underdog_draw_or_margin1": {
                "leg_a": "win",
                "leg_b": "lose",
                "net_profit": profit_underdog_draw_or_margin1,
            },
            "favorite_margin2": {
                "leg_a": "push",
                "leg_b": "win",
                "net_profit": profit_fav_margin2,
            },
            "favorite_margin3plus": {
                "leg_a": "lose",
                "leg_b": "lose",
                "net_profit": loss_fav_margin3plus,
            },
        },
    }


COMBO_CALCULATORS = {
    "draw_dnb0": calc_draw_dnb0_stakes,
    "draw_ah05": calc_draw_ah05_stakes,
    "draw_ah15": calc_draw_ah05_stakes,  # 수식은 라인 값과 무관하게 동일하게 성립
    "ahplus1_margin1": calc_ahplus1_margin1_stakes,
    "ahplus2_margin2": calc_ahplus2_margin2_stakes,
}


def first_leg_stake(staking: dict) -> float:
    """calc_* 결과 dict에서 다리 A(첫 번째)의 스테이크를 이름에 상관없이 뽑아낸다."""
    stake_keys = [k for k in staking if k.startswith("stake_")]
    return staking[stake_keys[0]]


def second_leg_stake(staking: dict) -> float:
    """calc_* 결과 dict에서 다리 B(두 번째)의 스테이크를 이름에 상관없이 뽑아낸다."""
    stake_keys = [k for k in staking if k.startswith("stake_")]
    return staking[stake_keys[1]]


def target_profit_for_total_stake(calc_fn, odds_a: float, odds_b: float, total_stake: float) -> float:
    """target_profit에 대해 선형(동차)인 성질을 이용해, 원하는 total_stake에
    맞는 target_profit을 역산한다 (baseline target_profit=1.0으로 비율 계산)."""
    baseline = calc_fn(odds_a, odds_b, 1.0)
    if baseline["total_stake"] <= 0:
        raise ValueError("유효하지 않은 오즈 조합입니다")
    return total_stake / baseline["total_stake"]
