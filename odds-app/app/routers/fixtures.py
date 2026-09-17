from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from app.services.combo_engine import compute_and_cache_combos
from app.services.pick_service import save_pick
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, league: str | None = None, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=48)

    query = db.query(Fixture).filter(
        Fixture.kickoff_utc >= now,
        Fixture.kickoff_utc <= horizon,
        Fixture.status == "scheduled",
        Fixture.source == "api",
    )
    if league:
        query = query.filter(Fixture.league_name == league)
    fixture_list = query.order_by(Fixture.kickoff_utc.asc()).all()

    leagues = [row[0] for row in db.query(Fixture.league_name).distinct().order_by(Fixture.league_name)]

    fixture_ids = [f.id for f in fixture_list]
    combo_fixture_ids: set[int] = set()
    if fixture_ids:
        from app.models.combo import ComboRecommendation

        rows = (
            db.query(ComboRecommendation.fixture_id)
            .filter(ComboRecommendation.fixture_id.in_(fixture_ids))
            .distinct()
            .all()
        )
        combo_fixture_ids = {r[0] for r in rows}

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "fixtures": fixture_list,
            "leagues": leagues,
            "selected_league": league,
            "combo_fixture_ids": combo_fixture_ids,
        },
    )


@router.get("/fixtures/{fixture_id}", response_class=HTMLResponse)
def fixture_detail(
    fixture_id: int, request: Request, total_stake: float | None = None, db: Session = Depends(get_db)
):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="fixture를 찾을 수 없습니다")

    effective_total_stake = total_stake if total_stake and total_stake > 0 else settings.default_total_stake

    # 최신 마켓(북메이커별, market_type+line별 가장 최근 fetched_at)만 표시.
    # SQL JOIN으로 line을 비교하면 NULL=NULL이 항상 거짓이라 1X2/DNB/승리마진처럼
    # line이 없는 마켓이 전부 누락되므로, 그룹핑은 파이썬에서 처리한다.
    all_markets = (
        db.query(Market)
        .filter(Market.fixture_id == fixture_id)
        .order_by(Market.market_type, Market.line, Market.bookmaker)
        .all()
    )
    latest_by_group: dict[tuple, Market] = {}
    for m in all_markets:
        key = (m.market_type, m.line, m.bookmaker)
        current = latest_by_group.get(key)
        if current is None or m.fetched_at > current.fetched_at:
            latest_by_group[key] = m
    latest_markets = sorted(
        latest_by_group.values(), key=lambda m: (m.market_type, m.line or 0, m.bookmaker)
    )

    markets_with_odds = []
    for m in latest_markets:
        odds_rows = db.query(Odds).filter(Odds.market_id == m.id).order_by(Odds.selection).all()
        markets_with_odds.append({"market": m, "odds": odds_rows})

    combos = compute_and_cache_combos(db, fixture, total_stake=effective_total_stake)

    return templates.TemplateResponse(
        request,
        "fixture_detail.html",
        {
            "fixture": fixture,
            "markets_with_odds": markets_with_odds,
            "combos": combos,
            "total_stake": effective_total_stake,
        },
    )


@router.post("/fixtures/{fixture_id}/picks")
def save_pick_from_fixture(
    fixture_id: int,
    db: Session = Depends(get_db),
    combo_type: str = Form(...),
    description: str = Form(...),
    leg_a_selection: str = Form(...),
    leg_b_selection: str = Form(...),
    favorite_side: str = Form(...),
    odds_leg_a: float = Form(...),
    odds_leg_b: float = Form(...),
    stake_leg_a: float = Form(...),
    stake_leg_b: float = Form(...),
    total_stake: float = Form(...),
    target_profit: float = Form(...),
    implied_hit_rate: float = Form(...),
    breakeven_prob: float = Form(...),
    estimated_ev_pct: float = Form(...),
    comment: str = Form(""),
):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="fixture를 찾을 수 없습니다")

    save_pick(
        db,
        fixture_id=fixture.id,
        home_team=fixture.home_team,
        away_team=fixture.away_team,
        combo_type=combo_type,
        description=description,
        leg_a_selection=leg_a_selection,
        leg_b_selection=leg_b_selection,
        favorite_side=favorite_side,
        odds_leg_a=odds_leg_a,
        odds_leg_b=odds_leg_b,
        stake_leg_a=stake_leg_a,
        stake_leg_b=stake_leg_b,
        total_stake=total_stake,
        target_profit=target_profit,
        implied_hit_rate=implied_hit_rate,
        breakeven_prob=breakeven_prob,
        estimated_ev_pct=estimated_ev_pct,
        comment=comment or None,
    )
    return RedirectResponse(url=f"/fixtures/{fixture_id}?saved=1", status_code=303)
