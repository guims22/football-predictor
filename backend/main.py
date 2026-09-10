"""
Football Predictor API.

Corrections :
  * CORS : allow_origins=["*"] combine a allow_credentials=True est refuse par
    les navigateurs (la spec l'interdit). Les origines sont desormais lisibles
    depuis ALLOWED_ORIGINS, avec credentials desactives.
  * /health : l'etat du modele ML, des cles API et du quota bookmakers etait
    invisible. Un modele non charge passait totalement inapercu.
  * gestionnaire d'erreurs API : plus de 500 opaque sur une erreur amont.
"""

import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models.predictor import MODEL_STATUS
from routes import analysis, leagues, matches, predictions
from security import auth_enabled, require_api_key
from services.football_api import FootballAPIError, cache_stats
from services.odds_service import quota_status

load_dotenv()

app = FastAPI(
    title="Football Predictor API",
    description="Prediction football : Poisson Dixon-Coles + XGBoost + cotes bookmakers, analyse par Claude.",
    version="2.0.0",
)

# En dev, Expo sert l'app depuis une IP locale variable : "*" reste pratique,
# mais sans allow_credentials, sinon la combinaison est invalide.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(FootballAPIError)
async def football_api_error_handler(request: Request, exc: FootballAPIError):
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


# Toutes ces routes consomment du quota (football-data, The Odds API, Claude) :
# elles exigent X-API-Key des que API_ACCESS_KEY est definie. "/" et "/health"
# restent ouverts pour la sonde de disponibilite de Railway.
_protected = [Depends(require_api_key)]

app.include_router(matches.router, prefix="/matches", tags=["Matchs"], dependencies=_protected)
app.include_router(predictions.router, prefix="/predictions", tags=["Predictions"], dependencies=_protected)
app.include_router(leagues.router, prefix="/leagues", tags=["Ligues"], dependencies=_protected)
app.include_router(analysis.router, prefix="/analysis", tags=["Analyse IA"], dependencies=_protected)


@app.get("/")
def root():
    return {
        "message": "Football Predictor API",
        "version": "2.0.0",
        "endpoints": {
            "sante": "/health",
            "matchs_aujourd_hui": "/matches/today",
            "matchs_a_venir": "/matches/upcoming",
            "prediction_rapide": "/predictions/quick",
            "analyse_complete": "/predictions/full",
            "ligues": "/leagues",
            "docs": "/docs",
        },
    }


@app.get("/health", tags=["Diagnostic"])
def health():
    """Etat reel du service : cles presentes, modele charge, quotas restants."""
    keys = {
        "claude": bool(os.getenv("CLAUDE_API_KEY")),
        "football_data": bool(os.getenv("FOOTBALL_API_KEY")),
        "odds": bool(os.getenv("ODDS_API_KEY")),
    }
    degraded = [name for name, present in keys.items() if not present]
    if not MODEL_STATUS["loaded"]:
        degraded.append("modele_ml")

    return {
        "status": "ok" if not degraded else "degraded",
        "degraded": degraded,
        "auth_required": auth_enabled(),
        "api_keys": keys,
        "model": MODEL_STATUS,
        "football_cache": cache_stats(),
        "odds_quota": quota_status(),
    }
