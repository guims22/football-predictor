import httpx
import os
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
BASE_URL = "https://api.football-data.org/v4"

HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}

TIMEOUT = 15.0


async def get_today_matches():
    today = date.today().isoformat()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/matches",
            headers=HEADERS,
            params={"dateFrom": today, "dateTo": today},
        )
        response.raise_for_status()
        return response.json()


async def get_upcoming_matches(days: int = 7):
    today = date.today()
    date_to = (today + timedelta(days=days)).isoformat()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/matches",
            headers=HEADERS,
            params={"dateFrom": today.isoformat(), "dateTo": date_to},
        )
        response.raise_for_status()
        return response.json()


async def get_competitions():
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(f"{BASE_URL}/competitions", headers=HEADERS)
        response.raise_for_status()
        return response.json()


async def get_competition_matches(competition_code: str, days_back: int = 7, days_ahead: int = 7):
    today = date.today()
    date_from = (today - timedelta(days=days_back)).isoformat()
    date_to = (today + timedelta(days=days_ahead)).isoformat()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/competitions/{competition_code}/matches",
            headers=HEADERS,
            params={"dateFrom": date_from, "dateTo": date_to},
        )
        response.raise_for_status()
        return response.json()


async def get_team_matches(team_id: int, limit: int = 10):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/teams/{team_id}/matches",
            headers=HEADERS,
            params={"limit": limit, "status": "FINISHED"},
        )
        response.raise_for_status()
        return response.json()


async def get_head_to_head(match_id: int, limit: int = 10):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/matches/{match_id}/head2head",
            headers=HEADERS,
            params={"limit": limit},
        )
        response.raise_for_status()
        return response.json()


async def get_competition_standings(competition_code: str):
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(
            f"{BASE_URL}/competitions/{competition_code}/standings",
            headers=HEADERS,
        )
        response.raise_for_status()
        return response.json()
