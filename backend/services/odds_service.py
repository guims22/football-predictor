"""
Client The Odds API (cotes bookmakers).

Correction majeure de consommation de quota :
  AVANT : get_odds_for_match recevait competition_code="" (les routes ne le
  passaient jamais) et bouclait donc sur les 12 sports de la table, soit
  12 requetes par prediction. Le quota gratuit de 500 req/mois etait epuise
  en 41 predictions.

  MAINTENANT : 1 requete par ligue, mise en cache 10 min et partagee par tous
  les matchs de cette ligue. Une journee de championnat complete coute
  1 requete au lieu de 120. Le quota restant est lu dans les en-tetes et
  expose par /health.
"""

import os
import re
import time
from difflib import SequenceMatcher

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import httpx
from dotenv import load_dotenv

load_dotenv()

ODDS_API_KEY = os.getenv("ODDS_API_KEY")
BASE_URL = "https://api.the-odds-api.com/v4"
TIMEOUT = 12.0
CACHE_TTL = 600          # 10 min : les cotes bougent lentement hors direct
MIN_MATCH_SCORE = 0.62

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

_odds_cache: dict = {}
QUOTA = {"remaining": None, "used": None, "last_check": None}


def quota_status() -> dict:
    return dict(QUOTA)


# --- rapprochement des noms d'equipes ----------------------------------------

_NOISE = re.compile(
    r"\b(fc|cf|sc|ac|as|ss|rc|cd|afc|fk|sk|sv|bv|vfb|vfl|fsv|tsg|ssc|us|ud|sd|cp|1)\b"
)


def _normalize(name: str) -> str:
    name = (name or "").lower()
    name = name.replace("&", " and ")
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = _NOISE.sub(" ", name)
    return " ".join(name.split())


def _similarity(a: str, b: str) -> float:
    """
    Similarite de noms.

    L'ancienne version renvoyait 0.9 des qu'une chaine etait incluse dans
    l'autre : "Real Madrid" et "Real Sociedad" partagent "real", et surtout
    "Manchester City" etait inclus dans... rien, mais "Milan" matchait
    "Inter Milan" a 0.9. On combine desormais recouvrement de mots et
    similarite de caracteres, ce qui separe ces cas.
    """
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    words_a, words_b = set(na.split()), set(nb.split())
    common = words_a & words_b
    word_score = len(common) / max(len(words_a), len(words_b))
    char_score = SequenceMatcher(None, na, nb).ratio()
    return 0.6 * word_score + 0.4 * char_score


# --- appel API ---------------------------------------------------------------

async def _fetch_sport_odds(sport: str):
    """Recupere toutes les cotes d'une ligue. Mise en cache : 1 requete par ligue."""
    entry = _odds_cache.get(sport)
    if entry and time.time() < entry["expires"]:
        return entry["data"]

    if not ODDS_API_KEY:
        return None

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(
                f"{BASE_URL}/sports/{sport}/odds",
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                    "bookmakers": "bet365,pinnacle,betfair,williamhill",
                },
            )
    except httpx.HTTPError:
        return None

    QUOTA["remaining"] = r.headers.get("x-requests-remaining")
    QUOTA["used"] = r.headers.get("x-requests-used")
    QUOTA["last_check"] = time.time()

    if r.status_code != 200:
        # on cache le vide pour ne pas re-bruler du quota sur une ligue morte
        _odds_cache[sport] = {"data": [], "expires": time.time() + CACHE_TTL}
        return []

    data = r.json()
    _odds_cache[sport] = {"data": data, "expires": time.time() + CACHE_TTL}
    return data


async def get_odds_for_match(home_team: str, away_team: str, competition_code: str = ""):
    """
    Cotes d'un match precis.

    Sans code de competition connu, on renonce plutot que de balayer les
    12 ligues : une prediction ne doit jamais couter 12 requetes de quota.
    """
    sport = COMPETITION_MAP.get((competition_code or "").upper())
    if not sport:
        return None

    games = await _fetch_sport_odds(sport)
    if not games:
        return None

    best, best_score = None, 0.0
    for game in games:
        score = (_similarity(game.get("home_team", ""), home_team)
                 + _similarity(game.get("away_team", ""), away_team)) / 2
        if score > best_score:
            best_score, best = score, game

    if not best or best_score < MIN_MATCH_SCORE:
        return None

    return _extract_implied_probs(best)


def _extract_implied_probs(game: dict):
    """Moyenne les cotes des bookmakers et retire la marge (overround)."""
    home_list, draw_list, away_list = [], [], []
    h_name, a_name = game.get("home_team", ""), game.get("away_team", "")

    for bookie in game.get("bookmakers", []):
        for market in bookie.get("markets", []):
            if market.get("key") != "h2h":
                continue
            for outcome in market.get("outcomes", []):
                name, price = outcome.get("name", ""), outcome.get("price")
                if not price:
                    continue
                if name.strip().lower() == "draw":
                    draw_list.append(price)
                    continue
                sim_h, sim_a = _similarity(name, h_name), _similarity(name, a_name)
                if sim_h > sim_a and sim_h > 0.5:
                    home_list.append(price)
                elif sim_a > sim_h and sim_a > 0.5:
                    away_list.append(price)

    if not (home_list and draw_list and away_list):
        return None

    avg_h = sum(home_list) / len(home_list)
    avg_d = sum(draw_list) / len(draw_list)
    avg_a = sum(away_list) / len(away_list)

    raw_h, raw_d, raw_a = 1 / avg_h, 1 / avg_d, 1 / avg_a
    total = raw_h + raw_d + raw_a

    return {
        "home_win": round(raw_h / total, 3),
        "draw": round(raw_d / total, 3),
        "away_win": round(raw_a / total, 3),
        "source": "bookmakers",
        "overround": round((total - 1) * 100, 2),
        "bookmakers_count": len(home_list),
        "avg_odds": {"home": round(avg_h, 2), "draw": round(avg_d, 2), "away": round(avg_a, 2)},
    }
