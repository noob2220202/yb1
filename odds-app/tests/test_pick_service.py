import math

from app.models.pick import Pick
from app.services.pick_service import compute_stats, grade_and_notify, save_pick


def _save_sample(db, **overrides):
    defaults = dict(
        fixture_id=None,
        home_team="Home FC",
        away_team="Away FC",
        combo_type="draw_dnb0",
        description="무승부 + 홈팀 DNB",
        leg_a_selection="draw",
        leg_b_selection="home",
        favorite_side="home",
        odds_leg_a=3.46,
        odds_leg_b=1.854,
        stake_leg_a=4100,
        stake_leg_b=16600,
        total_stake=20700,
        target_profit=10076,
        implied_hit_rate=0.776,
        breakeven_prob=0.673,
        estimated_ev_pct=-3.2,
    )
    defaults.update(overrides)
    return save_pick(db, **defaults)


def test_save_pick_persists_and_defaults_pending(db_session):
    pick = _save_sample(db_session)
    assert pick.id is not None
    assert pick.status == "pending"
    assert pick.telegram_sent is False  # .env에 토큰 없으므로 전송 스킵

    reloaded = db_session.query(Pick).filter(Pick.id == pick.id).one()
    assert reloaded.home_team == "Home FC"


def test_save_pick_stores_comment(db_session):
    pick = _save_sample(db_session, comment="홈팀 주전 결장, 조심")
    assert pick.comment == "홈팀 주전 결장, 조심"

    reloaded = db_session.query(Pick).filter(Pick.id == pick.id).one()
    assert reloaded.comment == "홈팀 주전 결장, 조심"


def test_save_pick_comment_defaults_to_none(db_session):
    pick = _save_sample(db_session)
    assert pick.comment is None


def test_grade_and_notify_marks_hit_and_settled(db_session):
    pick = _save_sample(db_session)
    graded = grade_and_notify(db_session, pick, home_score=1, away_score=1)

    assert graded.status == "settled"
    assert graded.outcome_scenario == "draw"
    assert graded.hit is True
    assert math.isclose(float(graded.actual_profit), 10076, rel_tol=1e-9)
    assert graded.settled_at is not None


def test_grade_and_notify_marks_loss(db_session):
    pick = _save_sample(db_session)
    graded = grade_and_notify(db_session, pick, home_score=0, away_score=1)

    assert graded.status == "settled"
    assert graded.outcome_scenario == "away_win"
    assert graded.hit is False
    assert float(graded.actual_profit) < 0


def test_compute_stats_empty(db_session):
    stats = compute_stats(db_session)
    assert stats["settled_count"] == 0
    assert stats["pending_count"] == 0
    assert stats["hit_rate"] is None
    assert stats["roi_pct"] is None


def test_compute_stats_aggregates_across_picks(db_session):
    win_pick = _save_sample(db_session)
    grade_and_notify(db_session, win_pick, home_score=1, away_score=1)  # 적중

    lose_pick = _save_sample(db_session)
    grade_and_notify(db_session, lose_pick, home_score=0, away_score=1)  # 실패

    pending_pick = _save_sample(db_session)  # 채점 안 함

    stats = compute_stats(db_session)
    assert stats["settled_count"] == 2
    assert stats["pending_count"] == 1
    assert stats["hits"] == 1
    assert math.isclose(stats["hit_rate"], 0.5, rel_tol=1e-9)
    assert "draw_dnb0" in stats["by_combo_type"]
    assert stats["by_combo_type"]["draw_dnb0"]["count"] == 2
    assert stats["by_combo_type"]["draw_dnb0"]["hits"] == 1
