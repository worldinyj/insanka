from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.dependencies import get_current_user
from typing import List
from pydantic import BaseModel
from datetime import datetime

router = APIRouter(prefix="/notifications", tags=["notifications"])

import asyncio
from sse_starlette.sse import EventSourceResponse
from app.services.notification_service import subscribe_user, unsubscribe_user
from fastapi import Request

@router.get("/stream")
async def notification_stream(
    request: Request,
    user: User = Depends(get_current_user)
):
    queue = subscribe_user(user.id)
    
    async def event_generator():
        try:
            while True:
                # If client closes connection, stop
                if await request.is_disconnected():
                    break
                    
                # Wait for a new message
                message = await queue.get()
                yield {
                    "event": "message",
                    "data": message
                }
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe_user(user.id, queue)
            
    return EventSourceResponse(event_generator())

@router.get("")
async def get_notifications(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    query = select(Notification).where(
        Notification.user_id == user.id,
        Notification.is_read == False
    ).order_by(desc(Notification.created_at)).limit(20)
    
    result = await db.execute(query)
    notifications = result.scalars().all()
    
    return {
        "notifications": [
            {
                "id": n.id,
                "type": n.type,
                "message": n.message,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at
            }
            for n in notifications
        ]
    }

@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    notification = (await db.execute(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )).scalar_one_or_none()
    
    if not notification:
        raise HTTPException(404, "Notification not found")
        
    notification.is_read = True
    await db.commit()
    return {"status": "success"}

@router.patch("/read-all")
async def mark_all_as_read(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    await db.commit()
    return {"status": "success"}
