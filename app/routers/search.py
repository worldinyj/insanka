from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.database import get_db
from app.models.post import Post, Comment
from app.models.user import User

router = APIRouter(prefix="/search", tags=["search"])

@router.get("")
async def search_all(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db)
):
    search_term = f"%{q}%"
    
    # 1. Search Posts (Feeds & Disclosures)
    post_query = select(Post, User).join(
        User, Post.author_id == User.id
    ).where(
        or_(
            Post.title.ilike(search_term),
            Post.content.ilike(search_term)
        )
    ).order_by(Post.created_at.desc()).limit(20)
    
    post_result = await db.execute(post_query)
    posts = post_result.all()
    
    # 2. Search Comments
    comment_query = select(Comment, User, Post).join(
        User, Comment.author_id == User.id
    ).join(
        Post, Comment.post_id == Post.id
    ).where(
        Comment.content.ilike(search_term)
    ).order_by(Comment.created_at.desc()).limit(20)
    
    comment_result = await db.execute(comment_query)
    comments = comment_result.all()
    
    # Format results
    results = {
        "posts": [],
        "disclosures": [],
        "comments": []
    }
    
    for post, user in posts:
        item = {
            "id": post.id,
            "title": post.title,
            "content": post.content[:200] + "..." if len(post.content) > 200 else post.content,
            "author": {"username": user.username, "level": user.level},
            "created_at": post.created_at,
            "room_id": post.room_id
        }
        if post.post_type == "disclosure":
            item["disclosure_type"] = post.disclosure_tag if post.disclosure_tag else ""
            results["disclosures"].append(item)
        else:
            results["posts"].append(item)
            
    for comment, user, post in comments:
        results["comments"].append({
            "id": comment.id,
            "post_id": comment.post_id,
            "post_title": post.title if post.title else "제목 없음",
            "content": comment.content,
            "author": {"username": user.username, "level": user.level},
            "created_at": comment.created_at
        })
        
    return results
