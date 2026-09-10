"""
Moteur de prediction : Poisson bivarie (Dixon-Coles) + XGBoost + cotes bookmakers.
"""

import math
import os
import pickle
from typing import Optional

import numpy as np

from models.features import (
    FEATURE_VERSION,
    N_FEATURES,
    build_features,
    compute_form,
    compute_h2h,
    sort_matches,
    finished_only,
    filter_team,
    rest_days,
    parse_date,
)

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "xgboost_model.pkl")

# Etat expose par /health : avant, un echec de chargement etait invisible.
MODEL_STATUS = {
    "loaded": False,
    "reason": "non charge",
    "accuracy": None,
    "log_loss": None,
    "trained_at": None,
    "feature_version": None,
}

_xgb_model = None
_ensemble_weights = {"poisson": 0.55, "xgb": 0.45}


def _load_xgb():
    """
    Charge le modele XGBoost.

    CORRECTIF : avant, toute exception ici etait avalee par un except silencieux
    et l'API repartait en Poisson pur sans le dire. En prod (Railway), xgboost
    n'etait meme pas dans requirements.txt, donc le modele n'a jamais tourne.
    """
    global _xgb_model, _ensemble_weights
    if _xgb_model is not None:
        return _xgb_model

    if not os.path.exists(_MODEL_PATH):
        MODEL_STATUS["reason"] = f"fichier absent : {_MODEL_PATH} (lancer python -m models.train)"
        return None

    try:
        import xgboost  # noqa: F401  -- verifie explicitement la dependance
    except ImportError:
        MODEL_STATUS["reason"] = "xgboost non installe (pip install -r requirements.txt)"
        return None

    try:
        with open(_MODEL_PATH, "rb") as f:
            data = pickle.load(f)
    except Exception as e:
        MODEL_STATUS["reason"] = f"pickle illisible : {e}"
        return None

    version = data.get("feature_version")
    if version != FEATURE_VERSION:
        MODEL_STATUS["reason"] = (
            f"modele obsolete (features v{version}, code v{FEATURE_VERSION}) -- reentrainer"
        )
        return None

    _xgb_model = data["model"]
    _ensemble_weights = data.get("ensemble_weights", _ensemble_weights)
    MODEL_STATUS.update({
        "loaded": True,
        "reason": "ok",
        "accuracy": data.get("accuracy"),
        "log_loss": data.get("log_loss"),
        "trained_at": data.get("trained_at"),
        "feature_version": version,
        "n_samples": data.get("n_samples"),
        "seasons": data.get("seasons"),
    })
    return _xgb_model


_load_xgb()


# --- Poisson / Dixon-Coles ---------------------------------------------------

LEAGUE_AVG_GOALS = 1.35     # buts par equipe et par match
HOME_ADVANTAGE = 1.25       # multiplicateur d'attaque a domicile
DC_RHO = -0.05              # correction Dixon-Coles sur les petits scores


def _poisson(lam: float, k: int) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    k = min(k, 20)
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _dc_tau(h: int, a: int, lh: float, la: float, rho: float = DC_RHO) -> float:
    """
    Correction Dixon-Coles.

    Le Poisson independant sous-estime systematiquement les scores nuls serres
    (0-0, 1-1) et donc la probabilite du match nul -- exactement la faiblesse
    qu'avait le modele precedent. Tau recalibre les quatre scores concernes.
    """
    if h == 0 and a == 0:
        return 1 - lh * la * rho
    if h == 0 and a == 1:
        return 1 + lh * rho
    if h == 1 and a == 0:
        return 1 + la * rho
    if h == 1 and a == 1:
        return 1 - rho
    return 1.0


def _score_matrix(home_xg: float, away_xg: float, max_goals: int = 8) -> dict:
    home_xg = max(0.15, home_xg)
    away_xg = max(0.15, away_xg)

    home_win = draw = away_win = 0.0
    best_score, best_p = "1-1", 0.0
    total_goals_probs = {}

    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson(home_xg, h) * _poisson(away_xg, a) * _dc_tau(h, a, home_xg, away_xg)
            p = max(p, 0.0)
            if p > best_p:
                best_p, best_score = p, f"{h}-{a}"
            if h > a:
                home_win += p
            elif h == a:
                draw += p
            else:
                away_win += p
            total_goals_probs[h + a] = total_goals_probs.get(h + a, 0.0) + p

    total = home_win + draw + away_win
    if total <= 0:
        return {"home_win": 0.33, "draw": 0.34, "away_win": 0.33,
                "predicted_score": "1-1", "goals_dist": {}}

    return {
        "home_win": home_win / total,
        "draw": draw / total,
        "away_win": away_win / total,
        "predicted_score": best_score,
        "goals_dist": {k: v / total for k, v in total_goals_probs.items()},
    }


def _btts_prob(home_xg: float, away_xg: float) -> float:
    return (1 - _poisson(home_xg, 0)) * (1 - _poisson(away_xg, 0))


def _over_prob(goals_dist: dict, line: float) -> float:
    return sum(p for total, p in goals_dist.items() if total > line)


# --- API publique de calcul de forme (reexport pour les routes) ---------------

def calculate_form(matches: list, team_id: int, venue: str = "all") -> dict:
    """Trie chronologiquement puis calcule la forme. Point d'entree des routes."""
    return compute_form(sort_matches(finished_only(matches)), team_id, venue)


def calculate_h2h_summary(h2h_matches: list, home_team_id: int, away_team_id: int,
                          reference_date=None) -> dict:
    return compute_h2h(h2h_matches, home_team_id, away_team_id, reference_date)


def calculate_rest(matches: list, team_id: int, match_date=None) -> float:
    team_matches = filter_team(sort_matches(finished_only(matches)), team_id, "all")
    return rest_days(team_matches, match_date)


# --- prediction --------------------------------------------------------------

def predict_match(
    home_form: dict,
    away_form: dict,
    home_form_home: dict,
    away_form_away: dict,
    h2h: Optional[dict] = None,
    home_position: Optional[int] = None,
    away_position: Optional[int] = None,
    league_size: int = 20,
    home_rest: float = 7.0,
    away_rest: float = 7.0,
) -> dict:
    """
    Prediction complete.

    xG multiplicatifs (force d'attaque x faiblesse defensive adverse x moyenne
    de ligue), au lieu de la moyenne additive precedente qui ecrasait les ecarts
    entre grosses et petites equipes.
    """
    h2h = h2h or {}

    def strength(value: float) -> float:
        return max(0.25, min(value / LEAGUE_AVG_GOALS, 2.5))

    # melange forme globale (40%) et forme specifique domicile/exterieur (60%)
    h_att = strength(home_form["xg_attack"] * 0.4 + home_form_home["xg_attack"] * 0.6)
    h_def = strength(home_form["xg_defense"] * 0.4 + home_form_home["xg_defense"] * 0.6)
    a_att = strength(away_form["xg_attack"] * 0.4 + away_form_away["xg_attack"] * 0.6)
    a_def = strength(away_form["xg_defense"] * 0.4 + away_form_away["xg_defense"] * 0.6)

    home_xg = h_att * a_def * LEAGUE_AVG_GOALS * HOME_ADVANTAGE
    away_xg = a_att * h_def * LEAGUE_AVG_GOALS

    # classement : desormais reellement transmis par les routes
    if home_position and away_position and league_size > 0:
        gap = (away_position - home_position) / league_size   # -1 .. +1
        home_xg *= 1 + gap * 0.12
        away_xg *= 1 - gap * 0.12

    # H2H pondere par anciennete
    if h2h.get("total", 0) >= 3:
        home_xg *= 1 + (h2h.get("w_home_rate", 0.45) - 0.45) * 0.15
        away_xg *= 1 + (h2h.get("w_away_rate", 0.30) - 0.30) * 0.15

    # fatigue : moins de 4 jours de repos penalise
    if home_rest < 4:
        home_xg *= 0.95
    if away_rest < 4:
        away_xg *= 0.95

    home_xg = max(0.25, min(home_xg, 4.5))
    away_xg = max(0.25, min(away_xg, 4.5))

    probs = _score_matrix(home_xg, away_xg)
    method = "Poisson Dixon-Coles"

    xgb = _load_xgb()
    if xgb is not None:
        try:
            features = np.array([build_features(
                home_form, away_form, home_form_home, away_form_away,
                h2h, home_rest, away_rest,
            )], dtype=float)
            if features.shape[1] != N_FEATURES:
                raise ValueError(f"shape {features.shape} incompatible")

            xgb_proba = xgb.predict_proba(features)[0]   # [domicile, nul, exterieur]
            wp = _ensemble_weights.get("poisson", 0.55)
            wx = _ensemble_weights.get("xgb", 0.45)

            blended = [
                probs["home_win"] * wp + float(xgb_proba[0]) * wx,
                probs["draw"] * wp + float(xgb_proba[1]) * wx,
                probs["away_win"] * wp + float(xgb_proba[2]) * wx,
            ]
            s = sum(blended)
            probs["home_win"], probs["draw"], probs["away_win"] = [b / s for b in blended]
            method = "Ensemble XGBoost+Poisson"
        except Exception as e:
            # on n'avale plus l'erreur en silence : elle remonte dans la reponse
            method = f"Poisson seul (XGBoost indisponible : {e})"

    btts = _btts_prob(home_xg, away_xg)
    dist = probs["goals_dist"]

    return {
        "home_win": round(probs["home_win"], 3),
        "draw": round(probs["draw"], 3),
        "away_win": round(probs["away_win"], 3),
        "predicted_score": probs["predicted_score"],
        "confidence": round(max(probs["home_win"], probs["draw"], probs["away_win"]) * 100, 1),
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "btts": round(btts, 3),
        "over_1_5": round(_over_prob(dist, 1.5), 3),
        "over_2_5": round(_over_prob(dist, 2.5), 3),
        "over_3_5": round(_over_prob(dist, 3.5), 3),
        "method": method,
        "model_loaded": MODEL_STATUS["loaded"],
    }


def blend_with_odds(prediction: dict, odds: dict) -> dict:
    """
    Fusion avec les probabilites implicites des bookmakers (35% modele / 65% marche).

    Ajoute la detection de value bet : ecart entre notre probabilite avant fusion
    et celle du marche. C'est la seule information reellement exploitable pour
    parier -- suivre le marche ne bat jamais le marche.
    """
    W_MODEL, W_ODDS = 0.35, 0.65
    model_probs = {
        "home_win": prediction["home_win"],
        "draw": prediction["draw"],
        "away_win": prediction["away_win"],
    }

    blended = {k: model_probs[k] * W_MODEL + odds[k] * W_ODDS for k in model_probs}
    total = sum(blended.values())

    for k in model_probs:
        prediction[k] = round(blended[k] / total, 3)

    prediction["confidence"] = round(
        max(prediction["home_win"], prediction["draw"], prediction["away_win"]) * 100, 1
    )
    prediction["method"] = "Ensemble+Bookmakers"
    prediction["odds"] = odds.get("avg_odds")

    value = {}
    for k, odds_key in (("home_win", "home"), ("draw", "draw"), ("away_win", "away")):
        book_odd = (odds.get("avg_odds") or {}).get(odds_key)
        if book_odd:
            edge = model_probs[k] - odds[k]
            value[k] = {
                "model_prob": round(model_probs[k], 3),
                "market_prob": round(odds[k], 3),
                "edge": round(edge, 3),
                "expected_value": round(model_probs[k] * book_odd - 1, 3),
                "value_bet": bool(edge > 0.05 and model_probs[k] * book_odd > 1.05),
            }
    prediction["value_analysis"] = value
    return prediction
