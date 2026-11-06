"""Comprueba tu clave de football-data.org antes de activar el job (2 peticiones).

Uso en Windows (CMD):
    set FOOTBALL_DATA_KEY=tu_clave
    py scripts\\check_access.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.api_client import ApiError, FootballDataClient  # noqa: E402
from src.stats import STATUS_MAP  # noqa: E402


def main():
    try:
        client = FootballDataClient()
        comp = client.get(f"competitions/{config.COMPETITION}")
        current = comp.get("currentSeason") or {}
        print(f"Clave válida. Competición: {comp.get('name')} | temporada actual: "
              f"{current.get('startDate')} → {current.get('endDate')} "
              f"(jornada {current.get('currentMatchday')})")

        matches = client.get(f"competitions/{config.COMPETITION}/matches",
                             season=config.SEASON).get("matches", [])
    except ApiError as e:
        print(f"\n❌ La API ha respondido con un error:\n   {e}")
        return 1

    if not matches:
        print(f"\n⚠️  0 partidos para {config.COMPETITION}, temporada {config.SEASON}. "
              "Revisa COMPETITION/SEASON.")
        return 1

    finished = sum(1 for m in matches if STATUS_MAP.get(m["status"]) in config.FINISHED)
    print(f"\n✅ Acceso correcto: {len(matches)} partidos de la temporada {config.SEASON} "
          f"({finished} ya jugados).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
