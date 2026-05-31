from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, date
import calendar

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.room import Room
from app.models.event import Event, EventAttendee

router = APIRouter(tags=["events"])

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    location: Optional[str] = None

@router.get("/rooms/{slug}/events")
async def get_room_events(
    slug: str,
    filter: Optional[str] = "month",
    db: AsyncSession = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    room = (await db.execute(select(Room).where(Room.slug == slug))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room not found")
        
    query = select(Event).where(Event.room_id == room.id)
    
    today = date.today()
    if filter == "today":
        start_date = datetime(today.year, today.month, today.day).astimezone()
        end_date = start_date + timedelta(days=1)
        query = query.where(Event.start_time >= start_date, Event.start_time < end_date)
    elif filter == "week":
        start_date = datetime(today.year, today.month, today.day) - timedelta(days=today.weekday())
        start_date = start_date.astimezone()
        end_date = start_date + timedelta(days=7)
        query = query.where(Event.start_time >= start_date, Event.start_time < end_date)
    elif filter == "month":
        start_date = datetime(today.year, today.month, 1).astimezone()
        _, last_day = calendar.monthrange(today.year, today.month)
        end_date = start_date + timedelta(days=last_day)
        query = query.where(Event.start_time >= start_date, Event.start_time < end_date)
        
    result = await db.execute(query.order_by(Event.start_time.asc()))
    events = result.scalars().all()
    
    events_data = []
    for evt in events:
        attendees = (await db.execute(select(EventAttendee).where(EventAttendee.event_id == evt.id))).scalars().all()
        user_ids = [a.user_id for a in attendees]
        events_data.append({
            "id": evt.id,
            "title": evt.title,
            "description": evt.description,
            "start_time": evt.start_time,
            "end_time": evt.end_time,
            "location": evt.location,
            "attendee_count": len(user_ids),
            "is_attending": user.id in user_ids
        })
        
    return {"events": events_data}

@router.post("/rooms/{slug}/events")
async def create_event(
    slug: str,
    event_in: EventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role not in ['admin', 'editor']:
        raise HTTPException(403, "관리자만 일정을 등록할 수 있습니다.")
        
    room = (await db.execute(select(Room).where(Room.slug == slug))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room not found")
        
    new_event = Event(
        room_id=room.id,
        creator_id=user.id,
        title=event_in.title,
        description=event_in.description,
        start_time=event_in.start_time,
        end_time=event_in.end_time,
        location=event_in.location
    )
    db.add(new_event)
    await db.commit()
    return {"message": "Event created", "id": new_event.id}

@router.delete("/rooms/{slug}/events/{event_id}")
async def delete_event(
    slug: str,
    event_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    if user.role not in ['admin', 'editor']:
        raise HTTPException(403, "관리자만 일정을 삭제할 수 있습니다.")
        
    evt = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not evt:
        raise HTTPException(404, "Event not found")
        
    await db.delete(evt)
    await db.commit()
    return {"message": "Event deleted"}

@router.post("/events/{event_id}/attend")
async def attend_event(event_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    evt = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
    if not evt:
        raise HTTPException(404, "Event not found")
        
    try:
        attendee = EventAttendee(event_id=event_id, user_id=user.id)
        db.add(attendee)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, "Already attending")
        
    return {"message": "참석 신청 완료"}

@router.delete("/events/{event_id}/attend")
async def cancel_attend_event(event_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    attendee = (await db.execute(select(EventAttendee).where(EventAttendee.event_id == event_id, EventAttendee.user_id == user.id))).scalar_one_or_none()
    if not attendee:
        raise HTTPException(404, "Not attending")
        
    await db.delete(attendee)
    await db.commit()
    return {"message": "참석 취소 완료"}
