from decimal import Decimal

import httpx
import pytest

from app.models.pick import Pick
from app.services import telegram_client as tg


def _make_pick(**overrides) -> Pick:
    defaults = dict(
        home_team="Home FC",
        away_team="Away FC",
        combo_type="draw_dnb0",
        description="무승부 + 홈팀 DNB",
        leg_a_selection="draw",
        leg_b_selection="home",
        favorite_side="home",
        odds_leg_a=Decimal("3.46"),
        odds_leg_b=Decimal("1.854"),
        stake_leg_a=Decimal("4100"),
        stake_leg_b=Decimal("16600"),
        total_stake=Decimal("20700"),
        target_profit=Decimal("10076"),
        implied_hit_rate=Decimal("0.776"),
        breakeven_prob=Decimal("0.673"),
        estimated_ev_pct=Decimal("-3.2"),
    )
    defaults.update(overrides)
    return Pick(**defaults)


def test_escape_md_escapes_all_special_chars():
    raw = "1.854 (test) - value [x]_y*z~w`v>u#t+s=r|q{p}o!n"
    escaped = tg.escape_md(raw)
    for ch in "_*[]()~`>#+-=|{}.!":
        assert f"\\{ch}" in escaped
    # 이스케이프 후에는 원본 특수문자가 backslash 없이 단독으로 남아있지 않아야 함
    assert "1\\.854" in escaped


def test_is_configured_false_by_default():
    assert tg.settings.telegram_bot_token == ""
    assert tg.is_configured() is False


def test_send_telegram_message_skips_when_not_configured():
    assert tg.send_telegram_message("hello") is False


def test_format_pick_message_contains_key_fields_and_disclaimer():
    pick = _make_pick()
    msg = tg.format_pick_message(pick)
    assert "새 픽 저장" in msg
    assert "Home FC" in msg
    assert "Away FC" in msg
    assert "4\\,100" not in msg  # 콤마는 이스케이프 대상 아님 — 그냥 그대로 있어야 함
    assert "4,100" in msg
    assert "손익 분산만 줄일 뿐 기대값을 개선하지 않습니다" in msg
    assert "🔴" in msg  # EV가 음수이므로 빨간 이모지


def test_format_pick_message_includes_comment_when_present():
    pick = _make_pick(comment="홈팀 주전 공격수 결장. 1.5 라인 주의")
    msg = tg.format_pick_message(pick)
    assert "코멘트" in msg
    # '.'은 MarkdownV2 특수문자라 이스케이프돼야 하고, 원본 숫자는 그대로 보여야 함
    assert "1\\.5" in msg
    assert "홈팀 주전 공격수 결장" in msg


def test_format_pick_message_omits_comment_section_when_absent():
    pick = _make_pick(comment=None)
    msg = tg.format_pick_message(pick)
    assert "코멘트" not in msg


def test_format_pick_message_positive_ev_uses_green_emoji():
    pick = _make_pick(estimated_ev_pct=Decimal("1.5"))
    msg = tg.format_pick_message(pick)
    assert "🟢" in msg


def test_format_result_message_hit_and_miss():
    pick = _make_pick(
        status="settled", home_score_actual=1, away_score_actual=1,
        outcome_scenario="draw", actual_profit=Decimal("10076"), hit=True,
    )
    msg = tg.format_result_message(pick)
    assert "적중" in msg
    assert "🟢" in msg

    pick_lost = _make_pick(
        status="settled", home_score_actual=0, away_score_actual=1,
        outcome_scenario="away_win", actual_profit=Decimal("-20700"), hit=False,
    )
    msg_lost = tg.format_result_message(pick_lost)
    assert "실패" in msg_lost
    assert "🔴" in msg_lost


def test_send_telegram_message_success(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "12345")

    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(tg.httpx, "post", fake_post)

    result = tg.send_telegram_message("테스트 메시지")
    assert result is True
    assert captured["json"]["chat_id"] == "12345"
    assert captured["json"]["parse_mode"] == "MarkdownV2"
    assert "fake-token" in captured["url"]


def test_send_telegram_message_handles_http_error(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "12345")

    def fake_post(url, json, timeout):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(tg.httpx, "post", fake_post)

    result = tg.send_telegram_message("테스트 메시지")
    assert result is False
