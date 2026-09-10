"""
Chat libre avec l'analyste IA.

Corrections :
  * reutilise le client de claude_service au lieu d'en instancier un second
  * roles valides : l'API Anthropic renvoyait une 400 si le mobile envoyait
    autre chose que "user"/"assistant"
  * historique borne : rien n'empechait d'envoyer 10 000 messages
  * appel async
"""

from typing import List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import claude_service

router = APIRouter()

SYSTEM = """Tu es un analyste football. Tu connais les ligues, les equipes et les
statistiques du sport. Tu fournis des analyses precises, nuancees et factuelles.
Quand tu n'as pas l'information (composition du jour, blessure recente, resultat
en direct), tu le dis clairement plutot que d'inventer. Tu reponds en francais,
de maniere concise."""

MAX_HISTORY = 20


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)


@router.post("/chat")
async def chat(body: ChatRequest):
    if not claude_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="CLAUDE_API_KEY absente : renseigner backend/.env (voir .env.example)",
        )

    messages = [m.model_dump() for m in body.history[-MAX_HISTORY:]]
    if not messages or messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": body.question})

    try:
        client = claude_service.get_client()
        response = await client.messages.create(
            model=claude_service.MODEL,
            max_tokens=2000,
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=messages,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erreur Claude : {e}")

    return {"response": "".join(b.text for b in response.content if b.type == "text")}
