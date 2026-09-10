"""
Routes de prediction.

Corrections :
  * competition_code est enfin transmis a odds_service (il restait a "" a cause
    d'un appel positionnel, ce qui declenchait 12 requetes de quota par prediction)
  * le classement est reellement recupere et injecte dans le modele : les
    parametres home_position / away_position existaient depuis le debut mais
    aucune route ne les remplissait
  * les erreurs API remontent avec leur vrai code HTTP (429, 403, 503...)
    au lieu d'un 500 generique
"""

import asyncio

from fastapi import APIRouter, HTTPException, Query

from models.predictor import (
    blend_with_odds,
    calculate_form,
    calculate_h2h_summary,
    calculate_rest,
    predict_match,
)
from models.features import parse_date
from services import claude_service
from services.football_api import (
    FootballAPIError,
    extract_positions,
    get_competition_standings,
    get_head_to_head,
    get_team_matches,
)
from services.odds_service import get_odds_for_match

router = APIRouter()


async def _safe(coro, default=None):
    """Une source annexe qui echoue ne doit pas faire tomber la prediction."""
    try:
        return await coro
    except Exception:
        return default


async def _build_prediction(match_id: int, home_team_id: int, away_team_id: int,
                            home_team_name: str = "", away_team_name: str = "",
                            competition: str = "", competition_code: str = "",
                            match_date: str = ""):
    try:
        home_data, away_data = await asyncio.gather(
            get_team_matches(home_team_id, 40),
            get_team_matches(away_team_id, 40),
        )
    except FootballAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    # sources optionnelles : leur absence degrade la prediction sans la bloquer
    h2h_data, odds, standings = await asyncio.gather(
        _safe(get_head_to_head(match_id, 10), {}),
        _safe(get_odds_for_match(home_team_name, away_team_name, competition_code)),
        _safe(get_competition_standings(competition_code), {}) if competition_code else _safe(
            asyncio.sleep(0), {}
        ),
    )

    home_matches = (home_data or {}).get("matches", [])
    away_matches = (away_data or {}).get("matches", [])
    ref_date = parse_date(match_date)

    home_form = calculate_form(home_matches, home_team_id, "all")
    away_form = calculate_form(away_matches, away_team_id, "all")
    home_form_home = calculate_form(home_matches, home_team_id, "home")
    away_form_away = calculate_form(away_matches, away_team_id, "away")
    h2h_summary = calculate_h2h_summary(
        (h2h_data or {}).get("matches", []), home_team_id, away_team_id, ref_date
    )

    home_pos, away_pos, league_size = extract_positions(
        standings or {}, home_team_id, away_team_id
    )

    prediction = predict_match(
        home_form=home_form,
        away_form=away_form,
        home_form_home=home_form_home,
        away_form_away=away_form_away,
        h2h=h2h_summary,
        home_position=home_pos,
        away_position=away_pos,
        league_size=league_size,
        home_rest=calculate_rest(home_matches, home_team_id, ref_date),
        away_rest=calculate_rest(away_matches, away_team_id, ref_date),
    )

    if odds:
        prediction = blend_with_odds(prediction, odds)

    return {
        "home_form": home_form,
        "away_form": away_form,
        "home_form_home": home_form_home,
        "away_form_away": away_form_away,
        "h2h": h2h_summary,
        "prediction": prediction,
        "odds": odds,
        "home_position": home_pos,
        "away_position": away_pos,
    }


@router.get("/quick")
async def quick_prediction(
    match_id: int = Query(...),
    home_team_id: int = Query(...),
    away_team_id: int = Query(...),
    home_team_name: str = Query(...),
    away_team_name: str = Query(...),
    competition: str = Query(default=""),
    competition_code: str = Query(default="", description="Code ligue : PL, PD, SA, BL1, FL1..."),
    match_date: str = Query(default="", description="Date ISO du match"),
):
    ctx = await _build_prediction(match_id, home_team_id, away_team_id, home_team_name,
                                  away_team_name, competition, competition_code, match_date)

    tip = None
    if claude_service.is_configured():
        try:
            tip = await claude_service.quick_tip(home_team_name, away_team_name, ctx["prediction"])
        except Exception as e:
            tip = f"(analyse IA indisponible : {e})"

    return {
        "match_id": match_id,
        "home_team": home_team_name,
        "away_team": away_team_name,
        "competition": competition,
        "prediction": ctx["prediction"],
        "tip": tip,
        "odds_available": ctx["odds"] is not None,
    }


@router.get("/full")
async def full_prediction(
    match_id: int = Query(...),
    home_team_id: int = Query(...),
    away_team_id: int = Query(...),
    home_team_name: str = Query(...),
    away_team_name: str = Query(...),
    competition: str = Query(default=""),
    competition_code: str = Query(default="", description="Code ligue : PL, PD, SA, BL1, FL1..."),
    match_date: str = Query(default="", description="Date ISO du match"),
):
    ctx = await _build_prediction(match_id, home_team_id, away_team_id, home_team_name,
                                  away_team_name, competition, competition_code, match_date)

    analysis = None
    if claude_service.is_configured():
        try:
            analysis = await claude_service.analyze_match(
                home_team=home_team_name,
                away_team=away_team_name,
                home_form=ctx["home_form"],
                away_form=ctx["away_form"],
                home_form_home=ctx["home_form_home"],
                away_form_away=ctx["away_form_away"],
                prediction=ctx["prediction"],
                competition=competition,
                h2h=ctx["h2h"],
                home_position=ctx["home_position"],
                away_position=ctx["away_position"],
            )
        except Exception as e:
            analysis = f"(analyse IA indisponible : {e})"

    return {
        "match_id": match_id,
        "home_team": home_team_name,
        "away_team": away_team_name,
        "competition": competition,
        "home_form": ctx["home_form"],
        "away_form": ctx["away_form"],
        "home_form_home": ctx["home_form_home"],
        "away_form_away": ctx["away_form_away"],
        "h2h": ctx["h2h"],
        "standings": {"home_position": ctx["home_position"], "away_position": ctx["away_position"]},
        "prediction": ctx["prediction"],
        "analysis": analysis,
        "odds_available": ctx["odds"] is not None,
        "odds": ctx["odds"],
    }
