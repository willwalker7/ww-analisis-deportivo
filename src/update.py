"""Job de actualización. Lo ejecuta GitHub Actions cada 15 minutos.

Lógica de cada ejecución (máximo 2 peticiones):
  1. Si el calendario guardado tiene más de 20 h -> refresco completo (1 petición).
  2. Si no, mira EN LOCAL si hay algún partido en juego ahora. Si no hay, termina
     sin hacer ninguna petición. Si lo hay, pide los partidos de ese día (1 petición).
  3. Si algún partido acaba de terminar -> clasificación (1 petición) y recálculo del modelo.
  4. Recalcula predicciones, estadísticas y rendimiento (sin peticiones) y solo
     reescribe los JSON que hayan cambiado.

Uso:
    python -m src.update            # ejecución normal
    python -m src.update --full     # fuerza refresco completo
    python -m src.update --demo     # datos simulados, sin clave ni peticiones reales
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .api_client import ApiError, QuotaExhausted
from .model import PoissonModel, backtest, evaluate, summarize
from .stats import (is_finished, model_matches, normalize_fixture, normalize_standings,
                    parse_date, team_stats)


class Storage:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.changed = []

    def load(self, name, default):
        path = self.dir / name
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, name, obj):
        """Escribe solo si el contenido cambia (evita commits vacíos)."""
        path = self.dir / name
        text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return False
        path.write_text(text, encoding="utf-8")
        self.changed.append(name)
        return True


def matches_in_window(fixtures, now):
    """Partidos que pueden estar jugándose ahora según el calendario guardado."""
    window = timedelta(minutes=config.LIVE_WINDOW_MINUTES)
    out = []
    for f in fixtures:
        if f["status"] in config.FINISHED | config.CANCELLED:
            continue
        kickoff = parse_date(f["date"])
        if kickoff - timedelta(minutes=5) <= now <= kickoff + window or f["status"] in config.LIVE:
            out.append(f)
    return out


def finished_ids(fixtures):
    return {f["id"] for f in fixtures if is_finished(f)}


def build_predictions(fixtures, now):
    model = PoissonModel().fit(model_matches(fixtures), now)
    horizon = now + timedelta(days=config.PREDICTION_HORIZON_DAYS)
    matches = []
    for f in fixtures:
        kickoff = parse_date(f["date"])
        if f["status"] in config.NOT_STARTED and now < kickoff <= horizon:
            matches.append({
                "fixture_id": f["id"], "date": f["date"], "round": f["round"],
                "home": f["home"], "away": f["away"],
                "prediction": model.predict(f["home"]["id"], f["away"]["id"]),
            })
    matches.sort(key=lambda m: m["date"])
    info = {
        "model": "poisson",
        "matches_used": model.matches_used,
        "league_home_goals_avg": round(model.home_avg, 3),
        "league_away_goals_avg": round(model.away_avg, 3),
    }
    return {"model": info, "matches": matches}


def update_history(history, predictions, fixtures, now):
    """Congela la última predicción previa al partido y la evalúa cuando termina."""
    for m in predictions["matches"]:
        if parse_date(m["date"]) > now:
            key = str(m["fixture_id"])
            if key in history and history[key].get("evaluation"):
                continue
            history[key] = {
                "fixture_id": m["fixture_id"], "date": m["date"], "round": m["round"],
                "home": m["home"], "away": m["away"], "prediction": m["prediction"],
                "result": None, "evaluation": None,
            }
    by_id = {f["id"]: f for f in fixtures}
    for key, h in history.items():
        f = by_id.get(h["fixture_id"])
        if h["evaluation"] is None and f and is_finished(f):
            hg, ag = f["goals"]["home"], f["goals"]["away"]
            h["result"] = {"home": hg, "away": ag}
            h["evaluation"] = evaluate(h["prediction"], hg, ag)
    return dict(sorted(history.items(), key=lambda kv: kv[1]["date"]))


def run(client, data_dir="data", competition=config.COMPETITION, season=config.SEASON,
        now=None, force_full=False, log=print):
    now = now or datetime.now(timezone.utc)
    store = Storage(data_dir)
    meta = store.load("meta.json", {})
    fixtures = store.load("fixtures.json", [])
    history = store.load("history.json", {})
    before_finished = finished_ids(fixtures)
    refreshed = False

    last_full = meta.get("last_full_refresh")
    stale = not last_full or now - parse_date(last_full) > timedelta(hours=config.FULL_REFRESH_HOURS)

    if force_full or not fixtures or stale:
        log("Refresco completo del calendario (1 petición)")
        raw = client.get(f"competitions/{competition}/matches", season=season).get("matches", [])
        if not raw:
            raise ApiError(f"La API no devolvió partidos para {competition} temporada {season}. "
                           "Comprueba el acceso con scripts/check_access.py.")
        fixtures = sorted((normalize_fixture(x) for x in raw), key=lambda f: f["date"])
        meta["last_full_refresh"] = now.isoformat(timespec="seconds")
        refreshed = True
    else:
        live = matches_in_window(fixtures, now)
        if not live:
            log("No hay partidos en juego: 0 peticiones")
        else:
            by_id = {f["id"]: f for f in fixtures}
            # Fechas en UTC; en la v4 dateTo no se incluye, por eso se pide día+1
            for day in sorted({parse_date(f["date"]).astimezone(timezone.utc).date() for f in live}):
                log(f"Partidos en juego el {day}: actualizando marcadores (1 petición)")
                data = client.get(f"competitions/{competition}/matches", season=season,
                                  dateFrom=day.isoformat(),
                                  dateTo=(day + timedelta(days=1)).isoformat())
                for item in data.get("matches", []):
                    f = normalize_fixture(item)
                    by_id[f["id"]] = f
            fixtures = sorted(by_id.values(), key=lambda f: f["date"])

    newly_finished = finished_ids(fixtures) - before_finished
    if newly_finished:
        log(f"Partidos recién terminados: {len(newly_finished)}")

    if refreshed or newly_finished or not (store.dir / "standings.json").exists():
        log("Actualizando clasificación (1 petición)")
        store.save("standings.json", normalize_standings(
            client.get(f"competitions/{competition}/standings", season=season)))

    # Todo lo derivado se calcula sin peticiones
    predictions = build_predictions(fixtures, now)
    history = update_history(history, predictions, fixtures, now)
    evaluated = [h["evaluation"] for h in history.values() if h["evaluation"]]
    performance = {
        "live": summarize(evaluated),
        "backtest": {**summarize(backtest(model_matches(fixtures))),
                     "note": "Simulación retrospectiva: cada partido se predice solo con los anteriores."},
    }

    store.save("fixtures.json", fixtures)
    store.save("teams.json", team_stats(fixtures))
    store.save("predictions.json", predictions)
    store.save("history.json", history)
    store.save("performance.json", performance)

    if store.changed or refreshed:
        meta.update({
            "competition": competition, "season": season,
            "source": "football-data.org",
            "last_update": now.isoformat(timespec="seconds"),
        })
        store.save("meta.json", meta)

    log(f"Peticiones usadas: {client.calls_made} | "
        f"archivos cambiados: {', '.join(store.changed) or 'ninguno'}")
    return store.changed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Actualiza los datos de la web")
    parser.add_argument("--full", action="store_true", help="forzar refresco completo")
    parser.add_argument("--demo", action="store_true", help="usar datos simulados")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)

    if args.demo:
        from .demo import FakeClient
        client, data_dir = FakeClient(), args.data_dir or "demo_data"
    else:
        from .api_client import FootballDataClient
        client, data_dir = FootballDataClient(), args.data_dir or "data"

    try:
        run(client, data_dir=data_dir, force_full=args.full)
    except QuotaExhausted as e:
        print(f"Límite por minuto alcanzado, se reintentará en la próxima ejecución: {e}")
        return 0  # no es un fallo del job
    except ApiError as e:
        print(f"ERROR de la API: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
