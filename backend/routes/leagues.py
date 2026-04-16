from fastapi import APIRouter, HTTPException, Path
from services.football_api import get_competitions, get_competition_standings

router = APIRouter()


@router.get("/")
async def list_competitions():
    try:
        data = await get_competitions()
        competitions = data.get("competitions", [])
        result = [
            {
                "id": c["id"],
                "code": c.get("code", ""),
                "name": c["name"],
                "area": c.get("area", {}).get("name", ""),
                "emblem": c.get("emblem", ""),
                "type": c.get("type", ""),
            }
            for c in competitions
        ]
        return {"competitions": result, "count": len(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{code}/standings")
async def competition_standings(code: str = Path(...)):
    try:
        data = await get_competition_standings(code.upper())
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
