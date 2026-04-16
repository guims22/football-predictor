import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

SYSTEM_PROMPT = """Tu es un expert analyste sportif spécialisé en football avec 20 ans d'expérience.
Tu analyses les données statistiques avec précision et fournis des pronostics basés sur les chiffres.
Tu connais toutes les ligues mondiales. Tu réponds toujours en français de manière claire et structurée."""


def analyze_match(
    home_team: str,
    away_team: str,
    home_form: dict,
    away_form: dict,
    home_form_home: dict,
    away_form_away: dict,
    prediction: dict,
    competition: str,
    h2h: dict = None,
    home_position: int = None,
    away_position: int = None,
) -> str:

    position_text = ""
    if home_position and away_position:
        position_text = f"\nClassement: {home_team} #{home_position} | {away_team} #{away_position}"

    h2h_text = ""
    if h2h and h2h.get("total", 0) > 0:
        h2h_text = f"""
Confrontations directes ({h2h['total']} matchs):
• {home_team}: {h2h['home_wins']} victoires | Nuls: {h2h['draws']} | {away_team}: {h2h['away_wins']} victoires
• Buts moyens: {home_team} {h2h['avg_goals_home']} | {away_team} {h2h['avg_goals_away']}"""

    prompt = f"""Analyse ce match et donne un pronostic complet avec plusieurs types de paris.

═══ MATCH ═══
{home_team} vs {away_team} | {competition}{position_text}

═══ FORME GÉNÉRALE (8 derniers matchs, pondérée) ═══
{home_team}: {home_form['wins']}V {home_form['draws']}N {home_form['losses']}D | Buts: +{home_form['avg_goals_scored']} -{home_form['avg_goals_conceded']} | Score forme: {home_form['form_score']*100:.0f}/100
{away_team}: {away_form['wins']}V {away_form['draws']}N {away_form['losses']}D | Buts: +{away_form['avg_goals_scored']} -{away_form['avg_goals_conceded']} | Score forme: {away_form['form_score']*100:.0f}/100

═══ FORME DOMICILE/EXTÉRIEUR SPÉCIFIQUE ═══
{home_team} à domicile: {home_form_home['wins']}V {home_form_home['draws']}N {home_form_home['losses']}D | xG: {home_form_home['xg_attack']} pour, {home_form_home['xg_defense']} contre | CS: {home_form_home['clean_sheets']}
{away_team} à l'extérieur: {away_form_away['wins']}V {away_form_away['draws']}N {away_form_away['losses']}D | xG: {away_form_away['xg_attack']} pour, {away_form_away['xg_defense']} contre | CS: {away_form_away['clean_sheets']}
{h2h_text}
═══ MODÈLE STATISTIQUE (Poisson) ═══
xG estimés: {home_team} {prediction['home_xg']} | {away_team} {prediction['away_xg']}
1 (Victoire {home_team}): {prediction['home_win']*100:.1f}%
X (Nul): {prediction['draw']*100:.1f}%
2 (Victoire {away_team}): {prediction['away_win']*100:.1f}%
Score le plus probable: {prediction['predicted_score']}
Les deux équipes marquent: {prediction['btts']*100:.1f}%
Plus de 2.5 buts: {prediction['over_2_5']*100:.1f}%
Plus de 1.5 buts: {prediction['over_1_5']*100:.1f}%

Fournis une analyse structurée en 4 parties:

**1. ANALYSE DES ÉQUIPES** (2-3 phrases: forme, forces/faiblesses)

**2. FACTEURS CLÉS** (avantage domicile, H2H, tendances)

**3. PRONOSTICS** (présente chaque pari avec ✅ ou ⚠️ selon la confiance):
• Résultat 1X2
• Score exact
• Les deux équipes marquent (BTTS)
• Total buts (+/- 2.5)

**4. VERDICT FINAL** (ton meilleur pari du match en 1 phrase)

Sois précis et concis (max 300 mots)."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=900,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def quick_tip(home_team: str, away_team: str, prediction: dict) -> str:
    if prediction["home_win"] >= prediction["draw"] and prediction["home_win"] >= prediction["away_win"]:
        outcome = f"Victoire {home_team}"
        prob = prediction["home_win"]
    elif prediction["draw"] >= prediction["away_win"]:
        outcome = "Match nul"
        prob = prediction["draw"]
    else:
        outcome = f"Victoire {away_team}"
        prob = prediction["away_win"]

    best_bet = outcome
    best_conf = prob

    if prediction["btts"] > 0.60:
        if prediction["btts"] > best_conf:
            best_bet = "Les deux équipes marquent"
            best_conf = prediction["btts"]

    if prediction["over_2_5"] > 0.65:
        if prediction["over_2_5"] > best_conf:
            best_bet = "Plus de 2.5 buts"
            best_conf = prediction["over_2_5"]

    prompt = f"""Pour {home_team} vs {away_team}:
- xG: {home_team} {prediction['home_xg']} | {away_team} {prediction['away_xg']}
- Résultat: {home_team} {prediction['home_win']*100:.0f}% | Nul {prediction['draw']*100:.0f}% | {away_team} {prediction['away_win']*100:.0f}%
- BTTS: {prediction['btts']*100:.0f}% | +2.5 buts: {prediction['over_2_5']*100:.0f}%
- Meilleur pari suggéré: {best_bet} ({best_conf*100:.0f}%)

Donne un tip ultra-court (2 phrases max): pari recommandé + raison principale."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=120,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
