from datetime import datetime, timedelta, timezone

import pytest

from src.model import PoissonModel, backtest, evaluate, summarize

NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def m(h, a, hg, ag, days_ago=7):
    return {"home_id": h, "away_id": a, "home_goals": hg, "away_goals": ag,
            "date": NOW - timedelta(days=days_ago)}


def test_probabilities_sum_to_one():
    p = PoissonModel().predict(1, 2)
    probs = p["probabilities"]
    assert sum(probs.values()) == pytest.approx(1, abs=1e-3)
    assert p["btts"]["yes"] + p["btts"]["no"] == pytest.approx(1)
    assert p["over_under"]["over_1_5"] > p["over_under"]["over_2_5"] > p["over_under"]["over_3_5"]


def test_unknown_teams_get_home_advantage():
    probs = PoissonModel().predict(1, 2)["probabilities"]
    assert probs["home_win"] > probs["away_win"]


def test_stronger_team_is_favourite():
    history = [m(1, 3, 3, 0), m(3, 1, 0, 2), m(1, 4, 4, 1), m(2, 3, 0, 1), m(4, 2, 2, 0), m(3, 2, 1, 1)]
    model = PoissonModel().fit(history, NOW)
    assert model.predict(1, 2)["probabilities"]["home_win"] > 0.5
    assert model.predict(2, 1)["probabilities"]["away_win"] > model.predict(2, 1)["probabilities"]["home_win"]


def test_shrinkage_keeps_small_samples_reasonable():
    league = [m(h, a, 1, 1) for h, a in ((2, 3), (3, 4), (4, 2), (3, 2), (4, 3), (2, 4))]
    model = PoissonModel().fit(league + [m(1, 2, 6, 0)], NOW)
    lam_h, _ = model.expected_goals(1, 3)
    assert 1 < lam_h < 3.5  # un solo 6-0 no dispara las expectativas


def test_future_matches_are_ignored():
    model = PoissonModel().fit([m(1, 2, 5, 0, days_ago=-1)], NOW)
    assert model.matches_used == 0


def test_evaluate_and_summarize():
    pred = PoissonModel().predict(1, 2)
    ev = evaluate(pred, 2, 0)
    assert ev["actual"] == "home_win" and ev["hit"] is True
    s = summarize([ev, evaluate(pred, 0, 1)])
    assert s["matches"] == 2 and s["accuracy_1x2"] == 0.5


def test_backtest_only_uses_past_matches():
    matches = [m(i % 4 + 1, (i + 1) % 4 + 1, i % 3, 1, days_ago=100 - i) for i in range(40)]
    evs = backtest(matches, min_training_matches=10)
    assert 0 < len(evs) <= 30
