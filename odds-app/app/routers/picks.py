from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.pick import Pick
from app.services.pick_service import compute_stats, grade_and_notify
from app.templating import templates

router = APIRouter()


@router.get("/picks", response_class=HTMLResponse)
def picks_list(request: Request, db: Session = Depends(get_db)):
    pending = db.query(Pick).filter(Pick.status == "pending").order_by(Pick.created_at.desc()).all()
    settled = db.query(Pick).filter(Pick.status == "settled").order_by(Pick.settled_at.desc()).all()
    return templates.TemplateResponse(
        request, "picks_list.html", {"pending": pending, "settled": settled}
    )


@router.post("/picks/{pick_id}/grade")
def picks_grade(
    pick_id: int,
    db: Session = Depends(get_db),
    home_score: int = Form(...),
    away_score: int = Form(...),
):
    pick = db.query(Pick).filter(Pick.id == pick_id).one_or_none()
    if pick is None:
        raise HTTPException(status_code=404, detail="픽을 찾을 수 없습니다")
    if pick.status == "settled":
        raise HTTPException(status_code=400, detail="이미 채점된 픽입니다")

    grade_and_notify(db, pick, home_score, away_score)
    return RedirectResponse(url="/picks", status_code=303)


@router.post("/picks/{pick_id}/delete")
def picks_delete(pick_id: int, db: Session = Depends(get_db)):
    pick = db.query(Pick).filter(Pick.id == pick_id).one_or_none()
    if pick is None:
        raise HTTPException(status_code=404, detail="픽을 찾을 수 없습니다")
    db.delete(pick)
    db.commit()
    return RedirectResponse(url="/picks", status_code=303)


@router.get("/stats", response_class=HTMLResponse)
def stats_page(request: Request, db: Session = Depends(get_db)):
    stats = compute_stats(db)
    return templates.TemplateResponse(request, "stats.html", {"stats": stats})
