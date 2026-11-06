import json
from datetime import datetime, timedelta, timezone

from src.demo import FakeClient
from src.update import run

# Sábado por la mañana: aún no ha empezado ningún partido
QUIET = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
MATCHES = "competitions/PD/matches"
STANDINGS = "competitions/PD/standings"


def load(tmp_path, name):
    return json.loads((tmp_path / name).read_text(encoding="utf-8"))


def quiet(*_):
    pass


def first_kickoff_after(client, when):
    return min(f["kickoff"] for f in client.fixtures if f["kickoff"] > when).astimezone(timezone.utc)


def test_first_run_does_full_refresh(tmp_path):
    client = FakeClient(now=QUIET)
    run(client, data_dir=tmp_path, now=QUIET, log=quiet)
    assert [c[0] for c in client.calls] == [MATCHES, STANDINGS]
    for name in ("fixtures.json", "standings.json", "teams.json", "predictions.json",
                 "history.json", "performance.json", "meta.json"):
        assert (tmp_path / name).exists()
    preds = load(tmp_path, "predictions.json")
    assert preds["matches"] and preds["model"]["matches_used"] > 100
    assert load(tmp_path, "standings.json")[0]["rank"] == 1
    assert load(tmp_path, "performance.json")["backtest"]["matches"] > 50


def test_quiet_run_makes_no_requests_and_changes_nothing(tmp_path):
    run(FakeClient(now=QUIET), data_dir=tmp_path, now=QUIET, log=quiet)
    later = QUIET + timedelta(minutes=15)
    client = FakeClient(now=later)
    changed = run(client, data_dir=tmp_path, now=later, log=quiet)
    assert client.calls_made == 0
    assert changed == []


def test_live_match_then_finish(tmp_path):
    first = FakeClient(now=QUIET)
    run(first, data_dir=tmp_path, now=QUIET, log=quiet)
    kickoff = first_kickoff_after(first, QUIET)

    during = kickoff + timedelta(minutes=30)
    live = FakeClient(now=during)
    run(live, data_dir=tmp_path, now=during, log=quiet)
    assert [c[0] for c in live.calls] == [MATCHES]
    assert "dateFrom" in live.calls[0][1] and "dateTo" in live.calls[0][1]
    statuses = {f["status"] for f in load(tmp_path, "fixtures.json")}
    assert "LIVE" in statuses

    after = kickoff + timedelta(minutes=130)
    end = FakeClient(now=after)
    run(end, data_dir=tmp_path, now=after, log=quiet)
    assert [c[0] for c in end.calls] == [MATCHES, STANDINGS]

    # la predicción congelada antes del partido queda evaluada
    history = load(tmp_path, "history.json")
    finished = [h for h in history.values() if h["evaluation"]]
    assert finished and all(h["result"] is not None for h in finished)
