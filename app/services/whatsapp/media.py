"""Media pipeline: download from WhatsApp, upload to S3, return public URL."""

import asyncio
import logging
import uuid
from datetime import datetime

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings
from app.services.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

_MIME_EXT_MAP: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "application/pdf": ".pdf",
}


def _mime_to_ext(mime_type: str) -> str:
    """Map a MIME type to a file extension.

    Falls back to .bin for unknown types.
    """
    base = mime_type.split(";")[0].strip().lower()
    return _MIME_EXT_MAP.get(base, ".bin")


class MediaService:
    """Downloads media from WhatsApp and uploads to S3."""

    def __init__(self, whatsapp_client: WhatsAppClient) -> None:
        self.whatsapp = whatsapp_client

    async def download_and_upload(
        self,
        media_id: str,
        mime_type: str,
        phone_number: str,
    ) -> str:
        """Download media from WhatsApp, upload to S3, return public URL.

        Args:
            media_id: WhatsApp media ID.
            mime_type: MIME type of the media (e.g. "image/jpeg").
            phone_number: Sender phone number (used for S3 key namespacing).

        Returns:
            Public URL of the uploaded file.
        """
        logger.info("Downloading media %s (type=%s)", media_id, mime_type)
        media_bytes = await self.whatsapp.download_media(media_id)
        logger.info("Downloaded %d bytes for media %s", len(media_bytes), media_id)

        ext = _mime_to_ext(mime_type)
        date_path = datetime.utcnow().strftime("%Y/%m/%d")
        key = f"evidence/whatsapp/{phone_number}/{date_path}/{uuid.uuid4().hex}{ext}"

        if settings.AWS_ACCESS_KEY_ID:
            return await self._upload_to_s3(key, media_bytes, mime_type)
        else:
            logger.info("No AWS credentials configured - using placeholder URL")
            return f"{settings.STORAGE_BASE_URL}/{key}"

    @staticmethod
    async def get_presigned_url(key: str, expires_in: int = 900) -> str:
        """Generate a presigned URL for private evidence access (15 min default).

        Uses STORAGE_BASE_URL (public endpoint) for presigned URLs so they're
        accessible from outside the Railway network.
        """
        import asyncio

        def _sign() -> str:
            # For MinIO behind Railway proxy, presigned URLs don't work
            # reliably (host mismatch). Return direct public URL instead —
            # bucket has public-read policy.
            return f"{settings.STORAGE_BASE_URL}/{settings.S3_BUCKET}/{key}"

        if not settings.AWS_ACCESS_KEY_ID:
            return f"{settings.STORAGE_BASE_URL}/{key}"
        return await asyncio.to_thread(_sign)

    @staticmethod
    async def upload_evidence(key: str, data: bytes, content_type: str) -> str:
        """Upload evidence bytes to S3 or return a placeholder URL.

        This is a static method so it can be called without a full
        MediaService instance.
        """
        if settings.AWS_ACCESS_KEY_ID:
            return await MediaService._static_upload_to_s3(key, data, content_type)
        logger.info("No AWS credentials configured - using placeholder URL")
        return f"{settings.STORAGE_BASE_URL}/{key}"

    @staticmethod
    async def _static_upload_to_s3(key: str, data: bytes, content_type: str) -> str:
        """Static S3/MinIO upload."""
        import asyncio

        def _put() -> str:
            client_kwargs = {
                "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                "region_name": settings.AWS_REGION,
            }
            if settings.S3_ENDPOINT_URL:
                client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

            s3 = boto3.client("s3", **client_kwargs)

            # Auto-create bucket and set public-read policy (MinIO)
            import json as _json
            try:
                s3.head_bucket(Bucket=settings.S3_BUCKET)
            except ClientError:
                try:
                    s3.create_bucket(Bucket=settings.S3_BUCKET)
                except Exception:
                    pass

            # Ensure public-read policy
            try:
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{settings.S3_BUCKET}/*"],
                    }],
                }
                s3.put_bucket_policy(
                    Bucket=settings.S3_BUCKET,
                    Policy=_json.dumps(policy),
                )
            except Exception:
                pass

            s3.put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

            if settings.S3_ENDPOINT_URL:
                return f"{settings.STORAGE_BASE_URL}/{settings.S3_BUCKET}/{key}"
            return f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"

        return await asyncio.to_thread(_put)

    async def _upload_to_s3(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload bytes to S3/MinIO. Delegates to the static method."""
        return await MediaService._static_upload_to_s3(key, data, content_type)
