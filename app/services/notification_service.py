from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification
import asyncio
import json

# Global dictionary to keep track of active SSE queues per user
# user_id -> List of asyncio.Queue
active_connections: dict[int, list[asyncio.Queue]] = {}

def subscribe_user(user_id: int) -> asyncio.Queue:
    if user_id not in active_connections:
        active_connections[user_id] = []
    queue = asyncio.Queue()
    active_connections[user_id].append(queue)
    return queue

def unsubscribe_user(user_id: int, queue: asyncio.Queue):
    if user_id in active_connections and queue in active_connections[user_id]:
        active_connections[user_id].remove(queue)
        if not active_connections[user_id]:
            del active_connections[user_id]

async def create_notification(
    db: AsyncSession,
    user_id: int,
    type: str,
    message: str,
    link: str = None
):
    notif = Notification(
        user_id=user_id,
        type=type,
        message=message,
        link=link
    )
    db.add(notif)
    # The caller is responsible for committing the session
    
    # Broadcast to connected SSE clients
    if user_id in active_connections:
        event_data = {
            "type": type,
            "message": message,
            "link": link
        }
        json_data = json.dumps(event_data)
        for queue in active_connections[user_id]:
            await queue.put(json_data)
