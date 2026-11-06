"""Normalización de respuestas de la API y estadísticas calculadas por nosotros."""
from datetime import datetime

from . import config


def parse_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Estados de football-data.org -> estados internos
STATUS_MAP = {
    "SCHEDULED": "NS", "TIMED": "NS",
    "IN_PLAY": "LIVE", "LIVE": "LIVE", "PAUSED": "HT",
    "FINISHED": "FT",
    "POSTPONED": "PST", "CANCELLED": "CANC", "SUSPENDED": "SUSP", "AWARDED": "AWD",
}


def _team(t):
    return {"id": t["id"], "name": t.get("shortName") or t["name"],
            "full_name": t["name"], "tla": t.get("tla"), "logo": t.get("crest")}


def _goals(score_part):
    score_part = score_part or {}
    # v4 usa home/away; se aceptan también homeTeam/awayTeam por si acaso
    return {"home": score_part.get("home", score_part.get("homeTeam")),
            "away": score_part.get("away", score_part.get("awayTeam"))}


def normalize_fixture(item):
    """Convierte un partido de football-data.org al formato interno."""
    return {
        "id": item["id"],
        "date": item["utcDate"],
        "round": f"Jornada {item['matchday']}" if item.get("matchday") else item.get("stage"),
        "status": STATUS_MAP.get(item["status"], item["status"]),
        "elapsed": item.get("minute"),
        "home": _team(item["homeTeam"]),
        "away": _team(item["awayTeam"]),
        "goals": _goals((item.get("score") or {}).get("fullTime")),
    }


def normalize_standings(data):
    groups = data.get("standings") or []
    table = next((g["table"] for g in groups if g.get("type") == "TOTAL"),
                 groups[0]["table"] if groups else [])
    return [{
        "rank": r["position"],
        "team": _team(r["team"]),
        "points": r["points"],
        "played": r["playedGames"],
        "win": r["won"],
        "draw": r["draw"],
        "lose": r["lost"],
        "goals_for": r["goalsFor"],
        "goals_against": r["goalsAgainst"],
        "goal_diff": r["goalDifference"],
        "form": r.get("form"),
    } for r in table]


def is_finished(f):
    return f["status"] in config.FINISHED and f["goals"]["home"] is not None


def model_matches(fixtures):
    """Partidos terminados en el formato que espera el modelo."""
    return [{
        "home_id": f["home"]["id"], "away_id": f["away"]["id"],
        "home_goals": f["goals"]["home"], "away_goals": f["goals"]["away"],
        "date": parse_date(f["date"]),
    } for f in fixtures if is_finished(f)]


def _empty_split():
    return {"played": 0, "wins": 0, "draws": 0, "losses": 0, "goals_for": 0, "goals_against": 0}


def team_stats(fixtures):
    """Estadísticas y porcentajes por equipo, calculados solo con los resultados."""
    teams = {}
    for f in sorted((f for f in fixtures if is_finished(f)), key=lambda f: f["date"]):
        hg, ag = f["goals"]["home"], f["goals"]["away"]
        for side, team, gf, ga in (("home", f["home"], hg, ag), ("away", f["away"], ag, hg)):
            t = teams.setdefault(team["id"], {
                "team": team, "home": _empty_split(), "away": _empty_split(),
                "clean_sheets": 0, "failed_to_score": 0, "btts": 0, "over_2_5": 0, "results": [],
            })
            res = "W" if gf > ga else "D" if gf == ga else "L"
            split = t[side]
            split["played"] += 1
            split["goals_for"] += gf
            split["goals_against"] += ga
            split[{"W": "wins", "D": "draws", "L": "losses"}[res]] += 1
            t["clean_sheets"] += ga == 0
            t["failed_to_score"] += gf == 0
            t["btts"] += gf > 0 and ga > 0
            t["over_2_5"] += gf + ga > 2.5
            t["results"].append(res)

    out = []
    for t in teams.values():
        h, a = t["home"], t["away"]
        played = h["played"] + a["played"]
        gf = h["goals_for"] + a["goals_for"]
        ga = h["goals_against"] + a["goals_against"]
        rate = lambda x: round(x / played, 3)
        out.append({
            "team": t["team"],
            "played": played,
            "wins": h["wins"] + a["wins"],
            "draws": h["draws"] + a["draws"],
            "losses": h["losses"] + a["losses"],
            "goals_for": gf,
            "goals_against": ga,
            "avg_goals_for": rate(gf),
            "avg_goals_against": rate(ga),
            "clean_sheets_rate": rate(t["clean_sheets"]),
            "failed_to_score_rate": rate(t["failed_to_score"]),
            "btts_rate": rate(t["btts"]),
            "over_2_5_rate": rate(t["over_2_5"]),
            "form": t["results"][-5:],
            "home": h,
            "away": a,
        })
    return sorted(out, key=lambda x: x["team"]["name"])
