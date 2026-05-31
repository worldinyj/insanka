import logging
from email.message import EmailMessage
import aiosmtplib
from app.config import settings

logger = logging.getLogger(__name__)

async def send_email(to_email: str, subject: str, content: str, is_html: bool = False):
    if not all([settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASS]):
        logger.info(f"MOCK EMAIL SENT to {to_email}: {subject}\n{content}")
        return

    message = EmailMessage()
    message["From"] = settings.SMTP_USER
    message["To"] = to_email
    message["Subject"] = subject
    
    if is_html:
        message.add_alternative(content, subtype='html')
    else:
        message.set_content(content)

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASS,
            start_tls=True
        )
        logger.info(f"Email successfully sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")

async def send_invitation_email(email: str, inviter_username: str, token: str):
    invite_url = f"{settings.FRONTEND_URL or 'http://localhost:8000'}/invite/{token}"
    subject = f"[인산가 커뮤니티] {inviter_username}님이 초대하셨습니다"
    content = f"{inviter_username}님이 인산가 주주 커뮤니티에 초대하셨습니다.\n다음 링크를 통해 가입을 완료해 주세요:\n{invite_url}"
    await send_email(email, subject, content)

async def send_approval_email(email: str):
    subject = "[인산가 커뮤니티] 회원 가입이 승인되었습니다"
    content = "인산가 커뮤니티 회원 가입이 승인되었습니다.\n지금 바로 로그인하여 활동을 시작해 보세요!"
    await send_email(email, subject, content)

async def send_rejection_email(email: str, reason: str):
    subject = "[인산가 커뮤니티] 회원 가입이 거절되었습니다"
    content = f"가입이 거절되었습니다.\n\n사유: {reason}"
    await send_email(email, subject, content)

async def send_password_reset_email(email: str, token: str):
    reset_url = f"{settings.FRONTEND_URL or 'http://localhost:8000'}/password-reset?token={token}"
    subject = "[인산가 커뮤니티] 비밀번호 재설정"
    content = f"비밀번호를 재설정하려면 다음 링크를 클릭하세요 (30분간 유효):\n{reset_url}"
    await send_email(email, subject, content)
