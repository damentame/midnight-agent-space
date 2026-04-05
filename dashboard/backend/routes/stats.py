"""Dashboard aggregate stats."""
from fastapi import APIRouter, Depends

from ..database import DatabaseManager, get_db

router = APIRouter()


@router.get("/stats")
async def dashboard_stats(db: DatabaseManager = Depends(get_db)):
    return await db.dashboard_stats()
