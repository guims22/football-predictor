"""
Script d'entrainement XGBoost pour la prediction football.
Collecte les donnees historiques via football-data.org et entraine le modele.
Usage: python models/train.py
"""

import os
import time
import json
import pickle
import numpy as np
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY}
MODEL_PATH = "models/xgboost_model.pkl"
DATA_PATH = "models/training_data.json"

# Competitions disponibles sur le tier gratuit
COMPETITIONS = ["PL", "BL1", "SA", "PD", "FL1", "CL", "DED", "PPL", "BSA"]
SEASONS = ["2022", "2023", "2024"]


def api_get(url: str, params: dict = None) -> dict:
    """Appel API avec respect du rate limit (10 req/min)."""
    time.sleep(6.5)  # 10 req/min max
    try:
        with httpx.Client(timeout=20) as client:
            r = client.get(url, headers=HEADERS, params=params)
            if r.status_code == 429:
                print("  Rate limit atteint, pause 60s...")
                time.sleep(60)
                r = client.get(url, headers=HEADERS, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"  Erreur API: {e}")
        return {}


def fetch_all_matches() -> list:
    """Collecte tous les matchs termines pour toutes les competitions et saisons."""
    all_matches = []
    total = len(COMPETITIONS) * len(SEASONS)
    done = 0

    for comp in COMPETITIONS:
        for season in SEASONS:
            done += 1
            print(f"[{done}/{total}] {comp} saison {season}...")
            data = api_get(
                f"{BASE_URL}/competitions/{comp}/matches",
                params={"season": season, "status": "FINISHED"},
            )
            matches = data.get("matches", [])
            all_matches.extend(matches)
            print(f"  -> {len(matches)} matchs collectes")

    print(f"\nTotal: {len(all_matches)} matchs")
    return all_matches


def build_team_stats(matches: list) -> dict:
    """Construit les stats cumulatives par equipe a partir des matchs passes."""
    stats = {}

    def _get(team_id):
        if team_id not in stats:
            stats[team_id] = {
                "matches": [], "wins": 0, "draws": 0, "losses": 0,
                "goals_scored": 0, "goals_conceded": 0,
                "home_wins": 0, "home_draws": 0, "home_losses": 0,
                "away_wins": 0, "away_draws": 0, "away_losses": 0,
            }
        return stats[team_id]

    for m in matches:
        if m.get("status") != "FINISHED":
            continue
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home") or 0
        ag = score.get("away") or 0
        h_id = m["homeTeam"]["id"]
        a_id = m["awayTeam"]["id"]

        hs = _get(h_id)
        as_ = _get(a_id)

        hs["matches"].append(m)
        as_["matches"].append(m)
        hs["goals_scored"] += hg
        hs["goals_conceded"] += ag
        as_["goals_scored"] += ag
        as_["goals_conceded"] += hg

        if hg > ag:
            hs["wins"] += 1; hs["home_wins"] += 1
            as_["losses"] += 1; as_["away_losses"] += 1
        elif hg == ag:
            hs["draws"] += 1; hs["home_draws"] += 1
            as_["draws"] += 1; as_["away_draws"] += 1
        else:
            hs["losses"] += 1; hs["home_losses"] += 1
            as_["wins"] += 1; as_["away_wins"] += 1

    return stats


def form_features(team_id: int, all_matches: list, before_date: str, venue: str = "all", n: int = 8) -> dict:
    """Calcule les features de forme d'une equipe avant une date donnee."""
    finished = [
        m for m in all_matches
        if m.get("status") == "FINISHED" and m.get("utcDate", "") < before_date
        and (team_id in [m["homeTeam"]["id"], m["awayTeam"]["id"]])
    ]

    if venue == "home":
        finished = [m for m in finished if m["homeTeam"]["id"] == team_id]
    elif venue == "away":
        finished = [m for m in finished if m["awayTeam"]["id"] == team_id]

    recent = finished[-n:]
    wins = draws = losses = gs = gc = cs = 0
    weighted_pts = total_w = 0.0

    for i, m in enumerate(recent):
        w = 0.6 + (i / max(len(recent) - 1, 1)) * 0.4
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home") or 0
        ag = score.get("away") or 0
        is_home = m["homeTeam"]["id"] == team_id
        s, c = (hg, ag) if is_home else (ag, hg)
        gs += s; gc += c
        if c == 0: cs += 1
        if s > c: wins += 1; weighted_pts += 3 * w
        elif s == c: draws += 1; weighted_pts += w
        else: losses += 1
        total_w += 3 * w

    p = wins + draws + losses
    if p == 0:
        return {"form": 0.5, "avg_gs": 1.2, "avg_gc": 1.2, "cs_rate": 0.2}

    return {
        "form": round(weighted_pts / total_w, 3) if total_w > 0 else 0.5,
        "avg_gs": round(gs / p, 3),
        "avg_gc": round(gc / p, 3),
        "cs_rate": round(cs / p, 3),
    }


def extract_features(match: dict, all_matches: list) -> list | None:
    """Extrait les features pour un match donne."""
    if match.get("status") != "FINISHED":
        return None
    score = match.get("score", {}).get("fullTime", {})
    hg = score.get("home")
    ag = score.get("away")
    if hg is None or ag is None:
        return None

    h_id = match["homeTeam"]["id"]
    a_id = match["awayTeam"]["id"]
    date = match.get("utcDate", "")

    hf = form_features(h_id, all_matches, date, "all")
    af = form_features(a_id, all_matches, date, "all")
    hfh = form_features(h_id, all_matches, date, "home")
    afa = form_features(a_id, all_matches, date, "away")

    features = [
        hf["form"], hf["avg_gs"], hf["avg_gc"], hf["cs_rate"],
        af["form"], af["avg_gs"], af["avg_gc"], af["cs_rate"],
        hfh["form"], hfh["avg_gs"], hfh["avg_gc"],
        afa["form"], afa["avg_gs"], afa["avg_gc"],
        hf["form"] - af["form"],
        hf["avg_gs"] - af["avg_gc"],
        af["avg_gs"] - hf["avg_gc"],
    ]

    if hg > ag:
        label = 0  # Home win
    elif hg == ag:
        label = 1  # Draw
    else:
        label = 2  # Away win

    return features + [label]


def train_model(X: np.ndarray, y: np.ndarray):
    """Entraine un modele XGBoost."""
    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("Installation de xgboost...")
        os.system("pip install xgboost scikit-learn")
        from xgboost import XGBClassifier

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    model = XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="mlogloss",
        random_state=42,
    )

    print("Entrainement en cours...")
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print(f"Precision sur test: {acc*100:.1f}%")

    return model, acc


def main():
    print("=" * 50)
    print("FOOTBALL PREDICTOR — Collecte & Entrainement")
    print("=" * 50)

    # 1. Collecte
    print("\n[1/3] Collecte des donnees historiques...")
    print(f"Competitions: {', '.join(COMPETITIONS)}")
    print(f"Saisons: {', '.join(SEASONS)}")
    print("(pause 6.5s entre chaque requete pour respecter le rate limit)\n")

    matches = fetch_all_matches()

    if len(matches) < 100:
        print("Pas assez de donnees collectees. Verifiez votre cle API.")
        return

    # Sauvegarde des donnees brutes
    with open(DATA_PATH, "w") as f:
        json.dump({"matches": matches, "collected_at": datetime.now().isoformat()}, f)
    print(f"Donnees sauvegardees: {DATA_PATH}")

    # 2. Feature engineering
    print("\n[2/3] Construction des features ML...")
    rows = []
    for i, m in enumerate(matches):
        if i % 500 == 0:
            print(f"  {i}/{len(matches)} matchs traites...")
        row = extract_features(m, matches)
        if row:
            rows.append(row)

    print(f"  {len(rows)} echantillons construits")
    data = np.array(rows)
    X = data[:, :-1]
    y = data[:, -1].astype(int)

    # 3. Entrainement
    print("\n[3/3] Entrainement XGBoost...")
    model, accuracy = train_model(X, y)

    # Sauvegarde du modele
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "accuracy": accuracy, "trained_at": datetime.now().isoformat()}, f)

    print(f"\nModele sauvegarde: {MODEL_PATH}")
    print(f"Precision finale: {accuracy*100:.1f}%")
    print("\nEntraine avec succes! Redemarrez le backend pour utiliser le nouveau modele.")


if __name__ == "__main__":
    main()
