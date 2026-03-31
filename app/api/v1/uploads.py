"""Presigned URL generation for evidence file uploads.

This endpoint generates presigned S3 URLs that SDKs and clients use
to upload evidence files directly to cloud storage.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.api.deps import CurrentUser

router = APIRouter()


class PresignResponse(BaseModel):
    """Response containing presigned upload URL and metadata."""

    upload_url: str
    file_key: str
    public_url: str
    expires_in: int = 3600  # seconds


class PresignRequest(BaseModel):
    """Request for generating a presigned upload URL."""

    filename: str
    content_type: str = "image/jpeg"
    file_size: int = 0  # bytes, 0 = unknown


@router.post("/uploads/presign", response_model=PresignResponse)
async def generate_presigned_url(
    request: PresignRequest,
    current_user: CurrentUser,
) -> PresignResponse:
    """Generate a presigned URL for uploading evidence files.

    The client uploads the file directly to cloud storage using the
    returned URL, then passes the public_url to the evidence endpoint.

    Args:
        request: Upload request with filename and content type.
        current_user: Authenticated user.

    Returns:
        PresignResponse with upload URL and file metadata.
    """
    # Validate content type
    allowed_types = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "video/mp4",
        "video/quicktime",
        "video/webm",
    ]
    if request.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Content type '{request.content_type}' not allowed. "
            f"Allowed types: {', '.join(allowed_types)}",
        )

    # Validate file size (max 50MB)
    max_size = 50 * 1024 * 1024  # 50MB
    if request.file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File size exceeds maximum of {max_size // (1024 * 1024)}MB",
        )

    # Generate unique file key
    ext = _get_extension(request.filename, request.content_type)
    file_key = (
        f"evidence/{current_user.id}/{datetime.utcnow().strftime('%Y/%m/%d')}"
        f"/{uuid.uuid4().hex}{ext}"
    )

    # Generate presigned URL — use S3 in production, fallback URL in dev
    if settings.AWS_ACCESS_KEY_ID and settings.is_production:
        try:
            import boto3

            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            upload_url = s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": settings.S3_BUCKET,
                    "Key": file_key,
                    "ContentType": request.content_type,
                },
                ExpiresIn=3600,
            )
            public_url = f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{file_key}"
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate upload URL: {str(e)}",
            )
    else:
        # Development fallback
        storage_base = settings.STORAGE_BASE_URL
        upload_url = f"{storage_base}/upload/{file_key}?content-type={request.content_type}"
        public_url = f"{storage_base}/{file_key}"

    return PresignResponse(
        upload_url=upload_url,
        file_key=file_key,
        public_url=public_url,
        expires_in=3600,
    )


def _get_extension(filename: str, content_type: str) -> str:
    """Get file extension from filename or content type."""
    if "." in filename:
        return f".{filename.rsplit('.', 1)[-1].lower()}"

    type_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
        "video/mp4": ".mp4",
        "video/quicktime": ".mov",
        "video/webm": ".webm",
    }
    return type_map.get(content_type, ".bin")
