from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.models.invitation import Invitation
from app.models.membership_proof import MembershipProof
from app.utils.media import upload_proof_image
from app.utils.security import verify_password, get_password_hash, create_access_token
from datetime import datetime, timezone

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
async def login(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == form_data.username))).scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(user.id)})
    
    # HttpOnly 쿠키 설정
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=3600 # 1 hour
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/invitations/{token}/signup")
async def signup(
    token: str,
    username: str = Form(...),
    password: str = Form(...),
    proof_image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Invitation).where(Invitation.token == token))
    invitation = result.scalar_one_or_none()
    
    if not invitation or invitation.status != 'pending' or invitation.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="유효하지 않은 초대 링크입니다.")
        
    # Check username
    existing_user = await db.execute(select(User).where(User.username == username))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 사용중인 닉네임입니다.")
        
    # Upload proof
    image_url = await upload_proof_image(proof_image)
    
    # Create user
    new_user = User(
        email=invitation.email,
        username=username,
        hashed_pw=get_password_hash(password),
        invited_by=invitation.inviter_id
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    # Create proof
    proof = MembershipProof(
        user_id=new_user.id,
        image_url=image_url
    )
    db.add(proof)
    
    # Update invitation
    invitation.status = 'accepted'
    
    await db.commit()
    return {"message": "가입 신청이 완료되었습니다. 관리자 승인을 기다려주세요."}

@router.post("/refresh")
async def refresh_token():
    # TODO: Implement token refresh
    return {"message": "Refresh endpoint"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Logged out"}

from pydantic import BaseModel
class PasswordResetRequest(BaseModel):
    email: str

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

@router.post("/password-reset/request")
async def request_password_reset(
    data: PasswordResetRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.utils.email import send_password_reset_email
    user = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if user:
        from datetime import timedelta
        # generate a token
        token = create_access_token({"sub": str(user.id), "type": "reset"}, timedelta(minutes=30))
        await send_password_reset_email(user.email, token)
    # Always return success to prevent email enumeration
    return {"message": "이메일이 등록되어 있다면 재설정 링크가 발송됩니다."}

@router.post("/password-reset/confirm")
async def confirm_password_reset(
    data: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    from app.utils.security import decode_access_token
    payload = decode_access_token(data.token)
    if not payload or payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 토큰입니다.")
        
    user_id = int(payload.get("sub"))
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
        
    user.hashed_pw = get_password_hash(data.new_password)
    await db.commit()
    return {"message": "비밀번호가 성공적으로 재설정되었습니다."}
