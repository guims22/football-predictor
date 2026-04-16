from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import matches, predictions, leagues, analysis

app = FastAPI(
    title="Football Predictor API",
    description="API de prédiction football alimentée par IA (Claude + ML)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(matches.router, prefix="/matches", tags=["Matchs"])
app.include_router(predictions.router, prefix="/predictions", tags=["Prédictions"])
app.include_router(leagues.router, prefix="/leagues", tags=["Ligues"])
app.include_router(analysis.router, prefix="/analysis", tags=["Analyse IA"])


@app.get("/")
def root():
    return {
        "message": "Football Predictor API",
        "version": "1.0.0",
        "endpoints": {
            "matchs_aujourd_hui": "/matches/today",
            "matchs_a_venir": "/matches/upcoming",
            "prediction_rapide": "/predictions/quick",
            "analyse_complete": "/predictions/full",
            "ligues": "/leagues",
            "docs": "/docs",
        },
    }
