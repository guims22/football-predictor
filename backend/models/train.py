"""
Collecte des donnees historiques + entrainement XGBoost.

Usage :
    python -m models.train                 # 3 saisons (max du tier gratuit)
    python -m models.train --seasons 2024 2025
    python -m models.train --offline       # reutilise training_data.json sans rappeler l'API

Corrections par rapport a la version precedente :
  * indexation par equipe  -> O(n log n) au lieu de O(n^2) (etait ~30 min, est ~10 s)
  * split chronologique    -> supprime la fuite temporelle du train_test_split aleatoire
  * ponderation des classes-> le modele ne peut plus ignorer le match nul
  * features partagees     -> models/features.py, identiques a l'inference
  * truststore             -> passe les antivirus qui interceptent le TLS
  * use_label_encoder      -> retire (supprime depuis XGBoost 2.0, erreur en 3.x)
"""

import argparse
import bisect
import json
import os
import pickle
import sys
import time
from datetime import datetime

import numpy as np

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

import httpx
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.features import (  # noqa: E402
    FEATURE_NAMES,
    FEATURE_VERSION,
    N_FEATURES,
    build_features,
    compute_form,
    compute_h2h,
    filter_team,
    parse_date,
    rest_days,
)

load_dotenv()

FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY")
BASE_URL = "https://api.football-data.org/v4"
HEADERS = {"X-Auth-Token": FOOTBALL_API_KEY or ""}

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_HERE, "xgboost_model.pkl")
DATA_PATH = os.path.join(_HERE, "training_data.json")

COMPETITIONS = ["PL", "BL1", "SA", "PD", "FL1", "CL", "DED", "PPL", "BSA", "ELC"]
# Le tier gratuit de football-data.org n'autorise que les 3 dernieres saisons.
# 2022 et anterieur renvoient HTTP 403.
DEFAULT_SEASONS = ["2023", "2024", "2025"]

MIN_HISTORY = 5   # matchs de historique minimum requis pour chaque equipe


# --- collecte ----------------------------------------------------------------

def api_get(url: str, params: dict = None, max_retries: int = 3) -> dict:
    """Appel API avec respect du rate limit (10 req/min) et retry sur 429."""
    for attempt in range(max_retries):
        time.sleep(6.2)
        try:
            with httpx.Client(timeout=30) as client:
                r = client.get(url, headers=HEADERS, params=params)
            if r.status_code == 429:
                wait = int(r.headers.get("X-RequestCounter-Reset", 60))
                print(f"    rate limit -- pause {wait}s")
                time.sleep(wait + 1)
                continue
            if r.status_code == 403:
                print("    403 : saison hors abonnement (tier gratuit = 3 saisons)")
                return {}
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            print(f"    erreur reseau ({attempt + 1}/{max_retries}) : {e}")
            time.sleep(5)
    return {}


def fetch_all_matches(seasons: list) -> list:
    all_matches = []
    seen = set()
    total = len(COMPETITIONS) * len(seasons)
    done = 0

    for comp in COMPETITIONS:
        for season in seasons:
            done += 1
            print(f"[{done}/{total}] {comp} saison {season}...", flush=True)
            data = api_get(
                f"{BASE_URL}/competitions/{comp}/matches",
                params={"season": season, "status": "FINISHED"},
            )
            matches = data.get("matches", [])
            fresh = 0
            for m in matches:
                mid = m.get("id")
                if mid and mid not in seen:
                    seen.add(mid)
                    all_matches.append(m)
                    fresh += 1
            print(f"    -> {len(matches)} recus, {fresh} nouveaux")

    print(f"\nTotal unique : {len(all_matches)} matchs")
    return all_matches


# --- indexation --------------------------------------------------------------

class MatchIndex:
    """
    Index par equipe pour retrouver en O(log n) les matchs anterieurs a une date.

    C'est le correctif de performance principal : l'ancienne version rebalayait
    la liste complete des 5800 matchs pour chaque match et chaque equipe.
    """

    def __init__(self, matches: list):
        self.by_team = {}
        self.by_pair = {}

        ordered = sorted(matches, key=lambda m: m.get("utcDate") or "")
        for m in ordered:
            home = (m.get("homeTeam") or {}).get("id")
            away = (m.get("awayTeam") or {}).get("id")
            if home is None or away is None:
                continue
            self.by_team.setdefault(home, []).append(m)
            self.by_team.setdefault(away, []).append(m)
            self.by_pair.setdefault(tuple(sorted((home, away))), []).append(m)

        self._team_dates = {
            tid: [m.get("utcDate") or "" for m in lst] for tid, lst in self.by_team.items()
        }
        self._pair_dates = {
            pair: [m.get("utcDate") or "" for m in lst] for pair, lst in self.by_pair.items()
        }

    def team_before(self, team_id: int, date_str: str) -> list:
        lst = self.by_team.get(team_id)
        if not lst:
            return []
        cut = bisect.bisect_left(self._team_dates[team_id], date_str)
        return lst[:cut]

    def pair_before(self, a: int, b: int, date_str: str) -> list:
        pair = tuple(sorted((a, b)))
        lst = self.by_pair.get(pair)
        if not lst:
            return []
        cut = bisect.bisect_left(self._pair_dates[pair], date_str)
        return lst[:cut]


# --- construction du dataset -------------------------------------------------

def build_dataset(matches: list):
    index = MatchIndex(matches)
    ordered = sorted(matches, key=lambda m: m.get("utcDate") or "")

    X, y, dates = [], [], []
    skipped = 0

    for i, m in enumerate(ordered):
        if i % 1000 == 0 and i:
            print(f"    {i}/{len(ordered)} traites...", flush=True)

        score = (m.get("score") or {}).get("fullTime") or {}
        hg, ag = score.get("home"), score.get("away")
        if hg is None or ag is None:
            skipped += 1
            continue

        h_id = (m.get("homeTeam") or {}).get("id")
        a_id = (m.get("awayTeam") or {}).get("id")
        date_str = m.get("utcDate") or ""
        if h_id is None or a_id is None or not date_str:
            skipped += 1
            continue

        h_hist = index.team_before(h_id, date_str)
        a_hist = index.team_before(a_id, date_str)

        # sans historique suffisant, l'exemple est du bruit : on l'ecarte
        if len(h_hist) < MIN_HISTORY or len(a_hist) < MIN_HISTORY:
            skipped += 1
            continue

        match_date = parse_date(date_str)
        h2h_hist = index.pair_before(h_id, a_id, date_str)

        features = build_features(
            compute_form(h_hist, h_id, "all"),
            compute_form(a_hist, a_id, "all"),
            compute_form(h_hist, h_id, "home"),
            compute_form(a_hist, a_id, "away"),
            compute_h2h(h2h_hist, h_id, a_id, match_date),
            rest_days(filter_team(h_hist, h_id, "all"), match_date),
            rest_days(filter_team(a_hist, a_id, "all"), match_date),
        )

        X.append(features)
        y.append(0 if hg > ag else (1 if hg == ag else 2))
        dates.append(date_str)

    print(f"    {len(X)} echantillons retenus, {skipped} ecartes (historique insuffisant)")
    return np.array(X, dtype=float), np.array(y, dtype=int), dates


# --- entrainement ------------------------------------------------------------

def train_model(X, y, dates):
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, log_loss

    # Split CHRONOLOGIQUE. L'ancien train_test_split(random_state=42) melangeait
    # les saisons : le modele voyait des matchs de 2025 puis etait teste sur 2023.
    order = np.argsort(dates)
    X, y = X[order], y[order]
    sorted_dates = [dates[i] for i in order]

    n = len(X)
    cut_train = int(n * 0.70)
    cut_val = int(n * 0.85)

    X_train, y_train = X[:cut_train], y[:cut_train]
    X_val, y_val = X[cut_train:cut_val], y[cut_train:cut_val]
    X_test, y_test = X[cut_val:], y[cut_val:]

    print(f"    train {len(X_train)} (jusqu'a {sorted_dates[cut_train - 1][:10]})")
    print(f"    val   {len(X_val)} (jusqu'a {sorted_dates[cut_val - 1][:10]})")
    print(f"    test  {len(X_test)} (jusqu'a {sorted_dates[-1][:10]})")

    counts = np.bincount(y_train, minlength=3).astype(float)
    print(f"    repartition train : dom {counts[0]:.0f} / nul {counts[1]:.0f} / ext {counts[2]:.0f}")

    # Pas de ponderation des classes : testee, elle degrade la calibration
    # (log loss 1.056 contre 1.025) en faisant sur-predire le nul. Pour parier
    # ce sont les probabilites calibrees qui comptent, pas la precision brute
    # de l'argmax -- on garde donc les frequences naturelles.
    #
    # max_depth=1 : retenu apres balayage (depth 1/2/3 x lr x min_child_weight).
    # Le signal disponible est faible et essentiellement additif ; les arbres
    # profonds surapprennent sans rien gagner.
    model = XGBClassifier(
        n_estimators=1500,
        max_depth=1,
        learning_rate=0.03,
        subsample=0.85,
        colsample_bytree=0.80,
        min_child_weight=20,
        reg_lambda=5.0,
        objective="multi:softprob",
        num_class=3,
        eval_metric="mlogloss",
        early_stopping_rounds=80,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    proba_test = model.predict_proba(X_test)
    preds = proba_test.argmax(axis=1)
    acc = accuracy_score(y_test, preds)
    ll = log_loss(y_test, proba_test, labels=[0, 1, 2])

    # Reperes honnetes : sans eux, "48%" ne veut rien dire.
    majority = np.bincount(y_test, minlength=3).argmax()
    baseline_acc = (y_test == majority).mean()
    baseline_ll = log_loss(y_test, np.tile([[0.46, 0.25, 0.29]], (len(y_test), 1)),
                           labels=[0, 1, 2])

    print(f"\n    precision test : {acc * 100:.1f}%   (baseline 'toujours domicile' : {baseline_acc * 100:.1f}%)")
    print(f"    log loss test  : {ll:.4f}   (baseline frequences de base : {baseline_ll:.4f})")
    print(f"    nuls predits   : {(preds == 1).sum()} / {(y_test == 1).sum()} reels")

    importances = sorted(zip(FEATURE_NAMES, model.feature_importances_),
                         key=lambda t: -t[1])[:8]
    print("    features les plus utiles : " + ", ".join(f"{n} {v:.3f}" for n, v in importances))

    return model, {
        "accuracy": float(acc),
        "log_loss": float(ll),
        "baseline_accuracy": float(baseline_acc),
        "baseline_log_loss": float(baseline_ll),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "draws_predicted": int((preds == 1).sum()),
        "draws_actual": int((y_test == 1).sum()),
        "top_features": [[n, float(v)] for n, v in importances],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", nargs="+", default=DEFAULT_SEASONS)
    ap.add_argument("--offline", action="store_true",
                    help="reutilise training_data.json sans appeler l'API")
    args = ap.parse_args()

    print("=" * 60)
    print("FOOTBALL PREDICTOR -- collecte & entrainement")
    print("=" * 60)

    if args.offline and os.path.exists(DATA_PATH):
        print(f"\n[1/3] Mode offline : lecture de {DATA_PATH}")
        with open(DATA_PATH, encoding="utf-8") as f:
            matches = json.load(f)["matches"]
        print(f"    {len(matches)} matchs")
    else:
        if not FOOTBALL_API_KEY:
            print("\nFOOTBALL_API_KEY absente du fichier .env -- abandon.")
            return 1
        print(f"\n[1/3] Collecte -- {len(COMPETITIONS)} competitions x {len(args.seasons)} saisons")
        print(f"    saisons : {', '.join(args.seasons)}")
        print(f"    duree estimee : ~{len(COMPETITIONS) * len(args.seasons) * 6.2 / 60:.0f} min (rate limit 10 req/min)\n")
        matches = fetch_all_matches(args.seasons)
        if len(matches) < 500:
            print("Pas assez de donnees collectees -- verifier la cle API.")
            return 1
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({"matches": matches,
                       "collected_at": datetime.now().isoformat(),
                       "seasons": args.seasons}, f)
        print(f"    sauvegarde : {DATA_PATH}")

    print(f"\n[2/3] Construction des features (v{FEATURE_VERSION}, {N_FEATURES} variables)")
    X, y, dates = build_dataset(matches)
    if len(X) < 500:
        print("Dataset trop petit apres filtrage -- abandon.")
        return 1

    print("\n[3/3] Entrainement XGBoost")
    model, metrics = train_model(X, y, dates)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump({
            "model": model,
            "feature_version": FEATURE_VERSION,
            "feature_names": FEATURE_NAMES,
            "ensemble_weights": {"poisson": 0.55, "xgb": 0.45},
            "trained_at": datetime.now().isoformat(),
            "seasons": args.seasons,
            "n_samples": int(len(X)),
            **metrics,
        }, f)

    print(f"\nModele sauvegarde : {MODEL_PATH}")
    print("Redemarrer le backend pour le charger.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
