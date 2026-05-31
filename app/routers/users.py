from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.point_log import PointLog
from app.models.post import Post, Comment

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "level": user.level,
        "total_points": user.total_points,
        "role": user.role,
        "bio": user.bio,
        "avatar_url": user.avatar_url
    }

from pydantic import BaseModel
from typing import Optional

class UserUpdate(BaseModel):
    bio: Optional[str] = None
    avatar_url: Optional[str] = None

@router.patch("/me")
async def update_me(update_data: UserUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    db_user = (await db.execute(select(User).where(User.id == user.id))).scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found")
        
    if update_data.bio is not None:
        db_user.bio = update_data.bio
    if update_data.avatar_url is not None:
        db_user.avatar_url = update_data.avatar_url
        
    await db.commit()
    return {"message": "Profile updated"}

@router.get("/me/points")
async def get_my_points(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    user_id = user.id
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
        
    logs_result = await db.execute(select(PointLog).where(PointLog.user_id == user_id).order_by(desc(PointLog.created_at)).limit(10))
    logs = logs_result.scalars().all()
    
    return {
        "total_points": user.total_points,
        "level": user.level,
        "logs": [{"id": l.id, "amount": l.amount, "reason": l.reason, "created_at": l.created_at} for l in logs]
    }
from fastapi import Query

@router.get("/me/posts")
async def get_my_posts(
    cursor: int = Query(None, description="Last post ID for cursor pagination"),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    query = select(Post).where(Post.author_id == user.id)
    if cursor:
        query = query.where(Post.id < cursor)
    
    query = query.order_by(desc(Post.id)).limit(limit)
    result = await db.execute(query)
    posts = result.scalars().all()
    
    return {
        "posts": [{"id": p.id, "title": p.title, "created_at": p.created_at, "post_type": p.post_type} for p in posts]
    }

@router.get("/me/comments")
async def get_my_comments(
    cursor: int = Query(None, description="Last comment ID for cursor pagination"),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    query = select(Comment).where(Comment.author_id == user.id)
    if cursor:
        query = query.where(Comment.id < cursor)
        
    query = query.order_by(desc(Comment.id)).limit(limit)
    result = await db.execute(query)
    comments = result.scalars().all()
    
    return {
        "comments": [{"id": c.id, "post_id": c.post_id, "content": c.content, "created_at": c.created_at} for c in comments]
    }

@router.get("/ranking")
async def get_ranking(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User)
        .where(User.role != 'admin', User.status == 'approved')
        .order_by(desc(User.total_points))
        .limit(50)
    )
    users = result.scalars().all()
    
    return {
        "ranking": [{"id": u.id, "username": u.username, "total_points": u.total_points, "level": u.level} for u in users]
    }
