from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.invitation import Invitation
import os

router = APIRouter(tags=["pages"])

# Templates directory setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/")
async def home_page(request: Request):
    return templates.TemplateResponse(request=request, name="home.html")

@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@router.get("/password-reset")
async def password_reset_page(request: Request):
    return templates.TemplateResponse(request=request, name="password_reset.html")

@router.get("/rules")
async def rules_page(request: Request):
    return templates.TemplateResponse(request=request, name="rules.html")

@router.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html")

@router.get("/invite/{token}")
async def invite_page(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid token")
        
    # Mock inviter name
    inviter_name = "인산가 관리자"
    
    return templates.TemplateResponse(
        request=request,
        name="invite.html", 
        context={
            "token": token,
            "email": invitation.email,
            "inviter": inviter_name
        }
    )

@router.get("/signup")
async def signup_page(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    invitation = result.scalar_one_or_none()
    
    if not invitation:
        raise HTTPException(status_code=404, detail="Invalid token")
        
    return templates.TemplateResponse(
        request=request,
        name="signup.html", 
        context={
            "token": token,
            "email": invitation.email
        }
    )

@router.get("/room/{slug}")
async def room_page(request: Request, slug: str):
    # In reality, fetch room info and initial posts here
    return templates.TemplateResponse(request=request, name="room.html", context={"slug": slug})

@router.get("/post/{post_id}")
async def post_page(request: Request, post_id: int):
    # Fetch post data and comments
    return templates.TemplateResponse(request=request, name="post.html", context={"post_id": post_id})

@router.get("/room/{slug}/write")
async def post_form_page(request: Request, slug: str):
    return templates.TemplateResponse(request=request, name="post_form.html", context={"slug": slug})

@router.get("/profile")
async def profile_page(request: Request):
    return templates.TemplateResponse(request=request, name="profile.html")

@router.get("/ranking")
async def ranking_page(request: Request):
    return templates.TemplateResponse(request=request, name="ranking.html")

@router.get("/admin")
async def admin_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html")

@router.get("/dm")
async def dm_page(request: Request):
    return templates.TemplateResponse(request=request, name="dm.html")

@router.get("/search")
async def search_page(request: Request):
    return templates.TemplateResponse(request=request, name="search.html")
