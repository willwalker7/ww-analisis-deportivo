"""Cliente simulado con el mismo formato que football-data.org (v4).

Sirve para probar todo (y empezar la web) sin clave y sin gastar peticiones.
Genera una liga de 20 equipos a doble vuelta; los partidos anteriores a `now`
salen terminados, los que están en curso salen en vivo y el resto sin jugar.
"""
import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TEAMS = ["Atlético Norte", "Real Costa", "Deportivo Sierra", "Unión Ribera", "CD Valle",
         "Racing Puerto", "Sporting Llano", "CF Meseta", "Athletic Monte", "UD Bahía",
         "Celta Mar", "Club Río", "SD Pinar", "Real Olivo", "CD Faro",
         "Recreativo Lago", "UD Campiña", "Elche Viejo", "Getafe Nuevo", "Levante Sur"]
SLOTS = [(0, 14, 0), (0, 16, 15), (0, 18, 30), (0, 21, 0), (1, 14, 0),
         (1, 16, 15), (1, 18, 30), (1, 21, 0), (2, 19, 0), (2, 21, 0)]  # (día desde sábado, h, m)
MADRID = ZoneInfo("Europe/Madrid")


def _round_robin(n):
    teams = list(range(n))
    rounds = []
    for r in range(n - 1):
        pairs = [(teams[i], teams[n - 1 - i]) for i in range(n // 2)]
        rounds.append([(a, b) if r % 2 == 0 else (b, a) for a, b in pairs])
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]
    return rounds + [[(b, a) for a, b in rnd] for rnd in rounds]


def _poisson(rng, lam):
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


class FakeClient:
    def __init__(self, now=None, seed=7, start=datetime(2026, 8, 15, tzinfo=MADRID)):
        self.now = now or datetime.now(timezone.utc)
        self.calls_made = 0
        self.calls = []
        rng = random.Random(seed)
        strength = {i: (rng.uniform(0.7, 1.4), rng.uniform(0.7, 1.3)) for i in range(len(TEAMS))}
        self.fixtures = []
        for r, matches in enumerate(_round_robin(len(TEAMS))):
            saturday = start + timedelta(weeks=r)
            for idx, (h, a) in enumerate(matches):
                d, hh, mm = SLOTS[idx]
                kickoff = (saturday + timedelta(days=d)).replace(hour=hh, minute=mm)
                lam_h = strength[h][0] * strength[a][1] * 1.45
                lam_a = strength[a][0] * strength[h][1] * 1.15
                self.fixtures.append({
                    "id": 1000 + r * 10 + idx, "matchday": r + 1,
                    "kickoff": kickoff, "home": h, "away": a,
                    "final": (_poisson(rng, lam_h), _poisson(rng, lam_a)),
                })

    def _team(self, i):
        return {"id": 500 + i, "name": TEAMS[i], "shortName": TEAMS[i],
                "tla": TEAMS[i][:3].upper(), "crest": None}

    def _api_match(self, f):
        minutes = (self.now - f["kickoff"]).total_seconds() / 60
        if minutes >= 115:
            status, goals = "FINISHED", f["final"]
        elif minutes >= 0:
            status = "IN_PLAY" if minutes < 45 or minutes >= 60 else "PAUSED"
            elapsed = minutes if minutes < 45 else 45 if minutes < 60 else minutes - 15
            share = min(elapsed, 90) / 90
            goals = (int(f["final"][0] * share), int(f["final"][1] * share))
        else:
            status, goals = "TIMED", (None, None)
        return {
            "id": f["id"], "utcDate": f["kickoff"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": status, "matchday": f["matchday"], "stage": "REGULAR_SEASON",
            "homeTeam": self._team(f["home"]), "awayTeam": self._team(f["away"]),
            "score": {"duration": "REGULAR", "fullTime": {"home": goals[0], "away": goals[1]}},
        }

    def get(self, path, **params):
        self.calls_made += 1
        self.calls.append((path, params))
        if path.endswith("/matches"):
            items = [self._api_match(f) for f in self.fixtures]
            if "dateFrom" in params:  # dateTo excluido, como en la v4
                items = [i for i in items if params["dateFrom"] <= i["utcDate"][:10] < params["dateTo"]]
            return {"matches": items}
        if path.endswith("/standings"):
            return {"standings": [{"type": "TOTAL", "table": self._table()}]}
        return {}

    def _table(self):
        table = {i: {"played": 0, "won": 0, "draw": 0, "lost": 0, "for": 0, "against": 0, "pts": 0}
                 for i in range(len(TEAMS))}
        for f in self.fixtures:
            if (self.now - f["kickoff"]).total_seconds() / 60 < 115:
                continue
            hg, ag = f["final"]
            for t, gf, ga in ((f["home"], hg, ag), (f["away"], ag, hg)):
                row = table[t]
                row["played"] += 1
                row["for"] += gf
                row["against"] += ga
                key = "won" if gf > ga else "draw" if gf == ga else "lost"
                row[key] += 1
                row["pts"] += {"won": 3, "draw": 1, "lost": 0}[key]
        order = sorted(table, key=lambda t: (-table[t]["pts"], -(table[t]["for"] - table[t]["against"]),
                                             -table[t]["for"]))
        return [{
            "position": pos + 1, "team": self._team(t), "playedGames": table[t]["played"],
            "form": None, "won": table[t]["won"], "draw": table[t]["draw"], "lost": table[t]["lost"],
            "points": table[t]["pts"], "goalsFor": table[t]["for"], "goalsAgainst": table[t]["against"],
            "goalDifference": table[t]["for"] - table[t]["against"],
        } for pos, t in enumerate(order)]
