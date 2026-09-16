"""API-Football 원본 마켓/셀렉션 이름 -> 내부 스키마 정규화 매핑.

**중요**: 이 매핑표는 API-Football v3의 공개 문서에 기술된 베팅명을 기준으로
작성한 최초 초안이다. 실제 API 키로 `scripts/inspect_api_response.py`를 실행해
얻은 실제 응답 샘플로 반드시 검증/보정할 것 (SPEC.md 5.2절).

구조:
    BET_NAME_TO_MARKET_TYPE: API 원본 bet.name -> 내부 market_type
    각 market_type 파서 함수: bet.values 리스트 -> [(selection, line, decimal_odds), ...]
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# API-Football bets.name -> 내부 market_type
BET_NAME_TO_MARKET_TYPE: dict[str, str] = {
    "Match Winner": "1x2",
    "Home/Draw/Away": "1x2",
    "Asian Handicap": "ah",
    "Goals Over/Under": "ou",
    "Over/Under": "ou",
    "Exact Score": "correct_score",
    "Winning Margin": "win_margin",
    "Both Teams Score": "btts",
    "Draw No Bet": "dnb",
}

_1X2_SELECTION_MAP = {"home": "home", "draw": "draw", "away": "away"}
_BTTS_SELECTION_MAP = {"yes": "btts_yes", "no": "btts_no"}
_DNB_SELECTION_MAP = {"home": "home", "away": "away"}

_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _to_decimal(odd_str: str) -> Decimal:
    try:
        return Decimal(str(odd_str))
    except InvalidOperation as exc:
        raise ValueError(f"유효하지 않은 오즈 값: {odd_str}") from exc


def parse_1x2(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    out = []
    for v in values:
        key = str(v["value"]).strip().lower()
        selection = _1X2_SELECTION_MAP.get(key)
        if selection is None:
            continue
        out.append((selection, None, _to_decimal(v["odd"])))
    return out


def parse_btts(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    out = []
    for v in values:
        key = str(v["value"]).strip().lower()
        selection = _BTTS_SELECTION_MAP.get(key)
        if selection is None:
            continue
        out.append((selection, None, _to_decimal(v["odd"])))
    return out


def parse_dnb(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    out = []
    for v in values:
        key = str(v["value"]).strip().lower()
        selection = _DNB_SELECTION_MAP.get(key)
        if selection is None:
            continue
        out.append((selection, None, _to_decimal(v["odd"])))
    return out


def _extract_side_and_line(value_str: str) -> tuple[str | None, Decimal | None]:
    """'Home -0.5' -> ('home', -0.5) 형태로 파싱. 'Over 2.5' -> ('over', 2.5)."""
    text = value_str.strip().lower()
    side: str | None = None
    if text.startswith("home"):
        side = "home"
    elif text.startswith("away"):
        side = "away"
    elif text.startswith("over"):
        side = "over"
    elif text.startswith("under"):
        side = "under"

    match = _NUMBER_RE.search(text)
    line = Decimal(match.group()) if match else None
    return side, line


def parse_ah(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    """'Home -0.5' / 'Away +0.5'는 같은 라인의 양면이므로, line은 항상
    홈팀 기준으로 정규화한다(away 쪽 부호를 뒤집어 홈 기준 라인에 맞춘다).
    이렇게 해야 ingest에서 동일 라인의 home/away가 같은 market row로 묶인다.
    """
    out = []
    for v in values:
        side, line = _extract_side_and_line(str(v["value"]))
        if side not in ("home", "away"):
            continue
        if side == "away" and line is not None:
            line = -line
        out.append((side, line, _to_decimal(v["odd"])))
    return out


def parse_ou(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    out = []
    for v in values:
        side, line = _extract_side_and_line(str(v["value"]))
        if side not in ("over", "under"):
            continue
        out.append((side, line, _to_decimal(v["odd"])))
    return out


def parse_correct_score(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    out = []
    for v in values:
        raw = str(v["value"]).strip().replace(":", "-")
        if not re.fullmatch(r"\d+-\d+", raw):
            continue
        out.append((raw, None, _to_decimal(v["odd"])))
    return out


def parse_win_margin(values: list[dict]) -> list[tuple[str, Decimal | None, Decimal]]:
    out = []
    for v in values:
        text = str(v["value"]).strip().lower()
        match = _NUMBER_RE.search(text)
        margin = match.group() if match else "0"
        if text.startswith("home"):
            selection = f"home_by_{margin}"
        elif text.startswith("away"):
            selection = f"away_by_{margin}"
        elif "draw" in text:
            selection = "draw"
        else:
            continue
        out.append((selection, None, _to_decimal(v["odd"])))
    return out


MARKET_PARSERS = {
    "1x2": parse_1x2,
    "ah": parse_ah,
    "ou": parse_ou,
    "dnb": parse_dnb,
    "btts": parse_btts,
    "correct_score": parse_correct_score,
    "win_margin": parse_win_margin,
}


def normalize_bet(bet_name: str, values: list[dict]) -> tuple[str, list[tuple[str, Decimal | None, Decimal]]] | None:
    """API 원본 bet(name, values)을 (market_type, [(selection, line, odds), ...])로 정규화.

    지원하지 않는 bet_name이면 None을 반환한다.
    """
    market_type = BET_NAME_TO_MARKET_TYPE.get(bet_name)
    if market_type is None:
        return None
    parser = MARKET_PARSERS[market_type]
    parsed = parser(values)
    if not parsed:
        return None
    return market_type, parsed
