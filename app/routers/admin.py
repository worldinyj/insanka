from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.membership_proof import MembershipProof
from app.dependencies import require_admin
from app.utils.email import send_approval_email, send_rejection_email
from app.utils.security import get_password_hash
from app.services.point_service import award_points, POINTS_SIGNUP
from app.services.notification_service import create_notification
from sqlalchemy.exc import IntegrityError
from app.models.post import Post, Comment
from app.models.warning import UserWarning
from app.models.vote import Vote, VoteOption
from app.routers.votes import VoteCreate
from sqlalchemy import func
from datetime import datetime, timezone
from pydantic import BaseModel
from app.models.room import Room
from app.services.notification_service import active_connections

router = APIRouter(prefix="/admin", tags=["admin"])

class PushRequest(BaseModel):
    message: str

@router.post("/push")
async def send_global_push(req: PushRequest, admin: User = Depends(require_admin)):
    import json
    msg = json.dumps({"type": "system", "message": f"[전체공지] {req.message}", "link": "/room/general"})
    for user_id, queues in active_connections.items():
        for q in queues:
            await q.put(msg)
    return {"message": f"{len(active_connections)}명의 사용자에게 공지를 발송했습니다."}

class RoomCreate(BaseModel):
    name: str
    slug: str
    description: str = ""

@router.post("/rooms")
async def create_room(room_in: RoomCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    existing = await db.execute(select(Room).where(Room.slug == room_in.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "해당 슬러그(slug)를 가진 게시판이 이미 존재합니다.")
        
    new_room = Room(name=room_in.name, slug=room_in.slug, description=room_in.description)
    db.add(new_room)
    await db.commit()
    return {"message": "게시판이 생성되었습니다.", "id": new_room.id}

@router.delete("/rooms/{room_id}")
async def delete_room(room_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    room = (await db.execute(select(Room).where(Room.id == room_id))).scalar_one_or_none()
    if not room:
        raise HTTPException(404, "Room not found")
        
    if room.slug == "general":
        raise HTTPException(400, "기본 통합게시판은 삭제할 수 없습니다.")
        
    await db.delete(room)
    await db.commit()
    return {"message": "게시판이 삭제되었습니다."}

class WarnRequest(BaseModel):
    reason: str

@router.get("/pending-members")
async def get_pending_members(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(
        select(MembershipProof, User)
        .join(User, MembershipProof.user_id == User.id)
        .where(MembershipProof.status == 'pending')
        .order_by(MembershipProof.created_at.desc())
    )
    rows = result.all()
    
    proofs_data = []
    for p, u in rows:
        proofs_data.append({
            "id": p.id,
            "user_id": u.id,
            "username": u.username,
            "email": u.email,
            "image_url": p.image_url,
            "created_at": p.created_at
        })
        
    return {"pending_count": len(proofs_data), "proofs": proofs_data}

@router.patch("/members/{user_id}/approve")
async def approve_member(user_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
        
    proof_result = await db.execute(select(MembershipProof).where(MembershipProof.user_id == user_id))
    proof = proof_result.scalar_one_or_none()
    
    if proof:
        proof.status = 'approved'
        proof.reviewer_id = admin.id
        proof.reviewed_at = datetime.now(timezone.utc)
        
    user.status = 'approved'
    user.approved_at = datetime.now(timezone.utc)
    
    await award_points(db, user.id, POINTS_SIGNUP, "signup_approved")
    await create_notification(db, user.id, 'system', "가입이 승인되었습니다! 인산가 커뮤니티에 오신 것을 환영합니다.", "/room/general")
    
    await db.commit()
    await send_approval_email(user.email)
    
    return {"message": "승인되었습니다."}

@router.patch("/members/{user_id}/reject")
async def reject_member(user_id: int, reason: str, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
        
    proof_result = await db.execute(select(MembershipProof).where(MembershipProof.user_id == user_id))
    proof = proof_result.scalar_one_or_none()
    
    if proof:
        proof.status = 'rejected'
        proof.reviewer_id = admin.id
        proof.review_note = reason
        proof.reviewed_at = datetime.now(timezone.utc)
        
    user.status = 'rejected'
    
    await db.commit()
    await send_rejection_email(user.email, reason)
    
    return {"message": "거절되었습니다."}

class AdminUserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str = "member"

@router.post("/members")
async def create_member_manually(
    user_data: AdminUserCreate, 
    db: AsyncSession = Depends(get_db), 
    admin: User = Depends(require_admin)
):
    try:
        new_user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_pw=get_password_hash(user_data.password),
            role=user_data.role,
            status='approved',
            level=1,
            total_points=0,
            approved_at=datetime.now(timezone.utc)
        )
        db.add(new_user)
        await db.commit()
        return {"message": "회원이 성공적으로 생성되었습니다.", "id": new_user.id}
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, "이미 존재하는 이메일 또는 닉네임입니다.")

@router.get("/members")
async def get_all_members(
    search: str = None, 
    db: AsyncSession = Depends(get_db), 
    admin: User = Depends(require_admin)
):
    query = select(User).order_by(User.id.desc())
    if search:
        query = query.where(
            (User.username.ilike(f"%{search}%")) | 
            (User.email.ilike(f"%{search}%"))
        )
    
    result = await db.execute(query)
    users = result.scalars().all()
    
    return {
        "members": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "status": u.status,
                "level": u.level,
                "points": u.total_points,
                "created_at": u.created_at
            }
            for u in users
        ]
    }

@router.patch("/members/{user_id}/ban")
async def ban_member(user_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    if user_id == admin.id:
        raise HTTPException(400, "자기 자신을 정지할 수 없습니다.")
        
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
        
    user.status = 'banned'
    await db.commit()
    
    return {"message": f"{user.username} 회원이 정지되었습니다."}

@router.patch("/members/{user_id}/warn")
async def warn_member(user_id: int, req: WarnRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
        
    warning = UserWarning(user_id=user.id, admin_id=admin.id, reason=req.reason)
    db.add(warning)
    
    await create_notification(db, user.id, 'system', f"관리자로부터 경고를 받았습니다: {req.reason}", "/room/general")
    await db.commit()
    
    return {"message": f"{user.username} 회원에게 경고를 발송했습니다."}

from sqlalchemy import text

@router.get("/dashboard/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    # 1. Basic counts
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    pending_users = (await db.execute(select(func.count(User.id)).where(User.status == 'pending'))).scalar()
    total_posts = (await db.execute(select(func.count(Post.id)))).scalar()
    total_comments = (await db.execute(select(func.count(Comment.id)))).scalar()
    
    # 2. Activity Trends (Last 7 days)
    # Note: SQLite specific date handling, for Postgres use DATE_TRUNC
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    seven_days_ago = now - timedelta(days=7)
    
    # User growth (Last 7 days)
    user_trend_query = select(
        func.date(User.created_at).label('date'),
        func.count(User.id).label('count')
    ).where(User.created_at >= seven_days_ago).group_by(func.date(User.created_at)).order_by('date')
    
    user_trend_result = await db.execute(user_trend_query)
    user_trend = [{"date": row[0], "count": row[1]} for row in user_trend_result.all()]
    
    # Post trends
    post_trend_query = select(
        func.date(Post.created_at).label('date'),
        func.count(Post.id).label('count')
    ).where(Post.created_at >= seven_days_ago).group_by(func.date(Post.created_at)).order_by('date')
    
    post_trend_result = await db.execute(post_trend_query)
    post_trend = [{"date": row[0], "count": row[1]} for row in post_trend_result.all()]
    
    return {
        "summary": {
            "total_users": total_users,
            "pending_users": pending_users,
            "total_posts": total_posts,
            "total_comments": total_comments
        },
        "trends": {
            "users": user_trend,
            "posts": post_trend
        },
        "system": {
            "version": "1.2.0",
            "environment": "production" if settings.DATABASE_URL.startswith("postgresql") else "development",
            "database": "PostgreSQL (Supabase)" if settings.DATABASE_URL.startswith("postgresql") else "SQLite",
            "storage": "AWS S3" if settings.S3_BUCKET_NAME else "Local/Base64 Fallback",
            "active_ws": len(active_connections)
        }
    }

@router.get("/system/logs")
async def get_system_logs(admin: User = Depends(require_admin)):
    # In a real environment, we'd read from a log file or a logging service.
    # For now, we return mock/recent logs for demonstration.
    return {
        "logs": [
            {"time": datetime.now().strftime("%H:%M:%S"), "level": "INFO", "msg": "Application startup complete."},
            {"time": (datetime.now() - timedelta(minutes=5)).strftime("%H:%M:%S"), "level": "INFO", "msg": "Database connection established."},
            {"time": (datetime.now() - timedelta(minutes=15)).strftime("%H:%M:%S"), "level": "WARN", "msg": "Rate limit triggered for IP 127.0.0.1"},
            {"time": (datetime.now() - timedelta(hours=1)).strftime("%H:%M:%S"), "level": "INFO", "msg": "Daily backup completed successfully."}
        ]
    }

@router.get("/votes")
async def get_admin_votes(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(select(Vote).order_by(Vote.created_at.desc()))
    votes = result.scalars().all()
    return {
        "votes": [
            {
                "id": v.id,
                "title": v.title,
                "is_multiple": v.is_multiple,
                "created_at": v.created_at,
                "ends_at": v.ends_at,
                "status": "closed" if v.ends_at and v.ends_at <= datetime.now(timezone.utc) else "active"
            }
            for v in votes
        ]
    }

@router.post("/votes")
async def create_admin_vote(vote_in: VoteCreate, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    # Create vote globally or in room 1 (General)
    new_vote = Vote(
        room_id=1,
        creator_id=admin.id,
        title=vote_in.title,
        is_multiple=vote_in.is_multiple,
        ends_at=vote_in.ends_at
    )
    db.add(new_vote)
    await db.commit()
    await db.refresh(new_vote)
    
    for opt in vote_in.options:
        db.add(VoteOption(vote_id=new_vote.id, text=opt.text))
        
    await db.commit()
    return {"message": "Vote created successfully", "id": new_vote.id}

@router.patch("/votes/{vote_id}/close")
async def close_admin_vote(vote_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(select(Vote).where(Vote.id == vote_id))
    vote = result.scalar_one_or_none()
    if not vote:
        raise HTTPException(404, "Vote not found")
        
    vote.ends_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Vote closed"}
