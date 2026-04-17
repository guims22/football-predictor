import httpx
import os
import time
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

TIMEOUT = 15.0

# ─── Simple in-memory cache ───────────────────────────────────────────────────

_cache: dict = {}

def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() < entry["expires"]:
        return entry["data"]
    return None

def _cache_set(key: str, data, ttl_seconds: int):
    _cache[key] = {"data": data, "expires": time.time() + ttl_seconds}

# ─── API calls with cache ─────────────────────────────────────────────────────

async def get_today_matches():
    today = date.today().isoformat()
    key = f"today_{today}"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/matches",
            headers=HEADERS,
            params={"dateFrom": today, "dateTo": today},
        )
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=1800)  # 30 min
        return data


async def get_upcoming_matches(days: int = 7):
    today = date.today()
    date_to = (today + timedelta(days=days)).isoformat()
    key = f"upcoming_{today.isoformat()}_{days}"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/matches",
            headers=HEADERS,
            params={"dateFrom": today.isoformat(), "dateTo": date_to},
        )
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=1800)  # 30 min
        return data


async def get_competitions():
    key = "competitions"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BASE_URL}/competitions", headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=86400)  # 24h
        return data


async def get_competition_matches(competition_code: str, days_back: int = 7, days_ahead: int = 7):
    today = date.today()
    date_from = (today - timedelta(days=days_back)).isoformat()
    date_to = (today + timedelta(days=days_ahead)).isoformat()
    key = f"comp_matches_{competition_code}_{today.isoformat()}"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/competitions/{competition_code}/matches",
            headers=HEADERS,
            params={"dateFrom": date_from, "dateTo": date_to},
        )
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=1800)  # 30 min
        return data


async def get_team_matches(team_id: int, limit: int = 10):
    key = f"team_matches_{team_id}_{limit}"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/teams/{team_id}/matches",
            headers=HEADERS,
            params={"limit": limit, "status": "FINISHED"},
        )
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=3600)  # 1h
        return data


async def get_head_to_head(match_id: int, limit: int = 10):
    key = f"h2h_{match_id}_{limit}"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/matches/{match_id}/head2head",
            headers=HEADERS,
            params={"limit": limit},
        )
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=86400)  # 24h (H2H ne change pas)
        return data


async def get_competition_standings(competition_code: str):
    key = f"standings_{competition_code}_{date.today().isoformat()}"
    cached = _cache_get(key)
    if cached:
        return cached
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/competitions/{competition_code}/standings",
            headers=HEADERS,
        )
        response.raise_for_status()
        data = response.json()
        _cache_set(key, data, ttl_seconds=3600)  # 1h
        return data
