from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.fixture import Fixture
from app.models.market import Market
from app.models.odds import Odds
from app.services.combo_engine import compute_and_cache_combos
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
def fixture_detail(fixture_id: int, request: Request, db: Session = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="fixture를 찾을 수 없습니다")

    # 최신 마켓(북메이커별, market_type+line별 가장 최근 fetched_at)만 표시
    subq = (
        db.query(
            Market.market_type,
            Market.line,
            Market.bookmaker,
            func.max(Market.fetched_at).label("max_fetched_at"),
        )
        .filter(Market.fixture_id == fixture_id)
        .group_by(Market.market_type, Market.line, Market.bookmaker)
        .subquery()
    )
    latest_markets = (
        db.query(Market)
        .join(
            subq,
            (Market.market_type == subq.c.market_type)
            & (Market.line == subq.c.line)
            & (Market.bookmaker == subq.c.bookmaker)
            & (Market.fetched_at == subq.c.max_fetched_at),
        )
        .filter(Market.fixture_id == fixture_id)
        .order_by(Market.market_type, Market.line, Market.bookmaker)
        .all()
    )

    markets_with_odds = []
    for m in latest_markets:
        odds_rows = db.query(Odds).filter(Odds.market_id == m.id).order_by(Odds.selection).all()
        markets_with_odds.append({"market": m, "odds": odds_rows})

    combos = compute_and_cache_combos(db, fixture)

    return templates.TemplateResponse(
        request,
        "fixture_detail.html",
        {
            "fixture": fixture,
            "markets_with_odds": markets_with_odds,
            "combos": combos,
        },
    )
