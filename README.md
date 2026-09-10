# Football Predictor

Prédiction de matchs de football : modèle statistique (Poisson Dixon-Coles) + apprentissage
automatique (XGBoost) + cotes bookmakers, avec une analyse rédigée en français par Claude.

Backend **FastAPI** (Python) · Application mobile **Expo / React Native**.

---

## Démarrage rapide

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Renseigne tes trois clés dans `backend/.env`, puis :

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Vérifie que tout est en ordre — cet endpoint dit franchement ce qui manque :

```bash
curl http://localhost:8000/health
```

`status: "ok"` signifie : les 3 clés sont présentes **et** le modèle ML est chargé.
`status: "degraded"` liste précisément ce qui manque dans `degraded`.

### Mobile

```bash
cd mobile
npm install
npx expo start
```

L'URL du backend est résolue automatiquement depuis l'IP du poste qui sert le bundle Expo.
Pour la forcer, crée `mobile/.env` :

```
EXPO_PUBLIC_API_URL=http://192.168.1.42:8000
```

---

## Entraîner le modèle

```bash
cd backend
python -m models.train                      # 3 saisons (maximum du tier gratuit)
python -m models.train --seasons 2024 2025  # sous-ensemble
python -m models.train --offline            # réutilise training_data.json, sans appel API
```

La collecte prend environ 4 minutes (limite de 10 requêtes/minute côté football-data.org).

> **Le tier gratuit ne donne accès qu'aux 3 dernières saisons.** Toute saison antérieure
> renvoie un HTTP 403. Un entraînement sur 5 ans nécessite un abonnement payant.

### Performance actuelle

Mesurée sur un **découpage chronologique** (entraînement sur le passé, test sur l'avenir),
seul protocole honnête pour une série temporelle :

| Indicateur | Modèle | Référence | Écart |
|---|---|---|---|
| Log loss | **1.0357** | 1.0755 | **−3.7 %** |
| Précision | **47.5 %** | 43.3 % | **+4.2 pts** |

9 676 matchs, 26 variables, 10 compétitions, saisons 2023 à 2025.

Le **log loss** est la métrique qui compte : parier demande des probabilités bien calibrées,
pas un maximum de bonnes réponses. Un modèle qui annonce 60 % doit gagner 60 % du temps.

---

## Architecture

```
backend/
  main.py                 API + /health
  models/
    features.py           construction des variables (partagée train/inférence)
    predictor.py          Poisson Dixon-Coles, ensemble, fusion des cotes
    train.py              collecte et entraînement
  routes/                 matches, predictions, leagues, analysis
  services/
    football_api.py       football-data.org (limiteur de débit, cache borné)
    odds_service.py       The Odds API (1 requête par ligue, mise en cache)
    claude_service.py     analyse rédigée (Claude Sonnet 5, asynchrone)
mobile/
  app/(tabs)/             accueil, prédictions, ligues, analyse
  services/api.ts         client HTTP typé
```

### Comment se construit une prédiction

1. **Poisson Dixon-Coles** — buts attendus calculés de façon multiplicative
   (force offensive × faiblesse défensive adverse × moyenne de la ligue × avantage du terrain),
   corrigés sur les petits scores. Le Poisson simple sous-estime les 0-0 et 1-1, donc les nuls.
2. **XGBoost** — 26 variables : forme pondérée par récence, forme séparée domicile/extérieur,
   confrontations directes pondérées par ancienneté, jours de repos. Fusion 55 / 45.
3. **Cotes bookmakers** — probabilités implicites, marge retirée. Fusion finale 35 / 65 :
   le marché reste le meilleur prédicteur disponible.
4. **Analyse de value** — écart entre notre probabilité *avant* fusion et celle du marché.
   C'est la seule information exploitable pour parier : suivre le marché ne bat pas le marché.

---

## Déploiement (Railway)

`Procfile` et `railway.toml` sont prêts. Variables à définir : `CLAUDE_API_KEY`,
`FOOTBALL_API_KEY`, `ODDS_API_KEY`, et `ALLOWED_ORIGINS` (origines autorisées, séparées
par des virgules).

`backend/models/xgboost_model.pkl` est versionné volontairement : sans lui, l'API démarre
quand même mais retombe en Poisson seul, sans le signaler.

---

## Quotas des API

| Service | Limite gratuite | Protection en place |
|---|---|---|
| football-data.org | 10 req/min, 3 saisons | limiteur à fenêtre glissante + cache |
| The Odds API | 500 req/mois | 1 requête par ligue, cache 10 min |
| Claude | à l'usage | effort `low`, appelé uniquement à la demande |

---

## Antivirus qui intercepte le TLS (AVG, Avast, Kaspersky)

Ces logiciels remplacent les certificats HTTPS par les leurs. Python les refuse, alors que
les navigateurs les acceptent. Symptôme : `CERTIFICATE_VERIFY_FAILED` alors que le site
s'ouvre normalement dans Chrome.

Le code appelle `truststore` au démarrage, ce qui fait lire à Python le magasin de
certificats de Windows et règle le problème pour l'application.

Pour `pip`, exporte les certificats une fois :

```powershell
$sb = New-Object System.Text.StringBuilder
Get-ChildItem Cert:\LocalMachine\Root | ForEach-Object {
  [void]$sb.AppendLine("-----BEGIN CERTIFICATE-----")
  [void]$sb.AppendLine([Convert]::ToBase64String($_.RawData,'InsertLineBreaks'))
  [void]$sb.AppendLine("-----END CERTIFICATE-----")
}
Set-Content backend\corp-ca-bundle.pem $sb.ToString() -Encoding ascii
```

```bash
pip install --cert ./corp-ca-bundle.pem --timeout 300 -r requirements.txt
```

---

## Avertissement

Ce projet est un outil d'analyse statistique, pas un conseil de pari. Le modèle bat de peu
les fréquences de base, et les cotes des bookmakers restent plus performantes que lui pris
isolément. Aucun modèle de ce type ne garantit un gain.
