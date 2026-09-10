from fastapi import APIRouter, HTTPException, Path

from services.football_api import FootballAPIError, get_competitions, get_competition_standings

router = APIRouter()


@router.get("/")
async def list_competitions():
    try:
        data = await get_competitions()
    except FootballAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    result = [
        {
            "id": c["id"],
            "code": c.get("code", ""),
            "name": c["name"],
            "area": (c.get("area") or {}).get("name", ""),
            "emblem": c.get("emblem", ""),
            "type": c.get("type", ""),
        }
        for c in data.get("competitions", [])
    ]
    return {"competitions": result, "count": len(result)}


@router.get("/{code}/standings")
async def competition_standings(code: str = Path(...)):
    try:
        return await get_competition_standings(code.upper())
    except FootballAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
