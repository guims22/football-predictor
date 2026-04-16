import asyncio
from fastapi import APIRouter, HTTPException, Query
from services.football_api import get_team_matches, get_head_to_head, get_competition_standings
from services.claude_service import analyze_match, quick_tip
from services.odds_service import get_odds_for_match
from models.predictor import (
    calculate_form,
    calculate_h2h_summary,
    predict_match,
    blend_with_odds,
)

router = APIRouter()


async def _build_prediction(
    match_id: int,
    home_team_id: int,
    away_team_id: int,
    home_team_name: str = "",
    away_team_name: str = "",
    competition: str = "",
    competition_code: str = "",
):
    """Fetch all data and compute prediction."""
    home_data, away_data, h2h_data, odds = await asyncio.gather(
        get_team_matches(home_team_id, 16),
        get_team_matches(away_team_id, 16),
        get_head_to_head(match_id, 10),
        get_odds_for_match(home_team_name, away_team_name, competition_code),
    )

    home_matches = home_data.get("matches", [])
    away_matches = away_data.get("matches", [])
    h2h_matches = h2h_data.get("matches", [])

    home_form      = calculate_form(home_matches, home_team_id, "all")
    away_form      = calculate_form(away_matches, away_team_id, "all")
    home_form_home = calculate_form(home_matches, home_team_id, "home")
    away_form_away = calculate_form(away_matches, away_team_id, "away")
    h2h_summary    = calculate_h2h_summary(h2h_matches, home_team_id, away_team_id)

    prediction = predict_match(
        home_form=home_form,
        away_form=away_form,
        home_form_home=home_form_home,
        away_form_away=away_form_away,
        h2h=h2h_summary,
    )

    # Blend with bookmaker odds if available
    if odds:
        prediction = blend_with_odds(prediction, odds)

    return home_form, away_form, home_form_home, away_form_away, h2h_summary, prediction, odds


@router.get("/quick")
async def quick_prediction(
    match_id: int = Query(...),
    home_team_id: int = Query(...),
    away_team_id: int = Query(...),
    home_team_name: str = Query(...),
    away_team_name: str = Query(...),
    competition: str = Query(default=""),
):
    try:
        _, _, _, _, _, prediction, odds = await _build_prediction(
            match_id, home_team_id, away_team_id,
            home_team_name, away_team_name, competition
        )
        tip = quick_tip(home_team_name, away_team_name, prediction)
        return {
            "match_id": match_id,
            "home_team": home_team_name,
            "away_team": away_team_name,
            "competition": competition,
            "prediction": prediction,
            "tip": tip,
            "odds_available": odds is not None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/full")
async def full_prediction(
    match_id: int = Query(...),
    home_team_id: int = Query(...),
    away_team_id: int = Query(...),
    home_team_name: str = Query(...),
    away_team_name: str = Query(...),
    competition: str = Query(default=""),
):
    try:
        home_form, away_form, home_form_home, away_form_away, h2h_summary, prediction, odds = (
            await _build_prediction(
                match_id, home_team_id, away_team_id,
                home_team_name, away_team_name, competition
            )
        )

        analysis = analyze_match(
            home_team=home_team_name,
            away_team=away_team_name,
            home_form=home_form,
            away_form=away_form,
            home_form_home=home_form_home,
            away_form_away=away_form_away,
            prediction=prediction,
            competition=competition,
            h2h=h2h_summary,
        )

        return {
            "match_id": match_id,
            "home_team": home_team_name,
            "away_team": away_team_name,
            "competition": competition,
            "home_form": home_form,
            "away_form": away_form,
            "home_form_home": home_form_home,
            "away_form_away": away_form_away,
            "h2h": h2h_summary,
            "prediction": prediction,
            "analysis": analysis,
            "odds_available": odds is not None,
            "odds": odds,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
