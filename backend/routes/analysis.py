from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import anthropic
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()
client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

SYSTEM = """Tu es un expert analyste football. Tu connais toutes les ligues mondiales,
les équipes, les joueurs et les statistiques. Tu fournis des analyses précises,
équilibrées et basées sur les faits. Tu réponds toujours en français de manière concise."""


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: List[ChatMessage] = []


@router.post("/chat")
async def chat(body: ChatRequest):
    try:
        messages = [{"role": m.role, "content": m.content} for m in body.history]
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": body.question})

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=SYSTEM,
            messages=messages,
        )
        return {"response": response.content[0].text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
