from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, desc
from typing import List, Dict
import json

from app.database import get_db, AsyncSessionLocal
from app.dependencies import get_current_user, get_current_user_ws
from app.models.user import User
from app.models.dm import DirectMessage

router = APIRouter(prefix="/dm", tags=["dm"])

# Store active connections: user_id -> WebSocket
class DMConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: int):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: int):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = DMConnectionManager()

def check_dm_permission(user: User):
    if user.role not in ['admin', 'editor'] and user.level < 4:
        raise HTTPException(403, "1:1 메시지는 Lv.4 이상부터 사용할 수 있습니다.")

@router.get("/conversations")
async def get_conversations(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_dm_permission(user)
    
    # Get all users the current user has exchanged messages with
    # This requires querying messages where sender_id=user.id OR receiver_id=user.id
    # We will get distinct users
    result = await db.execute(
        select(DirectMessage.sender_id, DirectMessage.receiver_id)
        .where(or_(DirectMessage.sender_id == user.id, DirectMessage.receiver_id == user.id))
        .order_by(desc(DirectMessage.created_at))
    )
    
    user_ids = set()
    for row in result.all():
        s_id, r_id = row
        if s_id != user.id:
            user_ids.add(s_id)
        if r_id != user.id:
            user_ids.add(r_id)
            
    # Now fetch user details
    if not user_ids:
        return {"conversations": []}
        
    users_res = await db.execute(select(User).where(User.id.in_(user_ids)))
    users_dict = {u.id: u for u in users_res.scalars().all()}
    
    convs = []
    for uid in user_ids:
        if uid in users_dict:
            u = users_dict[uid]
            convs.append({
                "id": u.id,
                "username": u.username,
                "level": u.level,
                "avatar_url": u.avatar_url
            })
            
    return {"conversations": convs}

@router.get("/{target_id}/history")
async def get_dm_history(target_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_dm_permission(user)
    
    result = await db.execute(
        select(DirectMessage, User)
        .join(User, DirectMessage.sender_id == User.id)
        .where(
            or_(
                and_(DirectMessage.sender_id == user.id, DirectMessage.receiver_id == target_id),
                and_(DirectMessage.sender_id == target_id, DirectMessage.receiver_id == user.id)
            )
        )
        .order_by(DirectMessage.created_at.asc())
        .limit(100)
    )
    
    history = []
    for msg, sender in result.all():
        history.append({
            "id": msg.id,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "sender_id": msg.sender_id,
            "sender_name": sender.username,
            "read_at": msg.read_at.isoformat() if msg.read_at else None
        })
        
    return {"history": history}

@router.websocket("/{target_id}/ws")
async def dm_websocket(websocket: WebSocket, target_id: int, token: str):
    user = await get_current_user_ws(token)
    if not user:
        await websocket.close(code=1008)
        return
        
    if user.role not in ['admin', 'editor'] and user.level < 4:
        await websocket.close(code=1008, reason="Lv.4+")
        return

    await manager.connect(websocket, user.id)
    try:
        while True:
            data = await websocket.receive_text()
            
            # Save message to DB
            async with AsyncSessionLocal() as db:
                new_msg = DirectMessage(
                    sender_id=user.id,
                    receiver_id=target_id,
                    content=data
                )
                db.add(new_msg)
                await db.commit()
                await db.refresh(new_msg)
                
                msg_payload = {
                    "id": new_msg.id,
                    "content": new_msg.content,
                    "created_at": new_msg.created_at.isoformat(),
                    "sender_id": user.id,
                    "sender_name": user.username
                }
                
                # Send back to sender
                await manager.send_personal_message(json.dumps(msg_payload), user.id)
                # Send to receiver if online
                await manager.send_personal_message(json.dumps(msg_payload), target_id)
                
    except WebSocketDisconnect:
        manager.disconnect(user.id)
