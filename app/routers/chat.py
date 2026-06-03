from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal, get_db
from app.models.chat import ChatMessage
from app.models.user import User
from app.models.room import Room
from app.utils.security import decode_access_token
from app.utils.sanitize import sanitize_html
import json
from typing import Dict, List, Set
from datetime import datetime

router = APIRouter(prefix="/chat", tags=["chat"])

class ConnectionManager:
    def __init__(self):
        # Dictionary mapping room_id to a set of active WebSockets
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: int):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = set()
        self.active_connections[room_id].add(websocket)

    def disconnect(self, websocket: WebSocket, room_id: int):
        if room_id in self.active_connections:
            self.active_connections[room_id].discard(websocket)

    async def broadcast(self, message: dict, room_id: int):
        if room_id in self.active_connections:
            # We convert message to JSON once and send to all
            text_data = json.dumps(message, ensure_ascii=False)
            for connection in self.active_connections[room_id]:
                try:
                    await connection.send_text(text_data)
                except Exception:
                    pass

manager = ConnectionManager()

async def get_ws_user(websocket: WebSocket, db: AsyncSession) -> User:
    token = None
    cookie_token = websocket.cookies.get("access_token")
    if cookie_token and cookie_token.startswith("Bearer "):
        token = cookie_token.split(" ")[1]
        
    if not token:
        return None
        
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return None
        
    user_id = int(payload.get("sub"))
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    return user

@router.get("/{room_slug}/history")
async def get_chat_history(room_slug: str, db: AsyncSession = Depends(get_db)):
    room = (await db.execute(select(Room).where(Room.slug == room_slug))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room not found")
        
    # Get last 50 messages
    result = await db.execute(
        select(ChatMessage, User)
        .join(User, ChatMessage.user_id == User.id)
        .where(ChatMessage.room_id == room.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
    )
    
    rows = result.all()
    
    history = []
    for msg, user in reversed(rows): # Reverse to chronological order
        history.append({
            "id": msg.id,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "author": {
                "id": user.id,
                "username": user.username,
                "level": user.level,
                "role": user.role
            }
        })
        
    return {"history": history}

@router.websocket("/{room_slug}/ws")
async def websocket_endpoint(websocket: WebSocket, room_slug: str):
    async with AsyncSessionLocal() as db:
        room = (await db.execute(select(Room).where(Room.slug == room_slug))).scalar_one_or_none()
        if not room:
            await websocket.close(code=1008, reason="Room not found")
            return
            
        user = await get_ws_user(websocket, db)
        if not user:
            await websocket.close(code=1008, reason="Not authenticated")
            return

        await manager.connect(websocket, room.id)
        
        # Broadcast user joined
        join_msg = {
            "type": "system",
            "content": f"{user.username}님이 입장하셨습니다."
        }
        await manager.broadcast(join_msg, room.id)

        try:
            while True:
                data = await websocket.receive_text()
                sanitized_content = sanitize_html(data)
                
                # Save to DB
                new_msg = ChatMessage(room_id=room.id, user_id=user.id, content=sanitized_content)
                db.add(new_msg)
                await db.commit()
                await db.refresh(new_msg)
                
                # Broadcast
                chat_msg = {
                    "type": "chat",
                    "id": new_msg.id,
                    "content": new_msg.content,
                    "created_at": new_msg.created_at.isoformat(),
                    "author": {
                        "id": user.id,
                        "username": user.username,
                        "level": user.level,
                        "role": user.role
                    }
                }
                await manager.broadcast(chat_msg, room.id)
                
        except WebSocketDisconnect:
            manager.disconnect(websocket, room.id)
            leave_msg = {
                "type": "system",
                "content": f"{user.username}님이 퇴장하셨습니다."
            }
            await manager.broadcast(leave_msg, room.id)
