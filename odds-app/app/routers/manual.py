from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.datastructures import FormData

from app.db import get_db
from app.models.fixture import Fixture
from app.services.manual_entry import (
    ManualOddsInput,
    create_manual_fixture,
    load_manual_form_data,
    save_manual_odds,
    update_manual_fixture_info,
)
from app.templating import templates

router = APIRouter()

_OPTIONAL_ODDS_FIELDS = [
    "odds_dnb_home", "odds_dnb_away",
    "odds_ah05_favorite", "odds_ah05_underdog",
    "odds_ah1_favorite", "odds_ah1_underdog",
    "odds_ah15_favorite", "odds_ah15_underdog",
    "odds_ah2_favorite", "odds_ah2_underdog",
    "margin_home_by1", "margin_home_by2", "margin_home_by3", "margin_home_by4plus",
    "margin_draw",
    "margin_away_by1", "margin_away_by2", "margin_away_by3", "margin_away_by4plus",
]


def _to_float(value: str | None) -> float | None:
    """빈 문자열(폼에서 비워둔 선택 입력 필드)을 None으로 취급해 파싱한다."""
    if value is None or value.strip() == "":
        return None
    return float(value)


def _empty_form_data() -> dict:
    data = {k: None for k in _OPTIONAL_ODDS_FIELDS}
    data.update({"odds_1x2_home": None, "odds_1x2_draw": None, "odds_1x2_away": None, "favorite_team": "home"})
    return data


def _parse_manual_odds_input(form: FormData) -> ManualOddsInput:
    kwargs = {field: _to_float(form.get(field)) for field in _OPTIONAL_ODDS_FIELDS}
    return ManualOddsInput(
        odds_1x2_home=float(form["odds_1x2_home"]),
        odds_1x2_draw=float(form["odds_1x2_draw"]),
        odds_1x2_away=float(form["odds_1x2_away"]),
        favorite_team=form.get("favorite_team"),
        **kwargs,
    )


@router.get("/manual", response_class=HTMLResponse)
def manual_list(request: Request, db: Session = Depends(get_db)):
    fixtures = (
        db.query(Fixture)
        .filter(Fixture.source == "manual")
        .order_by(Fixture.kickoff_utc.desc())
        .all()
    )
    return templates.TemplateResponse(request, "manual_list.html", {"fixtures": fixtures})


@router.get("/manual/new", response_class=HTMLResponse)
def manual_new_form(request: Request):
    return templates.TemplateResponse(
        request,
        "manual_form.html",
        {"fixture": None, "form": _empty_form_data(), "error": None},
    )


@router.post("/manual/new", response_class=HTMLResponse)
async def manual_new_submit(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    home_team = form["home_team"]
    away_team = form["away_team"]
    league_name = form.get("league_name", "")

    try:
        kickoff = datetime.fromisoformat(form["kickoff_utc"])
        odds_data = _parse_manual_odds_input(form)
    except (ValueError, KeyError):
        return templates.TemplateResponse(
            request,
            "manual_form.html",
            {"fixture": None, "form": _empty_form_data(), "error": "입력값을 확인해주세요 (필수 항목 누락 또는 형식 오류)"},
        )

    fixture = create_manual_fixture(db, home_team, away_team, league_name, kickoff)
    save_manual_odds(db, fixture.id, odds_data)
    return RedirectResponse(url=f"/fixtures/{fixture.id}", status_code=303)


@router.get("/manual/{fixture_id}/edit", response_class=HTMLResponse)
def manual_edit_form(fixture_id: int, request: Request, db: Session = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id, Fixture.source == "manual").one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="수동 입력 경기를 찾을 수 없습니다")

    form_data = load_manual_form_data(db, fixture_id)
    return templates.TemplateResponse(
        request, "manual_form.html", {"fixture": fixture, "form": form_data, "error": None}
    )


@router.post("/manual/{fixture_id}/edit", response_class=HTMLResponse)
async def manual_edit_submit(fixture_id: int, request: Request, db: Session = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id, Fixture.source == "manual").one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="수동 입력 경기를 찾을 수 없습니다")

    form = await request.form()
    home_team = form["home_team"]
    away_team = form["away_team"]
    league_name = form.get("league_name", "")

    try:
        kickoff = datetime.fromisoformat(form["kickoff_utc"])
        odds_data = _parse_manual_odds_input(form)
    except (ValueError, KeyError):
        form_data = load_manual_form_data(db, fixture_id)
        return templates.TemplateResponse(
            request,
            "manual_form.html",
            {"fixture": fixture, "form": form_data, "error": "입력값을 확인해주세요 (필수 항목 누락 또는 형식 오류)"},
        )

    update_manual_fixture_info(fixture, home_team, away_team, league_name, kickoff)
    save_manual_odds(db, fixture.id, odds_data)
    return RedirectResponse(url=f"/fixtures/{fixture.id}", status_code=303)


@router.post("/manual/{fixture_id}/delete")
def manual_delete(fixture_id: int, db: Session = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id, Fixture.source == "manual").one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="수동 입력 경기를 찾을 수 없습니다")
    db.delete(fixture)
    db.commit()
    return RedirectResponse(url="/manual", status_code=303)
