from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.models.post import Post, Comment, PostLike
from app.models.room import Room
from app.models.user import User
from app.dependencies import get_current_user
from app.services.point_service import award_points, POINTS_POST, POINTS_COMMENT, POINTS_LIKE_RECEIVED
from app.services.notification_service import create_notification
from app.utils.sanitize import sanitize_html
from app.utils.limiter import limiter
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(tags=["posts"])

class PostCreate(BaseModel):
    title: str
    content: str
    post_type: str = 'feed'
    disclosure_tag: Optional[str] = None

class PostUpdate(BaseModel):
    title: str
    content: str

class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None

@router.get("/rooms/{slug}/posts")
async def get_posts(
    slug: str,
    cursor: int = Query(None, description="Last post ID for cursor pagination"),
    limit: int = Query(20, le=50),
    post_type: str = Query('feed', description="Type of post to fetch (feed/disclosure)"),
    tag: Optional[str] = Query(None, description="Tag to filter by if disclosure"),
    db: AsyncSession = Depends(get_db)
):
    room = (await db.execute(select(Room).where(Room.slug == slug))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room not found")
        
    query = select(Post, User).join(User, Post.author_id == User.id).where(Post.room_id == room.id)
    query = query.where(Post.post_type == post_type)
    
    if post_type == 'disclosure' and tag:
        query = query.where(Post.disclosure_tag == tag)
        
    if cursor:
        query = query.where(Post.id < cursor)
        
    query = query.order_by(desc(Post.id)).limit(limit)
    result = await db.execute(query)
    rows = result.all()
    
    # Get comment and like counts
    posts_data = []
    for p, u in rows:
        likes_count = (await db.execute(select(func.count()).where(PostLike.post_id == p.id))).scalar()
        comments_count = (await db.execute(select(func.count()).where(Comment.post_id == p.id))).scalar()
        
        posts_data.append({
            "id": p.id, 
            "title": p.title, 
            "content_preview": p.content[:100] + "..." if len(p.content) > 100 else p.content,
            "created_at": p.created_at,
            "post_type": p.post_type,
            "disclosure_tag": p.disclosure_tag,
            "author": {"id": u.id, "username": u.username, "level": u.level},
            "likes": likes_count,
            "comments": comments_count
        })
    
    return {"posts": posts_data}

import re
from app.services.notification_service import create_notification

@router.post("/rooms/{slug}/posts")
@limiter.limit("10/minute")
async def create_post(
    request: Request,
    slug: str,
    post_in: PostCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    room = (await db.execute(select(Room).where(Room.slug == slug))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room not found")
        
    if post_in.post_type == 'disclosure' and user.role not in ('admin', 'staff'):
        raise HTTPException(403, "공시방에는 스태프 및 관리자만 글을 작성할 수 있습니다.")
        
    new_post = Post(
        room_id=room.id,
        author_id=user.id,
        title=post_in.title,
        content=sanitize_html(post_in.content),
        post_type=post_in.post_type,
        disclosure_tag=post_in.disclosure_tag
    )
    db.add(new_post)
    await award_points(db, 1, POINTS_POST, "post_created", target_id=new_post.id)
    await db.commit()
    await db.refresh(new_post)
    
    # Mention logic
    mentions = re.findall(r'@([a-zA-Z0-9_가-힣]+)', post_in.content)
    if mentions:
        mentioned_users = (await db.execute(select(User).where(User.username.in_(mentions)))).scalars().all()
        for mu in mentioned_users:
            if mu.id != user.id:
                await create_notification(db, mu.id, 'mention', f"{user.username}님이 게시글에서 회원님을 언급했습니다.", f"/post/{new_post.id}")
                
    return {"id": new_post.id, "title": new_post.title}

@router.get("/posts/{post_id}")
async def get_post(post_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Post, User).join(User, Post.author_id == User.id).where(Post.id == post_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(404, "Post not found")
        
    post, author = row
        
    # Get comments
    comments_result = await db.execute(
        select(Comment, User).join(User, Comment.author_id == User.id).where(Comment.post_id == post_id).order_by(Comment.created_at)
    )
    comments = []
    for c, u in comments_result.all():
        comments.append({
            "id": c.id, 
            "content": c.content, 
            "parent_id": c.parent_id,
            "created_at": c.created_at,
            "author": {"id": u.id, "username": u.username, "level": u.level}
        })
        
    likes_count = (await db.execute(select(func.count()).where(PostLike.post_id == post_id))).scalar()
    
    return {
        "id": post.id,
        "title": post.title,
        "content": post.content,
        "post_type": post.post_type,
        "disclosure_tag": post.disclosure_tag,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
        "author": {"id": author.id, "username": author.username, "level": author.level},
        "likes": likes_count,
        "comments": comments
    }

@router.patch("/posts/{post_id}")
async def update_post(
    post_id: int,
    post_in: PostUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    post = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")
        
    if post.author_id != user.id and user.role not in ('admin', 'staff'):
        raise HTTPException(403, "작성자만 수정할 수 있습니다.")
        
    post.title = post_in.title
    post.content = sanitize_html(post_in.content)
    await db.commit()
    return {"message": "수정되었습니다."}

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    post = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    if not post:
        raise HTTPException(404, "Post not found")
        
    if post.author_id != user.id and user.role not in ('admin', 'staff'):
        raise HTTPException(403, "작성자만 삭제할 수 있습니다.")
        
    await db.delete(post)
    await award_points(db, post.author_id, -POINTS_POST, "post_deleted", target_id=post.id)
    await db.commit()
    return {"message": "삭제되었습니다."}

@router.post("/posts/{post_id}/comments")
@limiter.limit("20/minute")
async def create_comment(
    request: Request,
    post_id: int,
    comment_in: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    new_comment = Comment(
        post_id=post_id,
        author_id=user.id,
        content=sanitize_html(comment_in.content),
        parent_id=comment_in.parent_id
    )
    db.add(new_comment)
    await award_points(db, user.id, POINTS_COMMENT, "comment_created", target_id=new_comment.id)
    
    # Notify
    post = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
    
    # Mention logic
    notified_user_ids = set()
    mentions = re.findall(r'@([a-zA-Z0-9_가-힣]+)', comment_in.content)
    if mentions:
        mentioned_users = (await db.execute(select(User).where(User.username.in_(mentions)))).scalars().all()
        for mu in mentioned_users:
            if mu.id != user.id:
                await create_notification(db, mu.id, 'mention', f"{user.username}님이 댓글에서 회원님을 언급했습니다.", f"/post/{post_id}")
                notified_user_ids.add(mu.id)
                
    if post and post.author_id != user.id and post.author_id not in notified_user_ids:
        if comment_in.parent_id:
            parent_comment = (await db.execute(select(Comment).where(Comment.id == comment_in.parent_id))).scalar_one_or_none()
            if parent_comment and parent_comment.author_id != user.id and parent_comment.author_id not in notified_user_ids:
                await create_notification(db, parent_comment.author_id, 'comment', f"{user.username}님이 회원님의 댓글에 답글을 달았습니다.", f"/post/{post_id}")
        else:
            await create_notification(db, post.author_id, 'comment', f"{user.username}님이 회원님의 글에 댓글을 달았습니다.", f"/post/{post_id}")
            
    await db.commit()
    return {"id": new_comment.id}

@router.delete("/posts/{post_id}/comments/{comment_id}")
async def delete_comment(
    post_id: int,
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    comment = (await db.execute(select(Comment).where(Comment.id == comment_id, Comment.post_id == post_id))).scalar_one_or_none()
    if not comment:
        raise HTTPException(404, "Comment not found")
        
    if comment.author_id != user.id and user.role not in ('admin', 'staff'):
        raise HTTPException(403, "작성자만 삭제할 수 있습니다.")
        
    comment.is_deleted = True
    comment.content = "삭제된 댓글입니다."
    await award_points(db, comment.author_id, -POINTS_COMMENT, "comment_deleted", target_id=comment.id)
    await db.commit()
    return {"message": "삭제되었습니다."}

@router.post("/posts/{post_id}/like")
async def toggle_like(
    post_id: int, 
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    existing = (await db.execute(select(PostLike).where(PostLike.post_id == post_id, PostLike.user_id == user.id))).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        action = "unliked"
    else:
        db.add(PostLike(post_id=post_id, user_id=user.id))
        
        # Award point to author
        post = (await db.execute(select(Post).where(Post.id == post_id))).scalar_one_or_none()
        if post:
            await award_points(db, post.author_id, POINTS_LIKE_RECEIVED, "like_received", target_id=post_id)
            if post.author_id != user.id:
                await create_notification(db, post.author_id, 'like', f"{user.username}님이 회원님의 글을 좋아합니다.", f"/post/{post_id}")
            
        action = "liked"
    await db.commit()
    return {"status": action}
