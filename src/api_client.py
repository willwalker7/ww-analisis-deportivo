"""Cliente mínimo de football-data.org (v4).

Plan gratuito: 10 peticiones por minuto y sin límite diario. El cliente espera
solo si se va a pasar del límite por minuto.
"""
import os
import time
from collections import deque

import requests

from . import config


class ApiError(Exception):
    pass


class QuotaExhausted(ApiError):
    pass


class FootballDataClient:
    def __init__(self, api_key=None, base_url=config.API_BASE_URL, timeout=20,
                 per_minute=config.PER_MINUTE_LIMIT):
        self.api_key = api_key or os.environ.get("FOOTBALL_DATA_KEY")
        if not self.api_key:
            raise ApiError("Falta la clave: define la variable de entorno FOOTBALL_DATA_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.per_minute = per_minute
        self.session = requests.Session()
        self.session.headers.update({"X-Auth-Token": self.api_key})
        self.calls_made = 0
        self._recent = deque()

    def _respect_per_minute_limit(self):
        now = time.monotonic()
        while self._recent and now - self._recent[0] > 60:
            self._recent.popleft()
        if len(self._recent) >= self.per_minute:
            time.sleep(61 - (now - self._recent[0]))
        self._recent.append(time.monotonic())

    def get(self, path, **params):
        self._respect_per_minute_limit()
        resp = self.session.get(f"{self.base_url}/{path.lstrip('/')}",
                                params=params, timeout=self.timeout)
        self.calls_made += 1
        if resp.status_code == 429:
            raise QuotaExhausted("Límite de peticiones por minuto alcanzado (HTTP 429)")
        if resp.status_code >= 400:
            try:
                message = resp.json().get("message", resp.text)
            except ValueError:
                message = resp.text
            raise ApiError(f"HTTP {resp.status_code}: {message}")
        return resp.json()
