"""
Client football-data.org.

Corrections :
  * rate limiting reel (tier gratuit = 10 req/min) : sans lui, 4 predictions
    simultanees declenchaient un 429 et l'app renvoyait 500
  * cache borne (l'ancien dict grandissait indefiniment)
  * erreurs API traduites en codes HTTP parlants au lieu d'un 500 generique
  * truststore : indispensable derriere un antivirus qui intercepte le TLS
  * tri chronologique et fenetre suffisante pour /teams/{id}/matches
"""

import asyncio
import os
import time
from collections import OrderedDict
from datetime import date, timedelta

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import httpx
from dotenv import load_dotenv

load_dotenv()

FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
BASE_URL = "https://api.football-data.org/v4"
TIMEOUT = 20.0
MAX_CACHE_ENTRIES = 500


class FootballAPIError(Exception):
    """Erreur API avec un status HTTP exploitable par les routes."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


# --- cache borne (LRU + TTL) -------------------------------------------------

_cache: "OrderedDict[str, dict]" = OrderedDict()


def _cache_get(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() >= entry["expires"]:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return entry["data"]


def _cache_set(key: str, data, ttl_seconds: int):
    _cache[key] = {"data": data, "expires": time.time() + ttl_seconds}
    _cache.move_to_end(key)
    while len(_cache) > MAX_CACHE_ENTRIES:
        _cache.popitem(last=False)


def cache_stats() -> dict:
    return {"entries": len(_cache), "max_entries": MAX_CACHE_ENTRIES}


# --- rate limiter ------------------------------------------------------------

class _RateLimiter:
    """
    Fenetre glissante : 10 requetes par minute maximum.

    L'ancien code n'en avait aucun cote API (seulement dans le script
    d'entrainement), donc quelques predictions en parallele suffisaient
    a epuiser le quota.
    """

    def __init__(self, max_calls: int = 10, period: float = 60.0):
        self.max_calls = max_calls
        self.period = period
        self._calls: list = []
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < self.period]
            if len(self._calls) >= self.max_calls:
                wait = self.period - (now - self._calls[0]) + 0.1
                await asyncio.sleep(max(wait, 0))
                now = time.monotonic()
                self._calls = [t for t in self._calls if now - t < self.period]
            self._calls.append(time.monotonic())


_limiter = _RateLimiter()


async def _get(path: str, params: dict = None, cache_key: str = None, ttl: int = 1800):
    if not FOOTBALL_API_KEY:
        raise FootballAPIError(
            "FOOTBALL_API_KEY absente : renseigner backend/.env (voir .env.example)", 503
        )

    if cache_key:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    await _limiter.acquire()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{BASE_URL}{path}",
                headers={"X-Auth-Token": FOOTBALL_API_KEY},
                params=params,
            )
    except httpx.HTTPError as e:
        raise FootballAPIError(f"football-data injoignable : {e}", 504)

    if r.status_code == 429:
        raise FootballAPIError(
            "Quota football-data.org atteint (10 requetes/min). Reessayer dans une minute.", 429
        )
    if r.status_code == 403:
        raise FootballAPIError(
            "Ressource hors abonnement (le tier gratuit couvre 3 saisons et 13 competitions).", 403
        )
    if r.status_code == 404:
        raise FootballAPIError("Ressource introuvable chez football-data.org.", 404)
    if r.status_code >= 400:
        raise FootballAPIError(f"football-data a repondu {r.status_code}", 502)

    data = r.json()
    if cache_key:
        _cache_set(cache_key, data, ttl)
    return data


# --- endpoints ---------------------------------------------------------------

async def get_today_matches():
    """
    Matchs du jour.

    CORRECTIF : football-data.org renvoie une liste VIDE quand dateFrom et dateTo
    sont identiques -- verifie directement contre l'API :
        dateFrom=2026-09-10 & dateTo=2026-09-10 -> 0 match
        dateFrom=2026-09-10 & dateTo=2026-09-11 -> 8 matchs, tous le 10
    L'ecran d'accueil affichait donc "Aucun match disponible" en permanence,
    depuis la toute premiere version.

    On demande donc un jour de plus, puis on refiltre sur la date du jour --
    l'intervalle elargi peut ramener des matchs de nuit rattaches au lendemain.
    """
    today = date.today()
    today_iso = today.isoformat()
    tomorrow_iso = (today + timedelta(days=1)).isoformat()

    data = await _get(
        "/matches",
        {"dateFrom": today_iso, "dateTo": tomorrow_iso},
        cache_key=f"today_{today_iso}",
        ttl=900,
    )

    matches = [m for m in data.get("matches", [])
               if (m.get("utcDate") or "").startswith(today_iso)]
    return {**data, "matches": matches, "count": len(matches)}


async def get_upcoming_matches(days: int = 7):
    today = date.today()
    date_to = (today + timedelta(days=days)).isoformat()
    return await _get("/matches", {"dateFrom": today.isoformat(), "dateTo": date_to},
                      cache_key=f"upcoming_{today.isoformat()}_{days}", ttl=1800)


async def get_competitions():
    return await _get("/competitions", cache_key="competitions", ttl=86400)


async def get_competition_matches(competition_code: str, days_back: int = 7, days_ahead: int = 7):
    today = date.today()
    return await _get(
        f"/competitions/{competition_code}/matches",
        {"dateFrom": (today - timedelta(days=days_back)).isoformat(),
         "dateTo": (today + timedelta(days=days_ahead)).isoformat()},
        cache_key=f"comp_{competition_code}_{today.isoformat()}_{days_back}_{days_ahead}",
        ttl=1800,
    )


async def get_team_matches(team_id: int, limit: int = 40):
    """
    Historique d'une equipe.

    limit passe de 16 a 40 : avec 16 matchs toutes competitions confondues,
    il ne restait souvent que 5 ou 6 matchs a domicile, alors que la forme
    domicile/exterieur en demande 8. La fenetre etait structurellement trop courte.
    """
    return await _get(f"/teams/{team_id}/matches",
                      {"limit": limit, "status": "FINISHED"},
                      cache_key=f"team_{team_id}_{limit}", ttl=3600)


async def get_head_to_head(match_id: int, limit: int = 10):
    return await _get(f"/matches/{match_id}/head2head", {"limit": limit},
                      cache_key=f"h2h_{match_id}_{limit}", ttl=86400)


async def get_competition_standings(competition_code: str):
    return await _get(f"/competitions/{competition_code}/standings",
                      cache_key=f"standings_{competition_code}_{date.today().isoformat()}",
                      ttl=3600)


def extract_positions(standings_data: dict, home_team_id: int, away_team_id: int):
    """
    Retrouve les positions au classement. Renvoie (pos_dom, pos_ext, taille_ligue).

    Cette fonction manquait : predict_match() acceptait home_position/away_position
    et le prompt Claude les affichait, mais aucune route ne les calculait jamais.
    Le facteur classement etait donc du code mort.
    """
    for table in standings_data.get("standings", []):
        if table.get("type") != "TOTAL":
            continue
        rows = table.get("table", [])
        positions = {(r.get("team") or {}).get("id"): r.get("position") for r in rows}
        if home_team_id in positions and away_team_id in positions:
            return positions[home_team_id], positions[away_team_id], len(rows)
    return None, None, 20
