"""텔레그램 전송 — 픽 저장/채점 결과를 이모지·볼드·이탤릭·인용을 활용해
보기 좋게 포맷해서 채널/그룹/DM으로 보낸다.

.env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID를 설정하면 활성화된다
(둘 중 하나라도 비어 있으면 조용히 스킵 — 텔레그램 없이도 앱은 정상 동작).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models.pick import Pick

logger = logging.getLogger("oddsapp.telegram")

_TELEGRAM_API_BASE = "https://api.telegram.org"

# MarkdownV2에서 이스케이프가 필요한 특수문자
_MD_V2_SPECIAL = set(r"_*[]()~`>#+-=|{}.!\\")


def escape_md(value) -> str:
    text = str(value)
    return "".join(f"\\{ch}" if ch in _MD_V2_SPECIAL else ch for ch in text)


def is_configured() -> bool:
    return bool(settings.telegram_bot_token and settings.telegram_chat_id)


def send_telegram_message(text: str) -> bool:
    if not is_configured():
        logger.info("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 전송 스킵")
        return False

    url = f"{_TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return True
    except httpx.HTTPError:
        logger.exception("텔레그램 전송 실패")
        return False


_COMBO_TYPE_EMOJI = {
    "draw_dnb0": "🤝",
    "draw_ah05": "🤝",
    "ahplus1_margin1": "🎯",
}

_SCENARIO_LABELS = {
    "draw": "무승부 적중 (상대 다리 push)",
    "home_win": "정배팀 승 적중",
    "away_win": "역배팀 승 — 양쪽 다리 실패",
    "underdog_win_or_draw": "역배승/무승부 적중",
    "favorite_margin1": "정배 1골차 승 적중",
    "favorite_margin2plus": "정배 2골차\\+ 승 — 양쪽 다리 실패",
}


def format_pick_message(pick: Pick) -> str:
    emoji = _COMBO_TYPE_EMOJI.get(pick.combo_type, "🧮")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

    lines = [
        f"{emoji} *새 픽 저장*",
        "",
        f"⚽ _{escape_md(pick.home_team)} vs {escape_md(pick.away_team)}_",
        f"🏷 *{escape_md(pick.description)}*",
        "",
        f"💰 다리 A 스테이크: `{escape_md(f'{float(pick.stake_leg_a):,.0f}')}원`",
        f"💰 다리 B 스테이크: `{escape_md(f'{float(pick.stake_leg_b):,.0f}')}원`",
        f"💵 총 스테이크: `{escape_md(f'{float(pick.total_stake):,.0f}')}원`",
        f"🎁 목표 이익: `{escape_md(f'{float(pick.target_profit):,.0f}')}원`",
        "",
    ]

    if pick.implied_hit_rate is not None:
        lines.append(f"📊 적중확률 추정: *{escape_md(f'{float(pick.implied_hit_rate) * 100:.1f}')}%*")
    if pick.breakeven_prob is not None:
        lines.append(f"⚖️ 손익분기확률: *{escape_md(f'{float(pick.breakeven_prob) * 100:.1f}')}%*")
    if pick.estimated_ev_pct is not None:
        ev = float(pick.estimated_ev_pct)
        ev_emoji = "🟢" if ev >= 0 else "🔴"
        sign = "\\+" if ev >= 0 else ""
        lines.append(f"📈 추정 EV: {ev_emoji} *{sign}{escape_md(f'{ev:.2f}')}%*")

    lines += [
        "",
        "> ⚠️ 이 배분은 손익 분산만 줄일 뿐 기대값을 개선하지 않습니다",
        "",
        f"🕒 {escape_md(ts)} UTC",
    ]
    return "\n".join(lines)


def format_result_message(pick: Pick) -> str:
    hit = bool(pick.hit)
    header = "✅ *픽 결과: 적중*" if hit else "❌ *픽 결과: 실패*"
    scenario_label = _SCENARIO_LABELS.get(pick.outcome_scenario or "", pick.outcome_scenario or "-")
    profit = float(pick.actual_profit) if pick.actual_profit is not None else 0.0
    profit_emoji = "🟢" if profit >= 0 else "🔴"
    sign = "\\+" if profit >= 0 else ""

    lines = [
        header,
        "",
        f"⚽ _{escape_md(pick.home_team)} vs {escape_md(pick.away_team)}_",
        f"🏷 {escape_md(pick.description)}",
        "",
        f"🔢 최종 스코어: *{pick.home_score_actual} : {pick.away_score_actual}*",
        f"📌 발생 시나리오: {scenario_label}",
        f"💰 실현 손익: {profit_emoji} *{sign}{escape_md(f'{profit:,.0f}')}원*",
    ]
    return "\n".join(lines)
