"""
Protection par cle partagee.

Une fois l'API deployee publiquement, n'importe qui connaissant l'URL peut
declencher des appels Claude, football-data et The Odds API -- tous factures
ou plafonnes sur les comptes du proprietaire. Cette protection minimale evite
qu'une URL devinee ou indexee vide les quotas.

Comportement :
  * API_ACCESS_KEY absente  -> aucune verification (developpement local inchange)
  * API_ACCESS_KEY definie  -> en-tete X-API-Key obligatoire sur les routes
                               couteuses ; / et /health restent ouverts pour
                               que Railway puisse sonder le service.
"""

import hmac
import os

from fastapi import Header, HTTPException, status


def _expected_key() -> str:
    return os.getenv("API_ACCESS_KEY", "").strip()


def auth_enabled() -> bool:
    return bool(_expected_key())


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Dependance FastAPI a appliquer aux routes qui consomment du quota."""
    expected = _expected_key()
    if not expected:
        return  # pas de cle configuree : mode developpement

    # comparaison a temps constant : evite de deduire la cle par mesure du delai
    if not hmac.compare_digest(x_api_key.strip(), expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cle d'acces manquante ou invalide (en-tete X-API-Key).",
        )
