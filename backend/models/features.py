"""
Source unique de verite pour la construction des features.

AVANT : train.py et predictor.py calculaient chacun leur vecteur de features,
avec des formules legerement differentes (train.py utilisait cs_rate, predictor.py
utilisait clean_sheets/played). Le modele etait donc entraine sur une distribution
et interroge sur une autre, sans qu'aucune erreur ne soit levee.

MAINTENANT : les deux passent par build_features() ci-dessous. Toute modification
du vecteur casse les deux cotes en meme temps, ce qui est le comportement voulu.
"""

from datetime import datetime
from typing import Optional

# L'ordre de cette liste EST le format du vecteur. Ne jamais reordonner sans
# reentrainer : FEATURE_VERSION est verifiee au chargement du modele.
FEATURE_NAMES = [
    "h_form", "h_gs", "h_gc", "h_cs", "h_played",
    "a_form", "a_gs", "a_gc", "a_cs", "a_played",
    "hh_form", "hh_gs", "hh_gc", "hh_cs",
    "aa_form", "aa_gs", "aa_gc", "aa_cs",
    "d_form", "d_att_home", "d_att_away",
    "h2h_home_rate", "h2h_draw_rate", "h2h_n",
    "h_rest", "a_rest",
]
FEATURE_VERSION = 2
N_FEATURES = len(FEATURE_NAMES)

DEFAULT_GOALS = 1.35   # moyenne buts/equipe/match toutes ligues confondues
FORM_WINDOW = 8


# --- utilitaires -------------------------------------------------------------

def parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def match_goals(match: dict, team_id: int):
    """(buts marques, buts encaisses) pour team_id, ou None si non applicable."""
    score = (match.get("score") or {}).get("fullTime") or {}
    hg, ag = score.get("home"), score.get("away")
    if hg is None or ag is None:
        return None
    home_id = (match.get("homeTeam") or {}).get("id")
    away_id = (match.get("awayTeam") or {}).get("id")
    if home_id == team_id:
        return hg, ag
    if away_id == team_id:
        return ag, hg
    return None


def sort_matches(matches: list) -> list:
    """
    Tri chronologique -- CORRECTIF CRITIQUE.

    L'ancien code faisait finished[-8:] en supposant que la liste etait triee.
    Elle ne l'etait pas : train.py concatenait competition par competition
    (toute la Premier League, puis toute la Bundesliga...) et l'API
    /teams/{id}/matches melange les competitions. On prenait donc "les 8 derniers
    de la liste" au lieu de "les 8 matchs les plus recents", et la ponderation
    par recence etait appliquee dans le desordre.
    """
    return sorted(matches, key=lambda m: m.get("utcDate") or "")


def finished_only(matches: list) -> list:
    return [m for m in matches if m.get("status") == "FINISHED"]


def filter_team(matches: list, team_id: int, venue: str = "all") -> list:
    out = []
    for m in matches:
        home_id = (m.get("homeTeam") or {}).get("id")
        away_id = (m.get("awayTeam") or {}).get("id")
        if venue == "home" and home_id != team_id:
            continue
        if venue == "away" and away_id != team_id:
            continue
        if venue == "all" and team_id not in (home_id, away_id):
            continue
        out.append(m)
    return out


# --- forme -------------------------------------------------------------------

def compute_form(matches: list, team_id: int, venue: str = "all",
                 window: int = FORM_WINDOW) -> dict:
    """
    Forme ponderee par recence sur les `window` derniers matchs.

    `matches` doit deja etre : termines, tries chronologiquement, et anterieurs
    au match a predire. L'anteriorite est la responsabilite de l'appelant, pour
    rendre toute fuite de donnees explicite plutot qu'implicite.
    """
    recent = filter_team(matches, team_id, venue)[-window:]

    wins = draws = losses = 0
    gs_total = gc_total = clean_sheets = 0
    weighted_pts = 0.0
    total_weight = 0.0

    n = len(recent)
    for i, m in enumerate(recent):
        goals = match_goals(m, team_id)
        if goals is None:
            continue
        gs, gc = goals
        # poids lineaire 0.6 -> 1.0 : le match le plus recent pese le plus
        weight = 1.0 if n == 1 else 0.6 + (i / (n - 1)) * 0.4

        gs_total += gs
        gc_total += gc
        if gc == 0:
            clean_sheets += 1

        if gs > gc:
            wins += 1
            weighted_pts += 3 * weight
        elif gs == gc:
            draws += 1
            weighted_pts += 1 * weight
        else:
            losses += 1
        total_weight += 3 * weight

    played = wins + draws + losses
    if played == 0:
        return {
            "wins": 0, "draws": 0, "losses": 0, "played": 0,
            "avg_goals_scored": DEFAULT_GOALS, "avg_goals_conceded": DEFAULT_GOALS,
            "form_score": 0.5, "clean_sheets": 0, "cs_rate": 0.25,
            "xg_attack": DEFAULT_GOALS, "xg_defense": DEFAULT_GOALS,
        }

    avg_gs = gs_total / played
    avg_gc = gc_total / played
    return {
        "wins": wins, "draws": draws, "losses": losses, "played": played,
        "avg_goals_scored": round(avg_gs, 2),
        "avg_goals_conceded": round(avg_gc, 2),
        "form_score": round(weighted_pts / total_weight, 3) if total_weight else 0.5,
        "clean_sheets": clean_sheets,
        "cs_rate": round(clean_sheets / played, 3),
        "xg_attack": round(avg_gs, 2),
        "xg_defense": round(avg_gc, 2),
    }


def compute_h2h(h2h_matches: list, home_team_id: int, away_team_id: int,
                reference_date: Optional[datetime] = None) -> dict:
    """
    Confrontations directes, ponderees par anciennete (demi-vie 2 ans).

    AVANT : un match de 2015 pesait autant qu'un match de 2025.
    """
    hw = aw = d = 0
    hg_total = ag_total = 0
    w_hw = w_aw = w_d = 0.0
    total_w = 0.0

    for m in finished_only(h2h_matches):
        goals = match_goals(m, home_team_id)
        if goals is None:
            continue
        hg, ag = goals

        weight = 1.0
        if reference_date is not None:
            md = parse_date(m.get("utcDate", ""))
            if md is not None:
                years = abs((reference_date - md).days) / 365.25
                weight = 0.5 ** (years / 2.0)   # demi-vie 2 ans

        hg_total += hg
        ag_total += ag
        if hg > ag:
            hw += 1
            w_hw += weight
        elif hg == ag:
            d += 1
            w_d += weight
        else:
            aw += 1
            w_aw += weight
        total_w += weight

    total = hw + d + aw
    return {
        "home_wins": hw, "draws": d, "away_wins": aw, "total": total,
        "avg_goals_home": round(hg_total / total, 2) if total else 0,
        "avg_goals_away": round(ag_total / total, 2) if total else 0,
        "w_home_rate": round(w_hw / total_w, 3) if total_w else 0.0,
        "w_draw_rate": round(w_d / total_w, 3) if total_w else 0.0,
        "w_away_rate": round(w_aw / total_w, 3) if total_w else 0.0,
        "weight_sum": round(total_w, 3),
    }


def rest_days(team_matches: list, match_date: Optional[datetime]) -> float:
    """Jours depuis le dernier match joue. 7 par defaut (rythme hebdomadaire)."""
    if match_date is None or not team_matches:
        return 7.0
    last = parse_date(team_matches[-1].get("utcDate", ""))
    if last is None:
        return 7.0
    return float(min(abs((match_date - last).days), 30))


# --- vecteur final -----------------------------------------------------------

def build_features(home_form: dict, away_form: dict,
                   home_form_home: dict, away_form_away: dict,
                   h2h: dict, home_rest: float, away_rest: float) -> list:
    """Construit le vecteur dans l'ordre de FEATURE_NAMES. Utilise par train ET predict."""
    v = [
        home_form["form_score"], home_form["avg_goals_scored"],
        home_form["avg_goals_conceded"], home_form["cs_rate"], float(home_form["played"]),

        away_form["form_score"], away_form["avg_goals_scored"],
        away_form["avg_goals_conceded"], away_form["cs_rate"], float(away_form["played"]),

        home_form_home["form_score"], home_form_home["avg_goals_scored"],
        home_form_home["avg_goals_conceded"], home_form_home["cs_rate"],

        away_form_away["form_score"], away_form_away["avg_goals_scored"],
        away_form_away["avg_goals_conceded"], away_form_away["cs_rate"],

        home_form["form_score"] - away_form["form_score"],
        home_form["avg_goals_scored"] - away_form["avg_goals_conceded"],
        away_form["avg_goals_scored"] - home_form["avg_goals_conceded"],

        h2h.get("w_home_rate", 0.0), h2h.get("w_draw_rate", 0.0), float(h2h.get("total", 0)),

        home_rest, away_rest,
    ]
    if len(v) != N_FEATURES:
        raise ValueError(f"attendu {N_FEATURES} features, obtenu {len(v)}")
    return v
