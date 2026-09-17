from app.services.staking import compute_quality_grade


def test_returns_none_when_any_input_missing():
    assert compute_quality_grade(None, 0.8, 0.6) is None
    assert compute_quality_grade(1.0, None, 0.6) is None
    assert compute_quality_grade(1.0, 0.8, None) is None


def test_grade_s_high_ev_and_margin():
    # EV=5, margin=(0.85-0.70)*100=15 -> score=20
    assert compute_quality_grade(5.0, 0.85, 0.70) == "S"


def test_grade_a():
    # EV=1, margin=(0.80-0.75)*100=5 -> score=6
    assert compute_quality_grade(1.0, 0.80, 0.75) == "A"


def test_grade_b():
    # EV=-1, margin=(0.80-0.79)*100=1 -> score=0
    assert compute_quality_grade(-1.0, 0.80, 0.79) == "B"


def test_grade_c():
    # EV=-3, margin=0 -> score=-3
    assert compute_quality_grade(-3.0, 0.70, 0.70) == "C"


def test_grade_d_negative_ev_and_margin():
    # EV=-10, margin=(0.60-0.75)*100=-15 -> score=-25
    assert compute_quality_grade(-10.0, 0.60, 0.75) == "D"


def test_boundary_scores():
    # score exactly 8 -> S ; just under -> A
    assert compute_quality_grade(8.0, 0.5, 0.5) == "S"
    assert compute_quality_grade(7.999, 0.5, 0.5) == "A"
    assert compute_quality_grade(3.0, 0.5, 0.5) == "A"
    assert compute_quality_grade(2.999, 0.5, 0.5) == "B"
    assert compute_quality_grade(0.0, 0.5, 0.5) == "B"
    assert compute_quality_grade(-0.001, 0.5, 0.5) == "C"
    assert compute_quality_grade(-5.0, 0.5, 0.5) == "C"
    assert compute_quality_grade(-5.001, 0.5, 0.5) == "D"
