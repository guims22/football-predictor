"""
Analyse rédigée par Claude.

Corrections :
  * AsyncAnthropic : les appels étaient synchrones dans des routes `async def`,
    donc chaque analyse bloquait l'event loop entier de FastAPI. Une seule
    prédiction en cours gelait toutes les autres requêtes.
  * claude-sonnet-5 remplace claude-sonnet-4-6 (génération courante, $2/$10
    par million de tokens au lieu de $3/$15).
  * max_tokens relevé : la réflexion adaptative est active par défaut sur
    Sonnet 5 et compte dans le budget, donc 900 tokens tronquaient l'analyse
    en plein milieu.
  * Erreurs typées au lieu d'un 500 opaque.
  * Le client n'est plus créé à l'import : une clé absente faisait planter
    le démarrage du serveur au lieu de dégrader proprement.
"""

import os
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5"
_client: Optional[anthropic.AsyncAnthropic] = None

SYSTEM_PROMPT = """Tu es un analyste football professionnel. Tu raisonnes à partir \
des chiffres qu'on te donne et tu ne les contredis jamais. Tu ne prétends pas \
connaître les compositions, blessures ou actualités récentes : tu n'as que les \
statistiques fournies. Tu réponds en français, de façon claire et structurée.

Tu rappelles la part d'incertitude quand la confiance du modèle est faible \
(moins de 45%), et tu ne présentes jamais un pronostic comme une certitude."""


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        key = os.getenv("CLAUDE_API_KEY")
        if not key:
            raise RuntimeError(
                "CLAUDE_API_KEY absente : renseigner backend/.env (voir .env.example)"
            )
        _client = anthropic.AsyncAnthropic(api_key=key)
    return _client


def is_configured() -> bool:
    return bool(os.getenv("CLAUDE_API_KEY"))


def _format_odds(prediction: dict) -> str:
    odds = prediction.get("odds")
    if not odds:
        return ""
    line = (f"\n=== COTES BOOKMAKERS ===\n"
            f"1 : {odds.get('home')} | X : {odds.get('draw')} | 2 : {odds.get('away')}")

    values = prediction.get("value_analysis") or {}
    flagged = [k for k, v in values.items() if v.get("value_bet")]
    if flagged:
        labels = {"home_win": "victoire domicile", "draw": "nul", "away_win": "victoire extérieur"}
        detail = ", ".join(
            f"{labels[k]} (espérance {values[k]['expected_value']:+.2f})" for k in flagged
        )
        line += f"\nÉcart favorable détecté sur : {detail}"
    else:
        line += "\nAucun écart favorable face au marché."
    return line


def _build_prompt(home_team, away_team, home_form, away_form, home_form_home,
                  away_form_away, prediction, competition, h2h,
                  home_position, away_position) -> str:
    position_text = ""
    if home_position and away_position:
        position_text = f"\nClassement : {home_team} #{home_position} | {away_team} #{away_position}"

    h2h_text = ""
    if h2h and h2h.get("total", 0) > 0:
        h2h_text = (
            f"\n=== CONFRONTATIONS DIRECTES ({h2h['total']} matchs) ===\n"
            f"{home_team} {h2h['home_wins']}V | Nuls {h2h['draws']} | {away_team} {h2h['away_wins']}V\n"
            f"Buts moyens : {home_team} {h2h['avg_goals_home']} | {away_team} {h2h['avg_goals_away']}"
        )

    return f"""Analyse ce match et donne un pronostic argumenté.

=== MATCH ===
{home_team} contre {away_team} | {competition}{position_text}

=== FORME GÉNÉRALE (8 derniers matchs, pondérée par récence) ===
{home_team} : {home_form['wins']}V {home_form['draws']}N {home_form['losses']}D | \
buts +{home_form['avg_goals_scored']} -{home_form['avg_goals_conceded']} | \
indice de forme {home_form['form_score'] * 100:.0f}/100
{away_team} : {away_form['wins']}V {away_form['draws']}N {away_form['losses']}D | \
buts +{away_form['avg_goals_scored']} -{away_form['avg_goals_conceded']} | \
indice de forme {away_form['form_score'] * 100:.0f}/100

=== FORME SELON LE LIEU ===
{home_team} à domicile : {home_form_home['wins']}V {home_form_home['draws']}N \
{home_form_home['losses']}D | {home_form_home['xg_attack']} buts marqués, \
{home_form_home['xg_defense']} encaissés par match | {home_form_home['clean_sheets']} clean sheets
{away_team} à l'extérieur : {away_form_away['wins']}V {away_form_away['draws']}N \
{away_form_away['losses']}D | {away_form_away['xg_attack']} buts marqués, \
{away_form_away['xg_defense']} encaissés par match | {away_form_away['clean_sheets']} clean sheets
{h2h_text}

=== MODÈLE STATISTIQUE ({prediction['method']}) ===
Buts attendus : {home_team} {prediction['home_xg']} | {away_team} {prediction['away_xg']}
1 (victoire {home_team}) : {prediction['home_win'] * 100:.1f}%
X (nul) : {prediction['draw'] * 100:.1f}%
2 (victoire {away_team}) : {prediction['away_win'] * 100:.1f}%
Score le plus probable : {prediction['predicted_score']}
Les deux équipes marquent : {prediction['btts'] * 100:.1f}%
Plus de 1.5 but : {prediction['over_1_5'] * 100:.1f}% | \
Plus de 2.5 buts : {prediction['over_2_5'] * 100:.1f}%
Confiance du modèle : {prediction['confidence']}%{_format_odds(prediction)}

Structure ta réponse en 4 parties :

**1. LECTURE DES ÉQUIPES** (2-3 phrases : forme, forces, faiblesses)

**2. FACTEURS CLÉS** (avantage du terrain, historique, dynamique)

**3. PRONOSTICS** (marque chaque pari d'un ✅ si solide ou d'un ⚠️ si incertain) :
• Résultat 1X2
• Score exact
• Les deux équipes marquent
• Total de buts (+/- 2.5)

**4. VERDICT** (le pari que tu retiens, en une phrase, avec son niveau de risque)

Maximum 300 mots."""


async def analyze_match(home_team: str, away_team: str, home_form: dict, away_form: dict,
                        home_form_home: dict, away_form_away: dict, prediction: dict,
                        competition: str, h2h: dict = None,
                        home_position: int = None, away_position: int = None) -> str:
    client = get_client()
    prompt = _build_prompt(home_team, away_team, home_form, away_form, home_form_home,
                           away_form_away, prediction, competition, h2h,
                           home_position, away_position)
    message = await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},   # rédaction guidée : la profondeur n'apporte rien
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in message.content if b.type == "text")


async def quick_tip(home_team: str, away_team: str, prediction: dict) -> str:
    client = get_client()

    outcomes = {
        f"victoire {home_team}": prediction["home_win"],
        "match nul": prediction["draw"],
        f"victoire {away_team}": prediction["away_win"],
    }
    best_bet, best_conf = max(outcomes.items(), key=lambda kv: kv[1])
    if prediction["btts"] > best_conf and prediction["btts"] > 0.60:
        best_bet, best_conf = "les deux équipes marquent", prediction["btts"]
    if prediction["over_2_5"] > best_conf and prediction["over_2_5"] > 0.65:
        best_bet, best_conf = "plus de 2.5 buts", prediction["over_2_5"]

    prompt = f"""{home_team} contre {away_team} :
- buts attendus : {home_team} {prediction['home_xg']} | {away_team} {prediction['away_xg']}
- 1X2 : {prediction['home_win'] * 100:.0f}% / {prediction['draw'] * 100:.0f}% / \
{prediction['away_win'] * 100:.0f}%
- les deux marquent {prediction['btts'] * 100:.0f}% | +2.5 buts {prediction['over_2_5'] * 100:.0f}%
- pari le mieux noté : {best_bet} ({best_conf * 100:.0f}%)

Donne le pari recommandé et sa raison principale. Deux phrases maximum."""

    message = await client.messages.create(
        model=MODEL,
        max_tokens=1000,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in message.content if b.type == "text")
