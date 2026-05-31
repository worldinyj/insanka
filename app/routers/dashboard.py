from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.models.post import Post
from app.models.user import User
from app.models.room import Room
from app.models.event import Event
from app.dependencies import get_current_user
from datetime import datetime, timezone

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/home")
async def get_home_dashboard(db: AsyncSession = Depends(get_db)):
    # 1. Fetch latest 5 feed posts across all rooms
    feed_query = (
        select(Post, User, Room)
        .join(User, Post.author_id == User.id)
        .join(Room, Post.room_id == Room.id)
        .where(Post.post_type == 'feed')
        .order_by(desc(Post.created_at))
        .limit(5)
    )
    feed_result = await db.execute(feed_query)
    feed_posts = []
    for p, u, r in feed_result.all():
        feed_posts.append({
            "id": p.id,
            "title": p.title,
            "content_preview": p.content[:100] + "..." if len(p.content) > 100 else p.content,
            "created_at": p.created_at,
            "room_slug": r.slug,
            "author": {"username": u.username, "level": u.level}
        })
        
    # 2. Fetch latest 3 disclosures
    disclosure_query = (
        select(Post, User, Room)
        .join(User, Post.author_id == User.id)
        .join(Room, Post.room_id == Room.id)
        .where(Post.post_type == 'disclosure')
        .order_by(desc(Post.created_at))
        .limit(3)
    )
    disclosure_result = await db.execute(disclosure_query)
    disclosures = []
    for p, u, r in disclosure_result.all():
        disclosures.append({
            "id": p.id,
            "title": p.title,
            "disclosure_tag": p.disclosure_tag,
            "created_at": p.created_at,
            "room_slug": r.slug
        })
        
    # 3. Fetch Top 5 leaderboard (based on total_points)
    top_users_query = (
        select(User)
        .where(User.status == 'approved')
        .where(User.role != 'admin')
        .order_by(desc(User.total_points))
        .limit(5)
    )
    top_users_result = await db.execute(top_users_query)
    leaderboard = []
    for idx, u in enumerate(top_users_result.scalars().all()):
        leaderboard.append({
            "rank": idx + 1,
            "username": u.username,
            "level": u.level,
            "points": u.total_points
        })
        
    # 4. Fetch upcoming 3 events
    events_query = (
        select(Event)
        .where(Event.start_time > datetime.now(timezone.utc))
        .order_by(Event.start_time.asc())
        .limit(3)
    )
    events_result = await db.execute(events_query)
    upcoming_events = []
    for evt in events_result.scalars().all():
        upcoming_events.append({
            "id": evt.id,
            "title": evt.title,
            "start_time": evt.start_time,
            "location": evt.location
        })
        
    return {
        "feed": feed_posts,
        "disclosures": disclosures,
        "leaderboard": leaderboard,
        "events": upcoming_events
    }
