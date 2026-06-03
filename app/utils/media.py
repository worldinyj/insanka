from fastapi import UploadFile, HTTPException
import filetype
from pathlib import Path

MEDIA_CONFIG = {
    "proof_image": {
        "max_bytes": 5 * 1024 * 1024,
        "allowed_extensions": [".jpg", ".jpeg", ".png"],
        "allowed_mimes": ["image/jpeg", "image/png"]
    }
}

async def validate_upload(file: UploadFile, config_type: str = "proof_image"):
    config = MEDIA_CONFIG.get(config_type)
    if not config:
        raise ValueError("Invalid config type")
        
    # 1. 확장자 검증
    ext = Path(file.filename).suffix.lower()
    if ext not in config["allowed_extensions"]:
        raise HTTPException(status_code=400, detail="허용되지 않는 확장자입니다.")
        
    # 2. MIME 타입 검증
    header = await file.read(2048)
    kind = filetype.guess(header)
    mime = kind.mime if kind else "application/octet-stream"
    if mime not in config["allowed_mimes"]:
        raise HTTPException(status_code=400, detail="허용되지 않는 파일 형식입니다.")
    await file.seek(0)
    
    # 3. 크기 검증
    content = await file.read()
    if len(content) > config["max_bytes"]:
        raise HTTPException(status_code=400, detail="파일 크기를 초과했습니다.")
    await file.seek(0)
    
    return content, mime

import boto3
import asyncio
from app.config import settings
import uuid

from PIL import Image
import io

def convert_to_webp(content: bytes) -> bytes:
    """Converts image content to WebP format."""
    img = Image.open(io.BytesIO(content))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=80)
    return out.getvalue()

async def upload_proof_image(file: UploadFile) -> str:
    content, mime = await validate_upload(file, "proof_image")
    
    # Process and convert to WebP
    try:
        content = await asyncio.to_thread(convert_to_webp, content)
        mime = "image/webp"
        filename = f"{uuid.uuid4().hex}.webp"
    except Exception:
        # Fallback to original if processing fails
        filename = f"{uuid.uuid4().hex}{Path(file.filename).suffix.lower()}"
    
    # If S3 is not configured, fallback to Base64
    if not all([settings.AWS_ACCESS_KEY, settings.AWS_SECRET_KEY, settings.S3_BUCKET_NAME, settings.S3_REGION]):
        import base64
        b64 = base64.b64encode(content).decode('utf-8')
        return f"data:{mime};base64,{b64}"

    # Use S3
    s3_client = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
        region_name=settings.S3_REGION
    )
    
    object_name = f"proofs/{filename}"
    
    def upload_to_s3():
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=object_name,
            Body=content,
            ContentType=mime
        )
        
    await asyncio.to_thread(upload_to_s3)
    
    # Return the S3 public URL
    return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.S3_REGION}.amazonaws.com/{object_name}"

