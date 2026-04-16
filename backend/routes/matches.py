from fastapi import APIRouter, HTTPException, Query
from services.football_api import get_today_matches, get_upcoming_matches, get_competition_matches

router = APIRouter()


@router.get("/today")
async def today_matches():
    try:
        data = await get_today_matches()
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/upcoming")
async def upcoming_matches(days: int = Query(default=7, ge=1, le=30)):
    try:
        data = await get_upcoming_matches(days)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competition/{code}")
async def competition_matches(
    code: str,
    days_back: int = Query(default=3, ge=0, le=30),
    days_ahead: int = Query(default=7, ge=0, le=30),
):
    try:
        data = await get_competition_matches(code.upper(), days_back, days_ahead)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
