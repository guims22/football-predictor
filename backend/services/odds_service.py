import httpx
import os
import re
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
TIMEOUT = 10.0

# Mapping football-data.org competition codes -> Odds API sport keys
COMPETITION_MAP = {
    "PL":  "soccer_epl",
    "FL1": "soccer_france_ligue_one",
    "BL1": "soccer_germany_bundesliga",
    "SA":  "soccer_italy_serie_a",
    "PD":  "soccer_spain_la_liga",
    "CL":  "soccer_uefa_champs_league",
    "ELC": "soccer_england_efl_champ",
    "DED": "soccer_netherlands_eredivisie",
    "PPL": "soccer_portugal_primeira_liga",
    "BSA": "soccer_brazil_campeonato",
    "WC":  "soccer_fifa_world_cup",
    "EC":  "soccer_uefa_european_championship",
}


def _normalize(name: str) -> str:
    """Normalize team name for fuzzy matching."""
    name = name.lower()
    name = re.sub(r"\b(fc|cf|sc|ac|as|ss|rc|cd|afc|fk|sk|sv|bv|vfb|1\.|fsv)\b", "", name)
    name = re.sub(r"[^a-z0-9 ]", "", name)
    return name.strip()


def _similarity(a: str, b: str) -> float:
    """Simple character overlap similarity."""
    a, b = _normalize(a), _normalize(b)
    if a == b:
        return 1.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return 0.9
    # Count matching words
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    common = words_a & words_b
    return len(common) / max(len(words_a), len(words_b))


async def get_odds_for_match(
    home_team: str,
    away_team: str,
    competition_code: str = "",
) -> dict | None:
    """
    Fetch bookmaker odds for a specific match.
    Returns implied probabilities {home_win, draw, away_win} or None.
    """
    sports_to_check = []

    if competition_code and competition_code in COMPETITION_MAP:
        sports_to_check.append(COMPETITION_MAP[competition_code])
    else:
        # Try all soccer sports
        sports_to_check = list(COMPETITION_MAP.values())

    for sport in sports_to_check:
        result = await _fetch_odds(sport, home_team, away_team)
        if result:
            return result

    return None


async def _fetch_odds(sport: str, home_team: str, away_team: str) -> dict | None:
    """Fetch and match odds from a specific sport."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{BASE_URL}/sports/{sport}/odds",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                    "bookmakers": "bet365,pinnacle,betfair",
                },
            )
            if r.status_code != 200:
                return None
            games = r.json()
    except Exception:
        return None

    best_match = None
    best_score = 0.0

    for game in games:
        h_score = _similarity(game.get("home_team", ""), home_team)
        a_score = _similarity(game.get("away_team", ""), away_team)
        score = (h_score + a_score) / 2

        if score > best_score and score >= 0.6:
            best_score = score
            best_match = game

    if not best_match:
        return None

    return _extract_implied_probs(best_match)


def _extract_implied_probs(game: dict) -> dict | None:
    """
    Average odds across bookmakers and convert to implied probabilities.
    Removes the overround (vigorish) via normalization.
    """
    home_odds_list, draw_odds_list, away_odds_list = [], [], []

    for bookie in game.get("bookmakers", []):
        for market in bookie.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = {o["name"]: o["price"] for o in market.get("outcomes", [])}
            h_name = game.get("home_team", "")
            a_name = game.get("away_team", "")

            # Match outcome names
            for name, price in outcomes.items():
                sim_h = _similarity(name, h_name)
                sim_a = _similarity(name, a_name)
                if name.lower() == "draw":
                    draw_odds_list.append(price)
                elif sim_h > sim_a and sim_h > 0.5:
                    home_odds_list.append(price)
                elif sim_a > sim_h and sim_a > 0.5:
                    away_odds_list.append(price)

    if not home_odds_list or not draw_odds_list or not away_odds_list:
        return None

    # Average odds
    avg_home = sum(home_odds_list) / len(home_odds_list)
    avg_draw = sum(draw_odds_list) / len(draw_odds_list)
    avg_away = sum(away_odds_list) / len(away_odds_list)

    # Raw implied probs
    raw_h = 1 / avg_home
    raw_d = 1 / avg_draw
    raw_a = 1 / avg_away

    # Remove overround
    total = raw_h + raw_d + raw_a
    return {
        "home_win": round(raw_h / total, 3),
        "draw":     round(raw_d / total, 3),
        "away_win": round(raw_a / total, 3),
        "source":   "bookmakers",
        "avg_odds": {
            "home": round(avg_home, 2),
            "draw": round(avg_draw, 2),
            "away": round(avg_away, 2),
        },
    }
