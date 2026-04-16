import math
import pickle
import os
import numpy as np
from typing import Optional

# ─── Chargement du modele XGBoost ────────────────────────────────────────────

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "xgboost_model.pkl")
_xgb_model = None

def _load_xgb():
    global _xgb_model
    if _xgb_model is None and os.path.exists(_MODEL_PATH):
        try:
            with open(_MODEL_PATH, "rb") as f:
                data = pickle.load(f)
                _xgb_model = data["model"]
                print(f"XGBoost charge (precision: {data.get('accuracy',0)*100:.1f}%)")
        except Exception as e:
            print(f"XGBoost non disponible: {e}")
    return _xgb_model

_load_xgb()


# ─── Poisson ──────────────────────────────────────────────────────────────────

def _poisson(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    k = min(k, 20)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_probs(home_xg: float, away_xg: float, max_goals: int = 7) -> dict:
    """Calculate full score matrix and H/D/A probabilities via Poisson."""
    home_xg = max(0.1, home_xg)
    away_xg = max(0.1, away_xg)

    home_win = draw = away_win = 0.0
    best_score = "1-1"
    best_p = 0.0

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson(home_xg, h) * _poisson(away_xg, a)
            if p > best_p:
                best_p = p
                best_score = f"{h}-{a}"
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p

    total = home_win + draw + away_win
    if total > 0:
        home_win /= total
        draw /= total
        away_win /= total

    return {
        "home_win": round(home_win, 3),
        "draw": round(draw, 3),
        "away_win": round(away_win, 3),
        "predicted_score": best_score,
    }


# ─── Form calculation ─────────────────────────────────────────────────────────

def calculate_form(matches: list, team_id: int, venue: str = "all") -> dict:
    """
    Calculate weighted team form.
    venue: 'home' | 'away' | 'all'
    More recent matches get higher weight (exponential decay).
    """
    finished = [m for m in matches if m.get("status") == "FINISHED"]

    # Filter by venue
    if venue == "home":
        finished = [m for m in finished if m["homeTeam"]["id"] == team_id]
    elif venue == "away":
        finished = [m for m in finished if m["awayTeam"]["id"] == team_id]

    recent = finished[-8:]  # Last 8 matches

    wins = draws = losses = 0
    goals_scored = goals_conceded = 0
    clean_sheets = 0
    weighted_pts = 0.0
    total_weight = 0.0

    for i, match in enumerate(recent):
        # More recent = higher weight (last match weight = 1.0)
        weight = 0.6 + (i / max(len(recent) - 1, 1)) * 0.4

        home_id = match["homeTeam"]["id"]
        score = match.get("score", {}).get("fullTime", {})
        hg = score.get("home") or 0
        ag = score.get("away") or 0

        if home_id == team_id:
            gs, gc = hg, ag
        elif match["awayTeam"]["id"] == team_id:
            gs, gc = ag, hg
        else:
            continue

        goals_scored += gs
        goals_conceded += gc
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

        total_weight += 3 * weight  # max possible

    played = wins + draws + losses
    if played == 0:
        return {
            "wins": 0, "draws": 0, "losses": 0,
            "avg_goals_scored": 1.2, "avg_goals_conceded": 1.2,
            "form_score": 0.5, "clean_sheets": 0, "played": 0,
            "xg_attack": 1.2, "xg_defense": 1.2,
        }

    form_score = weighted_pts / total_weight if total_weight > 0 else 0.5
    avg_scored = goals_scored / played
    avg_conceded = goals_conceded / played

    return {
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "avg_goals_scored": round(avg_scored, 2),
        "avg_goals_conceded": round(avg_conceded, 2),
        "form_score": round(form_score, 3),
        "clean_sheets": clean_sheets,
        "played": played,
        "xg_attack": round(avg_scored, 2),
        "xg_defense": round(avg_conceded, 2),
    }


def calculate_h2h_summary(h2h_matches: list, home_team_id: int, away_team_id: int) -> dict:
    home_wins = away_wins = draws = 0
    home_goals = away_goals = 0

    for match in h2h_matches:
        if match.get("status") != "FINISHED":
            continue
        score = match.get("score", {}).get("fullTime", {})
        hg = score.get("home") or 0
        ag = score.get("away") or 0
        h_id = match["homeTeam"]["id"]

        if h_id == home_team_id:
            home_goals += hg
            away_goals += ag
            if hg > ag:
                home_wins += 1
            elif hg == ag:
                draws += 1
            else:
                away_wins += 1
        else:
            home_goals += ag
            away_goals += hg
            if ag > hg:
                home_wins += 1
            elif ag == hg:
                draws += 1
            else:
                away_wins += 1

    total = home_wins + away_wins + draws
    return {
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "total": total,
        "avg_goals_home": round(home_goals / total, 2) if total else 0,
        "avg_goals_away": round(away_goals / total, 2) if total else 0,
    }


# ─── Main prediction ──────────────────────────────────────────────────────────

def predict_match(
    home_form: dict,
    away_form: dict,
    home_form_home: dict,   # form only at home
    away_form_away: dict,   # form only away
    h2h: Optional[dict] = None,
    home_position: Optional[int] = None,
    away_position: Optional[int] = None,
    league_size: int = 20,
) -> dict:
    """
    Full prediction using:
    - Poisson distribution on expected goals
    - Weighted form (home/away specific + overall)
    - H2H adjustment
    - League standings factor
    """
    HOME_ADV_GOALS = 0.25   # Home teams score ~0.25 more goals per game
    HOME_ADV_CONCEDE = 0.15  # Home teams concede ~0.15 fewer goals per game

    # Expected goals: blend overall form + home/away specific form
    home_xg_attack = home_form["xg_attack"] * 0.4 + home_form_home["xg_attack"] * 0.6
    home_xg_defense = home_form["xg_defense"] * 0.4 + home_form_home["xg_defense"] * 0.6
    away_xg_attack = away_form["xg_attack"] * 0.4 + away_form_away["xg_attack"] * 0.6
    away_xg_defense = away_form["xg_defense"] * 0.4 + away_form_away["xg_defense"] * 0.6

    # Expected goals per team
    home_xg = (home_xg_attack + away_xg_defense) / 2 + HOME_ADV_GOALS
    away_xg = (away_xg_attack + home_xg_defense) / 2 - HOME_ADV_CONCEDE

    # League position adjustment
    if home_position and away_position and league_size > 0:
        home_rank_factor = (league_size - home_position) / league_size * 0.15
        away_rank_factor = (league_size - away_position) / league_size * 0.15
        home_xg += home_rank_factor * 0.3
        away_xg += away_rank_factor * 0.3

    # H2H adjustment
    if h2h and h2h["total"] >= 3:
        total = h2h["total"]
        h2h_home_rate = h2h["home_wins"] / total
        h2h_away_rate = h2h["away_wins"] / total
        home_xg *= (1 + (h2h_home_rate - 0.45) * 0.15)
        away_xg *= (1 + (h2h_away_rate - 0.30) * 0.15)

    home_xg = max(0.3, min(home_xg, 4.0))
    away_xg = max(0.3, min(away_xg, 4.0))

    # Poisson probabilities
    probs = _poisson_probs(home_xg, away_xg)

    # ── Ensemble XGBoost + Poisson ───────────────────────────────────────────
    xgb = _load_xgb()
    method = "Poisson"

    if xgb is not None:
        try:
            features = np.array([[
                home_form["form_score"], home_form["avg_goals_scored"], home_form["avg_goals_conceded"], home_form.get("clean_sheets", 0) / max(home_form["played"], 1),
                away_form["form_score"], away_form["avg_goals_scored"], away_form["avg_goals_conceded"], away_form.get("clean_sheets", 0) / max(away_form["played"], 1),
                home_form_home["form_score"], home_form_home["avg_goals_scored"], home_form_home["avg_goals_conceded"],
                away_form_away["form_score"], away_form_away["avg_goals_scored"], away_form_away["avg_goals_conceded"],
                home_form["form_score"] - away_form["form_score"],
                home_form["avg_goals_scored"] - away_form["avg_goals_conceded"],
                away_form["avg_goals_scored"] - home_form["avg_goals_conceded"],
            ]])
            xgb_proba = xgb.predict_proba(features)[0]  # [home_win, draw, away_win]
            # Ensemble: 55% Poisson + 45% XGBoost
            W_POISSON, W_XGB = 0.55, 0.45
            final_home = probs["home_win"] * W_POISSON + xgb_proba[0] * W_XGB
            final_draw  = probs["draw"]     * W_POISSON + xgb_proba[1] * W_XGB
            final_away  = probs["away_win"] * W_POISSON + xgb_proba[2] * W_XGB
            # Renormalise
            total = final_home + final_draw + final_away
            probs["home_win"] = round(final_home / total, 3)
            probs["draw"]     = round(final_draw  / total, 3)
            probs["away_win"] = round(final_away  / total, 3)
            method = "Ensemble XGBoost+Poisson"
        except Exception as e:
            print(f"XGBoost prediction failed, using Poisson only: {e}")

    # Additional bet types
    btts = _btts_prob(home_xg, away_xg)
    over_2_5 = _over_under_prob(home_xg, away_xg, 2.5)
    over_1_5 = _over_under_prob(home_xg, away_xg, 1.5)

    confidence = round(max(probs["home_win"], probs["draw"], probs["away_win"]) * 100, 1)

    return {
        "home_win": probs["home_win"],
        "draw": probs["draw"],
        "away_win": probs["away_win"],
        "predicted_score": probs["predicted_score"],
        "confidence": confidence,
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "btts": round(btts, 3),
        "over_2_5": round(over_2_5, 3),
        "over_1_5": round(over_1_5, 3),
        "method": method,
    }


def blend_with_odds(prediction: dict, odds: dict) -> dict:
    """
    Blend prediction with bookmaker implied probabilities.
    Weights: 35% Poisson/XGBoost + 65% Market odds
    Market odds are the strongest predictor available.
    """
    W_MODEL = 0.35
    W_ODDS  = 0.65

    blended_home = prediction["home_win"] * W_MODEL + odds["home_win"] * W_ODDS
    blended_draw = prediction["draw"]     * W_MODEL + odds["draw"]     * W_ODDS
    blended_away = prediction["away_win"] * W_MODEL + odds["away_win"] * W_ODDS

    total = blended_home + blended_draw + blended_away
    prediction["home_win"] = round(blended_home / total, 3)
    prediction["draw"]     = round(blended_draw  / total, 3)
    prediction["away_win"] = round(blended_away  / total, 3)
    prediction["confidence"] = round(max(prediction["home_win"], prediction["draw"], prediction["away_win"]) * 100, 1)
    prediction["method"] = "Ensemble+Bookmakers"
    prediction["odds"] = odds["avg_odds"]
    return prediction


def _btts_prob(home_xg: float, away_xg: float) -> float:
    """Probability that BOTH teams score at least 1 goal."""
    home_scores = 1 - _poisson(home_xg, 0)
    away_scores = 1 - _poisson(away_xg, 0)
    return home_scores * away_scores


def _over_under_prob(home_xg: float, away_xg: float, line: float) -> float:
    """Probability that total goals > line."""
    over = 0.0
    threshold = int(line) + 1
    for total in range(threshold, 15):
        for h in range(total + 1):
            a = total - h
            over += _poisson(home_xg, h) * _poisson(away_xg, a)
    return min(over, 0.99)
