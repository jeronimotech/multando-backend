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
        """Static S3 upload."""
        import asyncio

        def _put() -> str:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            s3.put_object(
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            return f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"

        return await asyncio.to_thread(_put)

    async def _upload_to_s3(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload bytes to S3 and return the public URL.

        Runs the blocking boto3 call in a thread to avoid
        blocking the async event loop.
        """

        def _put() -> str:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_REGION,
            )
            try:
                s3.put_object(
                    Bucket=settings.S3_BUCKET,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
            except ClientError as exc:
                logger.error("S3 upload failed for key=%s: %s", key, exc)
                raise
            url = f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
            logger.info("Uploaded to S3: %s", url)
            return url

        return await asyncio.get_event_loop().run_in_executor(None, _put)
