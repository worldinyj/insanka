from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

app = FastAPI(title="Insanka API", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# Page routes are now handled by app/routers/pages.py

@app.on_event("startup")
async def startup_event():
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.models.room import Room
    from app.utils.security import get_password_hash
    from sqlalchemy import select
    from datetime import datetime, timezone
    
    async with AsyncSessionLocal() as session:
        # 1. Create Default Room
        room_result = await session.execute(select(Room).where(Room.slug == "general"))
        default_room = room_result.scalar_one_or_none()
        if not default_room:
            default_room = Room(
                name="통합게시판",
                slug="general",
                description="기본 통합 게시판입니다."
            )
            session.add(default_room)
            await session.commit()
            
        # 2. Create Default Admin
        result = await session.execute(select(User).where(User.email == "nsc.imp.atom@gmail.com"))
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            hashed_pw = get_password_hash("admin12345!")
            new_admin = User(
                email="nsc.imp.atom@gmail.com",
                username="총괄관리자",
                hashed_pw=hashed_pw,
                role="admin",
                status="approved",
                level=5,
                total_points=99999,
                approved_at=datetime.now(timezone.utc)
            )
            session.add(new_admin)
            await session.commit()


# CORS middleware setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import auth, pages, admin, invitations, posts, users, dashboard, notifications, chat, votes, events, dm, search, rooms, reports
app.include_router(auth.router, prefix="/api/v1")
app.include_router(invitations.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(posts.router, prefix="/api/v1")
app.include_router(votes.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(dm.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(rooms.router, prefix="/api/v1")
app.include_router(reports.router, prefix="/api/v1")
app.include_router(pages.router)

from fastapi.responses import RedirectResponse
