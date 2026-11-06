"""Configuración general. Todo se puede sobrescribir con variables de entorno."""
import os

API_BASE_URL = "https://api.football-data.org/v4"

# PD = Primera División (LaLiga) en football-data.org.
# Temporada = año en que empieza (2026 -> 2026-27).
COMPETITION = os.environ.get("COMPETITION", "PD")
SEASON = int(os.environ.get("SEASON", "2026"))

# Plan gratuito: 10 peticiones por minuto, sin límite diario
PER_MINUTE_LIMIT = int(os.environ.get("PER_MINUTE_LIMIT", "10"))

# Cada cuánto se fuerza un refresco completo del calendario (horas)
FULL_REFRESH_HOURS = 20
# Ventana en la que un partido se considera "en juego" (minutos desde el inicio).
# Algo amplia porque en el plan gratuito los marcadores llegan con retraso.
LIVE_WINDOW_MINUTES = 200
# Horizonte de predicciones (días hacia delante)
PREDICTION_HORIZON_DAYS = 14

# Estados internos (se traducen desde los de football-data.org en stats.py)
FINISHED = {"FT"}
NOT_STARTED = {"NS"}
LIVE = {"LIVE", "HT"}
CANCELLED = {"PST", "CANC", "SUSP", "AWD"}
