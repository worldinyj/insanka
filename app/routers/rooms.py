from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.room import Room

router = APIRouter(prefix="/rooms", tags=["rooms"])

@router.get("")
async def get_rooms(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Room).order_by(Room.id))
    rooms = result.scalars().all()
    return {
        "rooms": [{"id": r.id, "name": r.name, "slug": r.slug, "description": r.description} for r in rooms]
    }
