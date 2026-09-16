"""수동 오즈 입력 서비스.

API 키 없이도 사용자가 직접 마켓 오즈를 입력해 combo_engine을 그대로 사용할 수
있도록 한다. 조합 계산에 실제로 쓰이는 최소 마켓만 지원한다:

- 1X2 (필수)
- 무승부무효(DNB)
- 아시안 핸디캡 -0.5/+0.5
- 아시안 핸디캡 -1/+1
- 승리마진(홈 1골차/홈 2골차+/무승부/원정 1골차/원정 2골차+) — 5구간 합이
  전체 확률 공간을 이루도록 해 devig 정확도를 확보한다.

핸디캡 라인은 "어느 팀이 정배(마이너스 라인)인지"에 따라 부호가 달라지므로,
두 핸디캡 마켓 모두 공통 `favorite_team`(홈/원정) 값을 기준으로 저장한다
(한 경기 안에서 -0.5/-1 라인의 정배팀은 항상 같다고 가정).

수동 입력은 "덮어쓰기" 방식이다 — 저장할 때마다 기존 manual 마켓을 지우고
새로 넣는다 (자동 수집과 달리 시계열 이력을 남기지 않는다).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.combo import ComboRecommendation
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds

MANUAL_BOOKMAKER = "manual"


@dataclass
class ManualOddsInput:
    odds_1x2_home: float | None
    odds_1x2_draw: float | None
    odds_1x2_away: float | None
    odds_dnb_home: float | None = None
    odds_dnb_away: float | None = None
    favorite_team: str | None = None  # "home" | "away" — 두 핸디캡 마켓 공통
    odds_ah05_favorite: float | None = None
    odds_ah05_underdog: float | None = None
    odds_ah1_favorite: float | None = None
    odds_ah1_underdog: float | None = None
    margin_home_by1: float | None = None
    margin_home_by2plus: float | None = None
    margin_draw: float | None = None
    margin_away_by1: float | None = None
    margin_away_by2plus: float | None = None


def create_manual_fixture(
    db: Session, home_team: str, away_team: str, league_name: str | None, kickoff_utc: datetime
) -> Fixture:
    fixture = Fixture(
        external_id=f"manual-{uuid.uuid4().hex}",
        league_id=0,
        league_name=league_name or "수동 입력",
        home_team=home_team,
        away_team=away_team,
        kickoff_utc=kickoff_utc,
        status="scheduled",
        source="manual",
    )
    db.add(fixture)
    db.flush()
    return fixture


def update_manual_fixture_info(
    fixture: Fixture, home_team: str, away_team: str, league_name: str | None, kickoff_utc: datetime
) -> None:
    fixture.home_team = home_team
    fixture.away_team = away_team
    fixture.league_name = league_name or "수동 입력"
    fixture.kickoff_utc = kickoff_utc


def _clear_manual_odds(db: Session, fixture_id: int) -> None:
    # combo_recommendations 캐시가 기존 market row를 FK로 참조하므로 먼저 지운다
    # (fixture_detail 페이지를 다시 열면 compute_and_cache_combos가 새로 채운다).
    db.query(ComboRecommendation).filter(
        ComboRecommendation.fixture_id == fixture_id
    ).delete(synchronize_session=False)
    db.query(Market).filter(
        Market.fixture_id == fixture_id, Market.bookmaker == MANUAL_BOOKMAKER
    ).delete(synchronize_session=False)


def _add_market(
    db: Session, fixture_id: int, market_type: str, line: Decimal | None, selections: dict[str, float | None]
) -> None:
    values = {k: v for k, v in selections.items() if v is not None}
    if not values:
        return
    market = Market(fixture_id=fixture_id, market_type=market_type, line=line, bookmaker=MANUAL_BOOKMAKER)
    db.add(market)
    db.flush()
    for selection, odds in values.items():
        db.add(Odds(market_id=market.id, selection=selection, decimal_odds=Decimal(str(odds))))


def save_manual_odds(db: Session, fixture_id: int, data: ManualOddsInput) -> None:
    _clear_manual_odds(db, fixture_id)
    db.flush()

    _add_market(
        db, fixture_id, "1x2", None,
        {"home": data.odds_1x2_home, "draw": data.odds_1x2_draw, "away": data.odds_1x2_away},
    )
    _add_market(
        db, fixture_id, "dnb", None,
        {"home": data.odds_dnb_home, "away": data.odds_dnb_away},
    )

    favorite = data.favorite_team if data.favorite_team in ("home", "away") else None
    if favorite is not None:
        underdog = "away" if favorite == "home" else "home"
        line_05 = Decimal("-0.5") if favorite == "home" else Decimal("0.5")
        _add_market(
            db, fixture_id, "ah", line_05,
            {favorite: data.odds_ah05_favorite, underdog: data.odds_ah05_underdog},
        )
        line_1 = Decimal("-1") if favorite == "home" else Decimal("1")
        _add_market(
            db, fixture_id, "ah", line_1,
            {favorite: data.odds_ah1_favorite, underdog: data.odds_ah1_underdog},
        )

    _add_market(
        db, fixture_id, "win_margin", None,
        {
            "home_by_1": data.margin_home_by1,
            "home_by_2plus": data.margin_home_by2plus,
            "draw": data.margin_draw,
            "away_by_1": data.margin_away_by1,
            "away_by_2plus": data.margin_away_by2plus,
        },
    )

    db.commit()


def load_manual_form_data(db: Session, fixture_id: int) -> dict:
    """편집 화면에 기존 입력값을 미리 채우기 위한 로더."""
    result: dict = {
        "odds_1x2_home": None, "odds_1x2_draw": None, "odds_1x2_away": None,
        "odds_dnb_home": None, "odds_dnb_away": None,
        "favorite_team": "home",
        "odds_ah05_favorite": None, "odds_ah05_underdog": None,
        "odds_ah1_favorite": None, "odds_ah1_underdog": None,
        "margin_home_by1": None, "margin_home_by2plus": None, "margin_draw": None,
        "margin_away_by1": None, "margin_away_by2plus": None,
    }
    markets = (
        db.query(Market)
        .filter(Market.fixture_id == fixture_id, Market.bookmaker == MANUAL_BOOKMAKER)
        .all()
    )
    for m in markets:
        odds_rows = db.query(Odds).filter(Odds.market_id == m.id).all()
        by_sel = {o.selection: float(o.decimal_odds) for o in odds_rows}

        if m.market_type == "1x2":
            result["odds_1x2_home"] = by_sel.get("home")
            result["odds_1x2_draw"] = by_sel.get("draw")
            result["odds_1x2_away"] = by_sel.get("away")
        elif m.market_type == "dnb":
            result["odds_dnb_home"] = by_sel.get("home")
            result["odds_dnb_away"] = by_sel.get("away")
        elif m.market_type == "ah":
            line = float(m.line) if m.line is not None else None
            if line in (-0.5, 0.5):
                favorite = "home" if line == -0.5 else "away"
                underdog = "away" if favorite == "home" else "home"
                result["favorite_team"] = favorite
                result["odds_ah05_favorite"] = by_sel.get(favorite)
                result["odds_ah05_underdog"] = by_sel.get(underdog)
            elif line in (-1.0, 1.0):
                favorite = "home" if line == -1.0 else "away"
                underdog = "away" if favorite == "home" else "home"
                result["favorite_team"] = favorite
                result["odds_ah1_favorite"] = by_sel.get(favorite)
                result["odds_ah1_underdog"] = by_sel.get(underdog)
        elif m.market_type == "win_margin":
            result["margin_home_by1"] = by_sel.get("home_by_1")
            result["margin_home_by2plus"] = by_sel.get("home_by_2plus")
            result["margin_draw"] = by_sel.get("draw")
            result["margin_away_by1"] = by_sel.get("away_by_1")
            result["margin_away_by2plus"] = by_sel.get("away_by_2plus")

    return result
