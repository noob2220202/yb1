from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.schemas.calculator import ComboType, EqualizeRequest
from app.services.staking import (
    COMBO_CALCULATORS,
    STAKING_DISCLAIMER,
    target_profit_for_total_stake,
)
from app.templating import templates

router = APIRouter()

COMBO_LABELS: dict[str, dict[str, str]] = {
    "draw_dnb0": {"label": "무승부 + 정배팀 DNB(AH0)", "leg_a": "무승부 오즈", "leg_b": "정배팀 DNB 오즈"},
    "draw_ah05": {"label": "무승부 + 정배팀 AH-0.5", "leg_a": "무승부 오즈", "leg_b": "정배팀 AH-0.5 오즈"},
    "ahplus1_margin1": {
        "label": "역배팀 AH+1 + 정배팀 정확히 1골차 승",
        "leg_a": "역배팀 AH+1 오즈",
        "leg_b": "정배팀 1골차승 오즈",
    },
}


def equalize(combo_type: ComboType, odds_a: float, odds_b: float, target_profit: float) -> dict:
    calc_fn = COMBO_CALCULATORS[combo_type]
    return calc_fn(odds_a, odds_b, target_profit)


def resolve_target_profit(
    combo_type: ComboType, odds_a: float, odds_b: float, target_profit: float | None, total_stake: float | None
) -> float:
    """target_profit이 없고 total_stake만 주어졌을 경우, 계산식이 target_profit에 대해
    선형(동차)이라는 성질을 이용해 total_stake에 맞는 target_profit을 역산한다."""
    if target_profit is not None:
        return target_profit

    calc_fn = COMBO_CALCULATORS[combo_type]
    return target_profit_for_total_stake(calc_fn, odds_a, odds_b, total_stake)  # type: ignore[arg-type]


@router.post("/api/calculator/equalize")
def api_equalize(payload: EqualizeRequest) -> dict:
    target_profit = resolve_target_profit(
        payload.combo_type, payload.odds_a, payload.odds_b, payload.target_profit, payload.total_stake
    )
    result = equalize(payload.combo_type, payload.odds_a, payload.odds_b, target_profit)
    result["disclaimer"] = STAKING_DISCLAIMER
    return result


@router.get("/calculator", response_class=HTMLResponse)
def calculator_page(request: Request):
    return templates.TemplateResponse(
        request,
        "calculator.html",
        {
            "combo_labels": COMBO_LABELS,
            "disclaimer": STAKING_DISCLAIMER,
            "result": None,
        },
    )


@router.post("/calculator/compute", response_class=HTMLResponse)
def calculator_compute(
    request: Request,
    combo_type: ComboType = Form(...),
    odds_a: float = Form(...),
    odds_b: float = Form(...),
    input_mode: str = Form("target_profit"),
    amount: float = Form(...),
):
    error = None
    result = None
    try:
        if input_mode == "total_stake":
            target_profit = resolve_target_profit(combo_type, odds_a, odds_b, None, amount)
        else:
            target_profit = amount
        result = equalize(combo_type, odds_a, odds_b, target_profit)
    except ValueError as e:
        error = str(e)

    return templates.TemplateResponse(
        request,
        "_calculator_result.html",
        {
            "result": result,
            "error": error,
            "combo_labels": COMBO_LABELS,
            "combo_type": combo_type,
            "disclaimer": STAKING_DISCLAIMER,
        },
    )
