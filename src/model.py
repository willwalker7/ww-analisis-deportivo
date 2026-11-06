"""Modelo de Poisson para predecir resultados.

Idea: cada equipo tiene una fuerza de ataque y de defensa relativa a la media de
la liga. Los goles esperados de un partido son:

    goles_local     = ataque(local)     * defensa(visitante) * media_goles_local_liga
    goles_visitante = ataque(visitante) * defensa(local)     * media_goles_visitante_liga

Con esos goles esperados, la distribución de Poisson da la probabilidad de cada
marcador exacto, y sumando marcadores salen 1X2, más/menos goles y ambos marcan.

Dos ajustes para que funcione con pocos partidos:
  * Contracción (shrinkage): cada equipo arranca con PRIOR_MATCHES partidos
    "imaginarios" de equipo medio, así 3 jornadas buenas no lo convierten en el
    mejor de Europa.
  * Decaimiento temporal: los partidos recientes pesan más (vida media configurable).
"""
import math
from datetime import datetime

MAX_GOALS = 10
DEFAULT_HOME_AVG = 1.45
DEFAULT_AWAY_AVG = 1.15
PRIOR_MATCHES = 5
HALF_LIFE_DAYS = 120


def poisson_pmf(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


class PoissonModel:
    def __init__(self, prior_matches=PRIOR_MATCHES, half_life_days=HALF_LIFE_DAYS):
        self.prior_matches = prior_matches
        self.half_life_days = half_life_days
        self.home_avg = DEFAULT_HOME_AVG
        self.away_avg = DEFAULT_AWAY_AVG
        self.attack = {}
        self.defense = {}
        self.matches_used = 0

    def _weight(self, match_date, reference_date):
        if not self.half_life_days:
            return 1.0
        days = max((reference_date - match_date).total_seconds() / 86400, 0)
        return 0.5 ** (days / self.half_life_days)

    def fit(self, matches, reference_date):
        """matches: lista de dicts con home_id, away_id, home_goals, away_goals, date (datetime)."""
        matches = [m for m in matches if m["date"] < reference_date]
        self.matches_used = len(matches)
        if not matches:
            return self

        # El decaimiento se mide desde el último partido jugado (no desde "ahora"),
        # así las predicciones solo cambian cuando hay resultados nuevos.
        latest = max(m["date"] for m in matches)
        weighted = [(m, self._weight(m["date"], latest)) for m in matches]
        total_w = sum(w for _, w in weighted)
        self.home_avg = sum(m["home_goals"] * w for m, w in weighted) / total_w or DEFAULT_HOME_AVG
        self.away_avg = sum(m["away_goals"] * w for m, w in weighted) / total_w or DEFAULT_AWAY_AVG

        # Para cada equipo: goles reales frente a los que habría marcado/encajado un equipo medio
        acc = {}
        for m, w in weighted:
            for team, scored, conceded, exp_scored, exp_conceded in (
                (m["home_id"], m["home_goals"], m["away_goals"], self.home_avg, self.away_avg),
                (m["away_id"], m["away_goals"], m["home_goals"], self.away_avg, self.home_avg),
            ):
                a = acc.setdefault(team, [0.0, 0.0, 0.0, 0.0])
                a[0] += scored * w
                a[1] += exp_scored * w
                a[2] += conceded * w
                a[3] += exp_conceded * w

        prior = self.prior_matches * (self.home_avg + self.away_avg) / 2
        for team, (scored, exp_scored, conceded, exp_conceded) in acc.items():
            self.attack[team] = (scored + prior) / (exp_scored + prior)
            self.defense[team] = (conceded + prior) / (exp_conceded + prior)
        return self

    def expected_goals(self, home_id, away_id):
        lam_home = self.attack.get(home_id, 1.0) * self.defense.get(away_id, 1.0) * self.home_avg
        lam_away = self.attack.get(away_id, 1.0) * self.defense.get(home_id, 1.0) * self.away_avg
        return lam_home, lam_away

    def predict(self, home_id, away_id):
        lam_h, lam_a = self.expected_goals(home_id, away_id)
        ph = [poisson_pmf(k, lam_h) for k in range(MAX_GOALS + 1)]
        pa = [poisson_pmf(k, lam_a) for k in range(MAX_GOALS + 1)]
        matrix = [[ph[i] * pa[j] for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]
        total = sum(map(sum, matrix))

        home = draw = away = btts = 0.0
        over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
        scores = []
        for i, row in enumerate(matrix):
            for j, p in enumerate(row):
                p /= total
                if i > j:
                    home += p
                elif i == j:
                    draw += p
                else:
                    away += p
                if i > 0 and j > 0:
                    btts += p
                for line in over:
                    if i + j > line:
                        over[line] += p
                scores.append((p, f"{i}-{j}"))
        scores.sort(reverse=True)

        r = lambda x: round(x, 4)
        return {
            "expected_goals": {"home": round(lam_h, 2), "away": round(lam_a, 2)},
            "probabilities": {"home_win": r(home), "draw": r(draw), "away_win": r(away)},
            "over_under": {f"over_{str(k).replace('.', '_')}": r(v) for k, v in over.items()},
            "btts": {"yes": r(btts), "no": r(1 - btts)},
            "top_scores": [{"score": s, "probability": r(p)} for p, s in scores[:5]],
        }


# ---------- Evaluación ----------

OUTCOMES = ("home_win", "draw", "away_win")


def outcome_of(home_goals, away_goals):
    if home_goals > away_goals:
        return "home_win"
    return "draw" if home_goals == away_goals else "away_win"


def evaluate(prediction, home_goals, away_goals):
    probs = prediction["probabilities"]
    actual = outcome_of(home_goals, away_goals)
    predicted = max(OUTCOMES, key=lambda o: probs[o])
    brier = sum((probs[o] - (1.0 if o == actual else 0.0)) ** 2 for o in OUTCOMES)
    log_loss = -math.log(max(probs[actual], 1e-9))
    over_p = prediction.get("over_under", {}).get("over_2_5")
    result = {
        "actual": actual,
        "predicted": predicted,
        "hit": predicted == actual,
        "brier": round(brier, 4),
        "log_loss": round(log_loss, 4),
    }
    if over_p is not None:
        result["over_2_5_hit"] = (over_p >= 0.5) == (home_goals + away_goals > 2.5)
    return result


def summarize(evaluations):
    n = len(evaluations)
    if not n:
        return {"matches": 0}
    over = [e["over_2_5_hit"] for e in evaluations if "over_2_5_hit" in e]
    return {
        "matches": n,
        "accuracy_1x2": round(sum(e["hit"] for e in evaluations) / n, 4),
        "avg_brier": round(sum(e["brier"] for e in evaluations) / n, 4),
        "avg_log_loss": round(sum(e["log_loss"] for e in evaluations) / n, 4),
        "accuracy_over_2_5": round(sum(over) / len(over), 4) if over else None,
    }


def backtest(matches, min_training_matches=30, **model_kwargs):
    """Simulación retrospectiva: predice cada partido usando SOLO los anteriores."""
    matches = sorted(matches, key=lambda m: m["date"])
    evaluations = []
    cache = {}
    for m in matches:
        day = m["date"].date()
        if day not in cache:
            ref = datetime.combine(day, datetime.min.time(), tzinfo=m["date"].tzinfo)
            cache[day] = PoissonModel(**model_kwargs).fit(matches, ref)
        model = cache[day]
        if model.matches_used < min_training_matches:
            continue
        pred = model.predict(m["home_id"], m["away_id"])
        evaluations.append(evaluate(pred, m["home_goals"], m["away_goals"]))
    return evaluations
