"""Secure Evidence upload and verification endpoints.

These endpoints accept evidence captured with the Secure Evidence Capture
module, verify integrity, and persist the files + metadata.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.report import Evidence, Report
from app.models.enums import EvidenceType
from app.services.evidence_verification import EvidenceVerificationService

router = APIRouter(prefix="/evidence", tags=["evidence"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class VerificationDetail(BaseModel):
    """Individual check results from evidence verification."""

    signature_valid: bool = False
    timestamp_fresh: bool = False
    gps_plausible: bool = False
    capture_method_valid: bool = False
    motion_verified: bool = False
    not_duplicate: bool = False


class SecureUploadResponse(BaseModel):
    """Response from the secure-upload endpoint."""

    evidence_id: int
    report_id: str
    verified: bool
    checks: VerificationDetail
    failed_reasons: list[str]
    file_url: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/secure-upload",
    response_model=SecureUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload evidence with security verification",
)
async def secure_upload(
    file: UploadFile,
    report_id: str = Form(..., description="UUID of the parent report"),
    image_hash: str = Form(..., description="SHA-256 hex digest of original image bytes"),
    signature: str = Form(..., description="HMAC-SHA256 signature from the client"),
    timestamp: str = Form(..., description="ISO 8601 capture timestamp"),
    latitude: float = Form(...),
    longitude: float = Form(...),
    device_id: str = Form(...),
    capture_method: str = Form("camera"),
    motion_verified: bool = Form(False),
    platform: Optional[str] = Form(None),
    app_version: Optional[str] = Form(None),
    gps_accuracy: Optional[float] = Form(None),
    current_user: CurrentUser = ...,
    db: DbSession = ...,
) -> SecureUploadResponse:
    """Upload evidence with full security verification.

    Steps:
    1. Verify signature + metadata via ``EvidenceVerificationService``
    2. Upload image to S3 (or local storage for dev)
    3. Create Evidence record with verification status
    4. Return evidence ID + verification result

    The endpoint accepts ``multipart/form-data`` so the file and metadata
    travel in a single request.
    """
    # --- Validate report exists and belongs to user ---
    report_uuid: uuid.UUID
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid report_id format",
        )

    result = await db.execute(
        select(Report).where(
            Report.id == report_uuid,
            Report.reporter_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found or not owned by current user",
        )

    # --- Run verification ---
    verifier = EvidenceVerificationService(db)
    verification = await verifier.verify_evidence(
        image_hash=image_hash,
        signature=signature,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        device_id=device_id,
        capture_method=capture_method,
        motion_verified=motion_verified,
        user_id=current_user.id,
    )

    # --- Upload file ---
    file_content = await file.read()
    file_size = len(file_content)
    file_ext = (file.filename or "evidence.jpg").rsplit(".", 1)[-1]
    file_key = f"evidence/{current_user.id}/{report_id}/{uuid.uuid4()}.{file_ext}"

    # S3 upload (simplified — use presigned URL service in production)
    bucket = getattr(settings, "S3_BUCKET", None)
    file_url: str

    if bucket:
        import boto3

        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=bucket,
            Key=file_key,
            Body=file_content,
            ContentType=file.content_type or "image/jpeg",
        )
        cdn_domain = getattr(settings, "CDN_DOMAIN", f"{bucket}.s3.amazonaws.com")
        file_url = f"https://{cdn_domain}/{file_key}"
    else:
        # Local fallback for development
        import os

        upload_dir = os.path.join("uploads", "evidence")
        os.makedirs(upload_dir, exist_ok=True)
        local_path = os.path.join(upload_dir, f"{uuid.uuid4()}.{file_ext}")
        with open(local_path, "wb") as f:
            f.write(file_content)
        file_url = f"/uploads/{local_path}"

    # --- Build capture metadata ---
    capture_metadata = verifier.build_capture_metadata(
        device_id=device_id,
        motion_verified=motion_verified,
        capture_method=capture_method,
        platform=platform,
        app_version=app_version,
        gps_accuracy=gps_accuracy,
    )

    # --- Create Evidence record ---
    evidence = Evidence(
        report_id=report_uuid,
        type=EvidenceType.PHOTO,
        url=file_url,
        mime_type=file.content_type or "image/jpeg",
        file_size=file_size,
        capture_verified=verification["verified"],
        image_hash=image_hash,
        capture_signature=signature,
        capture_metadata=capture_metadata,
    )
    db.add(evidence)
    await db.commit()
    await db.refresh(evidence)

    checks = VerificationDetail(**verification["checks"])

    return SecureUploadResponse(
        evidence_id=evidence.id,
        report_id=report_id,
        verified=verification["verified"],
        checks=checks,
        failed_reasons=verification["failed_reasons"],
        file_url=file_url,
    )


@router.get(
    "/{evidence_id}/verification",
    summary="Get verification status of an evidence item",
)
async def get_verification_status(
    evidence_id: int,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Return the verification result and capture metadata for an evidence item."""
    result = await db.execute(
        select(Evidence)
        .join(Report, Report.id == Evidence.report_id)
        .where(
            Evidence.id == evidence_id,
            Report.reporter_id == current_user.id,
        )
    )
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evidence not found",
        )

    return {
        "evidence_id": evidence.id,
        "capture_verified": evidence.capture_verified,
        "image_hash": evidence.image_hash,
        "capture_metadata": evidence.capture_metadata,
    }
