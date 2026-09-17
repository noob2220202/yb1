from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

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


def _to_float(value: str | None) -> float | None:
    """빈 문자열(폼에서 비워둔 선택 입력 필드)을 None으로 취급해 파싱한다."""
    if value is None or value.strip() == "":
        return None
    return float(value)


def _empty_form_data() -> dict:
    return {
        "odds_1x2_home": None, "odds_1x2_draw": None, "odds_1x2_away": None,
        "odds_dnb_home": None, "odds_dnb_away": None,
        "favorite_team": "home",
        "odds_ah05_favorite": None, "odds_ah05_underdog": None,
        "odds_ah1_favorite": None, "odds_ah1_underdog": None,
        "margin_home_by1": None, "margin_home_by2plus": None, "margin_draw": None,
        "margin_away_by1": None, "margin_away_by2plus": None,
    }


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
def manual_new_submit(
    request: Request,
    db: Session = Depends(get_db),
    home_team: str = Form(...),
    away_team: str = Form(...),
    league_name: str = Form(""),
    kickoff_utc: str = Form(...),
    odds_1x2_home: float = Form(...),
    odds_1x2_draw: float = Form(...),
    odds_1x2_away: float = Form(...),
    odds_dnb_home: str | None = Form(None),
    odds_dnb_away: str | None = Form(None),
    favorite_team: str | None = Form(None),
    odds_ah05_favorite: str | None = Form(None),
    odds_ah05_underdog: str | None = Form(None),
    odds_ah1_favorite: str | None = Form(None),
    odds_ah1_underdog: str | None = Form(None),
    margin_home_by1: str | None = Form(None),
    margin_home_by2plus: str | None = Form(None),
    margin_draw: str | None = Form(None),
    margin_away_by1: str | None = Form(None),
    margin_away_by2plus: str | None = Form(None),
):
    try:
        kickoff = datetime.fromisoformat(kickoff_utc)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "manual_form.html",
            {"fixture": None, "form": _empty_form_data(), "error": "킥오프 일시 형식이 올바르지 않습니다"},
        )

    fixture = create_manual_fixture(db, home_team, away_team, league_name, kickoff)
    save_manual_odds(
        db,
        fixture.id,
        ManualOddsInput(
            odds_1x2_home=odds_1x2_home, odds_1x2_draw=odds_1x2_draw, odds_1x2_away=odds_1x2_away,
            odds_dnb_home=_to_float(odds_dnb_home), odds_dnb_away=_to_float(odds_dnb_away),
            favorite_team=favorite_team,
            odds_ah05_favorite=_to_float(odds_ah05_favorite), odds_ah05_underdog=_to_float(odds_ah05_underdog),
            odds_ah1_favorite=_to_float(odds_ah1_favorite), odds_ah1_underdog=_to_float(odds_ah1_underdog),
            margin_home_by1=_to_float(margin_home_by1), margin_home_by2plus=_to_float(margin_home_by2plus),
            margin_draw=_to_float(margin_draw),
            margin_away_by1=_to_float(margin_away_by1), margin_away_by2plus=_to_float(margin_away_by2plus),
        ),
    )
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
def manual_edit_submit(
    fixture_id: int,
    request: Request,
    db: Session = Depends(get_db),
    home_team: str = Form(...),
    away_team: str = Form(...),
    league_name: str = Form(""),
    kickoff_utc: str = Form(...),
    odds_1x2_home: float = Form(...),
    odds_1x2_draw: float = Form(...),
    odds_1x2_away: float = Form(...),
    odds_dnb_home: str | None = Form(None),
    odds_dnb_away: str | None = Form(None),
    favorite_team: str | None = Form(None),
    odds_ah05_favorite: str | None = Form(None),
    odds_ah05_underdog: str | None = Form(None),
    odds_ah1_favorite: str | None = Form(None),
    odds_ah1_underdog: str | None = Form(None),
    margin_home_by1: str | None = Form(None),
    margin_home_by2plus: str | None = Form(None),
    margin_draw: str | None = Form(None),
    margin_away_by1: str | None = Form(None),
    margin_away_by2plus: str | None = Form(None),
):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id, Fixture.source == "manual").one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="수동 입력 경기를 찾을 수 없습니다")

    try:
        kickoff = datetime.fromisoformat(kickoff_utc)
    except ValueError:
        form_data = load_manual_form_data(db, fixture_id)
        return templates.TemplateResponse(
            request,
            "manual_form.html",
            {"fixture": fixture, "form": form_data, "error": "킥오프 일시 형식이 올바르지 않습니다"},
        )

    update_manual_fixture_info(fixture, home_team, away_team, league_name, kickoff)
    save_manual_odds(
        db,
        fixture.id,
        ManualOddsInput(
            odds_1x2_home=odds_1x2_home, odds_1x2_draw=odds_1x2_draw, odds_1x2_away=odds_1x2_away,
            odds_dnb_home=_to_float(odds_dnb_home), odds_dnb_away=_to_float(odds_dnb_away),
            favorite_team=favorite_team,
            odds_ah05_favorite=_to_float(odds_ah05_favorite), odds_ah05_underdog=_to_float(odds_ah05_underdog),
            odds_ah1_favorite=_to_float(odds_ah1_favorite), odds_ah1_underdog=_to_float(odds_ah1_underdog),
            margin_home_by1=_to_float(margin_home_by1), margin_home_by2plus=_to_float(margin_home_by2plus),
            margin_draw=_to_float(margin_draw),
            margin_away_by1=_to_float(margin_away_by1), margin_away_by2plus=_to_float(margin_away_by2plus),
        ),
    )
    return RedirectResponse(url=f"/fixtures/{fixture.id}", status_code=303)


@router.post("/manual/{fixture_id}/delete")
def manual_delete(fixture_id: int, db: Session = Depends(get_db)):
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id, Fixture.source == "manual").one_or_none()
    if fixture is None:
        raise HTTPException(status_code=404, detail="수동 입력 경기를 찾을 수 없습니다")
    db.delete(fixture)
    db.commit()
    return RedirectResponse(url="/manual", status_code=303)
