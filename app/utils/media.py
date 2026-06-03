from fastapi import UploadFile, HTTPException
import filetype
from pathlib import Path

MEDIA_CONFIG = {
    "proof_image": {
        "max_bytes": 5 * 1024 * 1024,
        "allowed_extensions": [".jpg", ".jpeg", ".png"],
        "allowed_mimes": ["image/jpeg", "image/png"]
    },
    "post_image": {
        "max_bytes": 10 * 1024 * 1024,
        "allowed_extensions": [".jpg", ".jpeg", ".png", ".gif", ".webp"],
        "allowed_mimes": ["image/jpeg", "image/png", "image/gif", "image/webp"]
    }
}

async def validate_upload(file: UploadFile, config_type: str = "proof_image"):
    config = MEDIA_CONFIG.get(config_type)
    if not config:
        raise ValueError("Invalid config type")
        
    # 1. 확장자 검증
    ext = Path(file.filename).suffix.lower()
    if ext not in config["allowed_extensions"]:
        raise HTTPException(status_code=400, detail=f"허용되지 않는 확장자입니다: {ext}")
        
    # 2. MIME 타입 검증
    header = await file.read(2048)
    kind = filetype.guess(header)
    mime = kind.mime if kind else "application/octet-stream"
    if mime not in config["allowed_mimes"]:
        raise HTTPException(status_code=400, detail=f"허용되지 않는 파일 형식입니다: {mime}")
    await file.seek(0)
    
    # 3. 크기 검증
    content = await file.read()
    if len(content) > config["max_bytes"]:
        raise HTTPException(status_code=400, detail=f"파일 크기를 초과했습니다 (최대 {config['max_bytes']//(1024*1024)}MB).")
    await file.seek(0)
    
    return content, mime

import boto3
import asyncio
from app.config import settings
import uuid

from PIL import Image
import io

def process_image(content: bytes, max_width: int = 1200) -> bytes:
    """Processes image: resizes if too large, converts to WebP, strips metadata."""
    img = Image.open(io.BytesIO(content))
    
    # Strip EXIF and convert to RGB
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    else:
        img = img.convert("RGB")
        
    # Resize if too large to save Render's memory and bandwidth
    if img.width > max_width:
        ratio = max_width / float(img.width)
        height = int(float(img.height) * float(ratio))
        img = img.resize((max_width, height), Image.Resampling.LANCZOS)
    
    out = io.BytesIO()
    img.save(out, format="WEBP", quality=75) # Slightly lower quality for better compression
    return out.getvalue()

async def upload_image(file: UploadFile, config_type: str = "post_image") -> str:
    content, mime = await validate_upload(file, config_type)
    
    # Process and convert to WebP
    try:
        content = await asyncio.to_thread(process_image, content)
        mime = "image/webp"
        filename = f"{uuid.uuid4().hex}.webp"
    except Exception as e:
        print(f"Image processing error: {e}")
        # Fallback to original if processing fails (but still use original filename for security)
        filename = f"{uuid.uuid4().hex}{Path(file.filename).suffix.lower()}"
    
    return await _save_to_storage(content, mime, filename, "posts" if config_type == "post_image" else "proofs")

async def upload_proof_image(file: UploadFile) -> str:
    # Legacy wrapper or specialized if needed
    return await upload_image(file, "proof_image")

async def _save_to_storage(content: bytes, mime: str, filename: str, folder: str) -> str:
    # If S3 is not configured, fallback to Base64 (Useful for local dev or simple free tier)
    if not all([settings.AWS_ACCESS_KEY, settings.AWS_SECRET_KEY, settings.S3_BUCKET_NAME, settings.S3_REGION]):
        import base64
        b64 = base64.b64encode(content).decode('utf-8')
        return f"data:{mime};base64,{b64}"

    # Use S3
    kwargs = {
        'aws_access_key_id': settings.AWS_ACCESS_KEY,
        'aws_secret_access_key': settings.AWS_SECRET_KEY,
        'region_name': settings.S3_REGION
    }
    if settings.S3_ENDPOINT_URL:
        kwargs['endpoint_url'] = settings.S3_ENDPOINT_URL
        
    s3_client = boto3.client('s3', **kwargs)
    
    object_name = f"{folder}/{filename}"
    
    def upload_to_s3():
        s3_client.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=object_name,
            Body=content,
            ContentType=mime
        )
        
    await asyncio.to_thread(upload_to_s3)
    return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.S3_REGION}.amazonaws.com/{object_name}"

