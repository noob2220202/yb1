"""조합 생성/랭킹 엔진.

한 fixture의 최신 오즈를 로드해, 사전 정의된 두-다리 조합(combo_type) 후보를
생성하고 각 후보의 스테이크 배분·적중확률·EV를 계산한다.

절대 금지 사항 (SPEC.md 8.2절):
- 자동 스테이크 증액/마틴게일 로직 없음.
- 손실추격(loss-chasing) 자동화 없음.
- 모든 결과에 고정 안내 문구(STAKING_DISCLAIMER)를 포함해야 하며, EV가 음수여도
  리스트에서 숨기지 않는다 — "⚠ 마이너스 EV" 표시만 붙인다.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.combo import ComboRecommendation
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from app.services.devig import calc_ev, consensus_probability, devig_market
from app.services.staking import (
    STAKING_DISCLAIMER,
    calc_ahplus1_margin1_stakes,
    calc_draw_ah05_stakes,
    calc_draw_dnb0_stakes,
    first_leg_stake,
    second_leg_stake,
    target_profit_for_total_stake,
)


def _latest_markets(db: Session, fixture_id: int, market_type: str, line: float | None = None) -> list[Market]:
    q = db.query(Market).filter(Market.fixture_id == fixture_id, Market.market_type == market_type)
    if line is None:
        q = q.filter(Market.line.is_(None))
    else:
        q = q.filter(Market.line == line)
    markets = q.all()

    latest_by_bookmaker: dict[str, Market] = {}
    for m in markets:
        cur = latest_by_bookmaker.get(m.bookmaker)
        if cur is None or m.fetched_at > cur.fetched_at:
            latest_by_bookmaker[m.bookmaker] = m
    return list(latest_by_bookmaker.values())


def consensus_probs_for_market(db: Session, fixture_id: int, market_type: str, line: float | None = None) -> dict[str, float]:
    """market_type(+line)의 최신 북메이커별 오즈를 devig해 셀렉션별 컨센서스 확률로 평균."""
    markets = _latest_markets(db, fixture_id, market_type, line)
    per_selection: dict[str, list[float]] = {}
    for market in markets:
        odds_rows = db.query(Odds).filter(Odds.market_id == market.id).all()
        if not odds_rows:
            continue
        selections = [o.selection for o in odds_rows]
        values = [float(o.decimal_odds) for o in odds_rows]
        try:
            probs = devig_market(market_type, values)
        except ValueError:
            continue
        for sel, p in zip(selections, probs):
            per_selection.setdefault(sel, []).append(p)
    return {sel: consensus_probability(probs) for sel, probs in per_selection.items()}


def best_odds_for_selection(
    db: Session, fixture_id: int, market_type: str, selection: str, line: float | None = None
) -> tuple[float | None, Market | None]:
    """조합 계산에 사용할 대표 오즈 — 최신 오즈 중 최댓값(best available)."""
    markets = _latest_markets(db, fixture_id, market_type, line)
    best_odds: float | None = None
    best_market: Market | None = None
    for market in markets:
        row = (
            db.query(Odds)
            .filter(Odds.market_id == market.id, Odds.selection == selection)
            .one_or_none()
        )
        if row is not None and (best_odds is None or float(row.decimal_odds) > best_odds):
            best_odds = float(row.decimal_odds)
            best_market = market
    return best_odds, best_market


def _combo_ev_pct(
    stake_a: float, odds_a: float, prob_a: float, stake_b: float, odds_b: float, prob_b: float
) -> float:
    ev_a = calc_ev(stake_a, odds_a, prob_a)
    ev_b = calc_ev(stake_b, odds_b, prob_b)
    total_stake = stake_a + stake_b
    if total_stake <= 0:
        return 0.0
    return (ev_a + ev_b) / total_stake * 100


def generate_combo_candidates(db: Session, fixture: Fixture, total_stake: float | None = None) -> list[dict]:
    total_stake = total_stake or settings.default_total_stake
    candidates: list[dict] = []

    probs_1x2 = consensus_probs_for_market(db, fixture.id, "1x2")
    if not {"home", "draw", "away"} <= probs_1x2.keys():
        return candidates  # 1X2 데이터가 없으면 어떤 조합도 만들 수 없음

    favorite = "home" if probs_1x2["home"] >= probs_1x2["away"] else "away"
    underdog = "away" if favorite == "home" else "home"

    odds_draw, market_draw = best_odds_for_selection(db, fixture.id, "1x2", "draw")

    # --- draw_dnb0: 무승부 + 정배팀 DNB ---
    odds_dnb, market_dnb = best_odds_for_selection(db, fixture.id, "dnb", favorite)
    dnb_probs = consensus_probs_for_market(db, fixture.id, "dnb")
    if odds_draw and odds_dnb and favorite in dnb_probs:
        try:
            target_profit = target_profit_for_total_stake(calc_draw_dnb0_stakes, odds_draw, odds_dnb, total_stake)
            staking = calc_draw_dnb0_stakes(odds_draw, odds_dnb, target_profit)
            implied_hit_rate = 1 - probs_1x2[underdog]
            ev_pct = _combo_ev_pct(
                staking["stake_draw"], odds_draw, probs_1x2["draw"],
                staking["stake_dnb"], odds_dnb, dnb_probs[favorite],
            )
            candidates.append(_build_candidate(
                combo_type="draw_dnb0",
                description=f"무승부 + {'홈팀' if favorite == 'home' else '원정팀'} DNB",
                leg_a_market=market_draw, leg_a_selection="draw", odds_leg_a=odds_draw,
                leg_b_market=market_dnb, leg_b_selection=favorite, odds_leg_b=odds_dnb,
                favorite_side=favorite,
                staking=staking, implied_hit_rate=implied_hit_rate, ev_pct=ev_pct,
            ))
        except ValueError:
            pass

    # --- draw_ah05: 무승부 + 정배팀 AH-0.5 ---
    ah05_line = -0.5 if favorite == "home" else 0.5
    odds_ah05, market_ah05 = best_odds_for_selection(db, fixture.id, "ah", favorite, ah05_line)
    ah05_probs = consensus_probs_for_market(db, fixture.id, "ah", ah05_line)
    if odds_draw and odds_ah05 and favorite in ah05_probs:
        try:
            target_profit = target_profit_for_total_stake(calc_draw_ah05_stakes, odds_draw, odds_ah05, total_stake)
            staking = calc_draw_ah05_stakes(odds_draw, odds_ah05, target_profit)
            implied_hit_rate = 1 - probs_1x2[underdog]
            ev_pct = _combo_ev_pct(
                staking["stake_draw"], odds_draw, probs_1x2["draw"],
                staking["stake_ah05"], odds_ah05, ah05_probs[favorite],
            )
            candidates.append(_build_candidate(
                combo_type="draw_ah05",
                description=f"무승부 + {'홈팀' if favorite == 'home' else '원정팀'} AH-0.5",
                leg_a_market=market_draw, leg_a_selection="draw", odds_leg_a=odds_draw,
                leg_b_market=market_ah05, leg_b_selection=favorite, odds_leg_b=odds_ah05,
                favorite_side=favorite,
                staking=staking, implied_hit_rate=implied_hit_rate, ev_pct=ev_pct,
            ))
        except ValueError:
            pass

    # --- ahplus1_margin1: 역배팀 AH+1 + 정배�름 정확히 1골차 승 ---
    ahplus1_line = -1.0 if favorite == "home" else 1.0
    odds_ahplus1, market_ahplus1 = best_odds_for_selection(db, fixture.id, "ah", underdog, ahplus1_line)
    ahplus1_probs = consensus_probs_for_market(db, fixture.id, "ah", ahplus1_line)
    margin1_selection = f"{favorite}_by_1"
    odds_margin1, market_margin1 = best_odds_for_selection(db, fixture.id, "win_margin", margin1_selection)
    margin_probs = consensus_probs_for_market(db, fixture.id, "win_margin")
    if odds_ahplus1 and odds_margin1 and underdog in ahplus1_probs and margin1_selection in margin_probs:
        try:
            target_profit = target_profit_for_total_stake(
                calc_ahplus1_margin1_stakes, odds_ahplus1, odds_margin1, total_stake
            )
            staking = calc_ahplus1_margin1_stakes(odds_ahplus1, odds_margin1, target_profit)
            # 주의: probs_1x2(1X2 마켓)와 margin_probs(승리마진 마켓)는 서로 다른 마켓에서
            # 독립적으로 devig되므로 두 확률을 그대로 더하면 100%를 넘을 수 있다(서로 다른
            # 북메이커 마진이 섞이기 때문). 대신 승리마진 마켓 하나의 분포만으로 계산한다
            # ("정배 2골차+ 승" 버킷들의 합을 1에서 빼는 방식) — 이 분포는 항상 합이 1이 되도록
            # devig되어 있으므로 100%를 넘을 수 없다.
            favorite_prefix = f"{favorite}_by_"
            favorite_margin2plus_prob = sum(
                p for sel, p in margin_probs.items()
                if sel.startswith(favorite_prefix) and sel != margin1_selection
            )
            implied_hit_rate = max(0.0, 1 - favorite_margin2plus_prob)
            ev_pct = _combo_ev_pct(
                staking["stake_ahplus1"], odds_ahplus1, ahplus1_probs[underdog],
                staking["stake_margin1"], odds_margin1, margin_probs[margin1_selection],
            )
            candidates.append(_build_candidate(
                combo_type="ahplus1_margin1",
                description=f"{'원정팀' if favorite == 'home' else '홈팀'} AH+1 + {'홈팀' if favorite == 'home' else '원정팀'} 정확히 1골차 승",
                leg_a_market=market_ahplus1, leg_a_selection=underdog, odds_leg_a=odds_ahplus1,
                leg_b_market=market_margin1, leg_b_selection=margin1_selection, odds_leg_b=odds_margin1,
                favorite_side=favorite,
                staking=staking, implied_hit_rate=implied_hit_rate, ev_pct=ev_pct,
            ))
        except ValueError:
            pass

    candidates.sort(key=lambda c: c["implied_hit_rate"], reverse=True)
    return candidates


def _build_candidate(
    *, combo_type: str, description: str,
    leg_a_market: Market, leg_a_selection: str, odds_leg_a: float,
    leg_b_market: Market, leg_b_selection: str, odds_leg_b: float,
    favorite_side: str, staking: dict, implied_hit_rate: float, ev_pct: float,
) -> dict:
    return {
        "combo_type": combo_type,
        "description": description,
        "leg_a_market_id": leg_a_market.id,
        "leg_a_selection": leg_a_selection,
        "odds_leg_a": odds_leg_a,
        "leg_b_market_id": leg_b_market.id,
        "leg_b_selection": leg_b_selection,
        "odds_leg_b": odds_leg_b,
        "favorite_side": favorite_side,
        "staking": staking,
        "implied_hit_rate": implied_hit_rate,
        "breakeven_prob": staking["breakeven_prob"],
        "estimated_ev_pct": ev_pct,
        "ev_negative": ev_pct < 0,
        "stake_leg_a": first_leg_stake(staking),
        "stake_leg_b": second_leg_stake(staking),
        "total_stake": staking["total_stake"],
        "target_profit": staking["target_profit"],
        "disclaimer": STAKING_DISCLAIMER,
    }


def compute_and_cache_combos(db: Session, fixture: Fixture, total_stake: float | None = None) -> list[dict]:
    """조합 후보를 계산하고 combo_recommendations 테이블에 캐시(기존 캐시는 갱신)."""
    candidates = generate_combo_candidates(db, fixture, total_stake)

    db.query(ComboRecommendation).filter(ComboRecommendation.fixture_id == fixture.id).delete()
    for c in candidates:
        db.add(ComboRecommendation(
            fixture_id=fixture.id,
            leg_a_market_id=c["leg_a_market_id"],
            leg_a_selection=c["leg_a_selection"],
            leg_b_market_id=c["leg_b_market_id"],
            leg_b_selection=c["leg_b_selection"],
            combo_type=c["combo_type"],
            implied_hit_rate=c["implied_hit_rate"],
            breakeven_prob=c["breakeven_prob"],
            estimated_ev_pct=c["estimated_ev_pct"],
            stake_leg_a=c["stake_leg_a"],
            stake_leg_b=c["stake_leg_b"],
            total_stake=c["total_stake"],
            target_profit=c["target_profit"],
        ))
    db.commit()
    return candidates
