"""저장된 픽(Pick)을 실제 최종 스코어로 채점한다.

핵심 원칙: 스테이크/오즈/목표이익은 저장 시점에 이미 고정돼 있으므로,
staking.py의 동일한 계산 함수를 다시 호출해 all_scenarios를 재구성하고,
실제 스코어가 그중 어느 시나리오에 해당하는지만 판정한다 — 즉 손익 계산
로직은 단 한 곳(staking.py)에만 존재하고, 여기서는 "어느 시나리오가
발생했는가"만 결정한다.
"""
from __future__ import annotations

from app.models.pick import Pick
from app.services.staking import COMBO_CALCULATORS


def _margin_for(favorite_side: str, home_score: int, away_score: int) -> int:
    """정배팀 골 마진 (양수: 정배팀이 이긴 골차, 0: 무승부, 음수: 정배팀이 짐)."""
    if favorite_side == "home":
        return home_score - away_score
    return away_score - home_score


def determine_scenario(pick: Pick, home_score: int, away_score: int) -> str:
    margin = _margin_for(pick.favorite_side, home_score, away_score)

    if pick.combo_type in ("draw_dnb0", "draw_ah05"):
        # DNB/AH-0.5는 정배팀이 "1골차 이상"만 이기면 다리 B가 적중한다.
        if home_score == away_score:
            return "draw"
        return "home_win" if margin >= 1 else "away_win"

    if pick.combo_type == "draw_ah15":
        # AH-1.5는 정배팀이 "2골차 이상" 이겨야 다리 B가 적중한다(1골차 승은
        # 핸디캡을 못 넘겨 다리 B도 실패 — away_win과 동일한 손실로 묶인다).
        if home_score == away_score:
            return "draw"
        return "home_win" if margin >= 2 else "away_win"

    if pick.combo_type == "ahplus1_margin1":
        if margin <= 0:
            return "underdog_win_or_draw"
        if margin == 1:
            return "favorite_margin1"
        return "favorite_margin2plus"

    if pick.combo_type == "ahplus2_margin2":
        if margin <= 1:
            return "underdog_draw_or_margin1"
        if margin == 2:
            return "favorite_margin2"
        return "favorite_margin3plus"

    raise ValueError(f"알 수 없는 combo_type: {pick.combo_type}")


def grade_pick(pick: Pick, home_score: int, away_score: int) -> dict:
    """스코어를 받아 (scenario, net_profit)을 반환한다. Pick을 직접 수정하지 않는다."""
    calc_fn = COMBO_CALCULATORS[pick.combo_type]
    staking = calc_fn(float(pick.odds_leg_a), float(pick.odds_leg_b), float(pick.target_profit))

    scenario = determine_scenario(pick, home_score, away_score)
    net_profit = staking["all_scenarios"][scenario]["net_profit"]

    return {"scenario": scenario, "net_profit": net_profit}
