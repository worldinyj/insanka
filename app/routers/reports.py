from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.dependencies import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/reports", tags=["reports"])

class ReportCreate(BaseModel):
    target_type: str # 'user', 'post', 'comment'
    target_id: int
    reason: str

@router.post("")
async def create_report(report_in: ReportCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.notification_service import create_notification
    admins = (await db.execute(select(User).where(User.role == 'admin'))).scalars().all()
    for admin in admins:
        await create_notification(
            db, admin.id, 'system', 
            f"새로운 신고 접수: {report_in.target_type} ID {report_in.target_id} - 사유: {report_in.reason}",
            "/admin"
        )
    return {"message": "신고가 접수되었습니다."}
