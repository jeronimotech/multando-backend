"""Report endpoints for the Multando API.

This module provides endpoints for creating, retrieving, updating,
and deleting traffic violation reports.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models import ReportStatus
from app.schemas.common import MessageResponse
from app.schemas.evidence import EvidenceResponse, EvidenceType
from app.schemas.infraction import InfractionResponse
from app.schemas.report import (
    LocationSchema,
    ReportCreate,
    ReportDetail,
    ReportList,
    ReportStatus as SchemaReportStatus,
    ReportSummary,
    VehicleCategory as SchemaVehicleCategory,
    ReportSource as SchemaReportSource,
)
from app.schemas.user import UserPublic
from app.schemas.vehicle_type import VehicleTypeResponse
from app.services.report import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])


def _build_location_schema(report) -> LocationSchema:
    """Build a LocationSchema from a report model."""
    return LocationSchema(
        lat=report.latitude,
        lon=report.longitude,
        address=report.location_address,
        city=report.location_city,
        country=report.location_country,
    )


def _build_infraction_response(infraction) -> InfractionResponse:
    """Build an InfractionResponse from an infraction model."""
    from app.schemas.infraction import InfractionCategory, InfractionSeverity

    return InfractionResponse(
        id=infraction.id,
        code=infraction.code,
        name_en=infraction.name_en,
        name_es=infraction.name_es,
        description_en=infraction.description_en or "",
        description_es=infraction.description_es or "",
        category=InfractionCategory(infraction.category.value),
        severity=InfractionSeverity(infraction.severity.value),
        points_reward=infraction.points_reward,
        multa_reward=infraction.multa_reward,
        icon=infraction.icon,
    )


def _build_vehicle_type_response(vehicle_type) -> VehicleTypeResponse | None:
    """Build a VehicleTypeResponse from a vehicle type model."""
    if not vehicle_type:
        return None
    return VehicleTypeResponse(
        id=vehicle_type.id,
        code=vehicle_type.code,
        name_en=vehicle_type.name_en,
        name_es=vehicle_type.name_es,
        icon=vehicle_type.icon,
        plate_pattern=vehicle_type.plate_pattern,
        requires_plate=vehicle_type.requires_plate,
    )


def _build_user_public(user) -> UserPublic:
    """Build a UserPublic schema from a user model."""
    return UserPublic(
        id=user.id,
        username=user.username or "",
        display_name=user.display_name or user.username or "",
        avatar_url=user.avatar_url,
        points=user.points,
        level=None,  # Simplified for report context
        badges=[],
        created_at=user.created_at,
    )


def _fix_evidence_url(url: str) -> str:
    """Ensure evidence URL includes bucket name in path."""
    if url and settings.STORAGE_BASE_URL and url.startswith(settings.STORAGE_BASE_URL):
        path = url[len(settings.STORAGE_BASE_URL):]
        if not path.startswith(f"/{settings.S3_BUCKET}/"):
            return f"{settings.STORAGE_BASE_URL}/{settings.S3_BUCKET}{path}"
    return url


def _build_evidence_response(evidence) -> EvidenceResponse:
    """Build an EvidenceResponse from an evidence model."""
    return EvidenceResponse(
        id=evidence.id,
        type=EvidenceType(evidence.type.value),
        url=_fix_evidence_url(evidence.url),
        thumbnail_url=evidence.thumbnail_url,
        mime_type=evidence.mime_type,
        ipfs_hash=evidence.ipfs_hash,
        created_at=evidence.created_at,
    )


def _build_report_summary(report) -> ReportSummary:
    """Build a ReportSummary from a report model."""
    return ReportSummary(
        id=report.id,
        short_id=report.short_id,
        status=SchemaReportStatus(report.status.value),
        vehicle_plate=report.vehicle_plate,
        vehicle_type=_build_vehicle_type_response(report.vehicle_type),
        infraction=_build_infraction_response(report.infraction),
        location=_build_location_schema(report),
        created_at=report.created_at,
    )


def _build_report_detail(report) -> ReportDetail:
    """Build a ReportDetail from a report model."""
    return ReportDetail(
        id=report.id,
        short_id=report.short_id,
        status=SchemaReportStatus(report.status.value),
        vehicle_plate=report.vehicle_plate,
        vehicle_type=_build_vehicle_type_response(report.vehicle_type),
        infraction=_build_infraction_response(report.infraction),
        location=_build_location_schema(report),
        created_at=report.created_at,
        reporter=_build_user_public(report.reporter),
        verifier=_build_user_public(report.verifier) if report.verifier else None,
        evidences=[_build_evidence_response(e) for e in report.evidences],
        verified_at=report.verified_at,
        on_chain=report.on_chain,
        tx_signature=report.tx_signature,
        incident_datetime=report.incident_datetime,
        vehicle_category=SchemaVehicleCategory(report.vehicle_category.value)
        if hasattr(report.vehicle_category, "value")
        else SchemaVehicleCategory(report.vehicle_category),
        source=SchemaReportSource(report.source.value)
        if hasattr(report.source, "value")
        else SchemaReportSource(report.source),
        rejection_reason=report.rejection_reason,
    )


@router.post(
    "",
    response_model=ReportDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new report",
    description="Submit a new traffic infraction report. Requires authentication.",
)
async def create_report(
    data: ReportCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> ReportDetail:
    """Create a new traffic violation report.

    Creates a report and awards points to the reporter based on the infraction type.

    Args:
        data: Report creation data including infraction, vehicle, and location info.
        current_user: The authenticated user submitting the report.
        db: Database session.

    Returns:
        The created ReportDetail.

    Raises:
        HTTPException: 400 if infraction or vehicle type is not found.
    """
    report_service = ReportService(db)

    try:
        report = await report_service.create(current_user.id, data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return _build_report_detail(report)


@router.get(
    "",
    response_model=ReportList,
    summary="List reports",
    description="Get a paginated list of reports with optional filters.",
)
async def list_reports(
    db: DbSession,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status: SchemaReportStatus | None = Query(default=None, description="Filter by status"),
    infraction_id: int | None = Query(default=None, description="Filter by infraction ID"),
    city: str | None = Query(default=None, description="Filter by city"),
) -> ReportList:
    """List reports with pagination and filtering.

    This is a public endpoint that returns report summaries.

    Args:
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of items per page.
        status: Optional status filter.
        infraction_id: Optional infraction ID filter.
        city: Optional city filter.

    Returns:
        A paginated list of report summaries.
    """
    report_service = ReportService(db)

    # Convert schema status to model status if provided
    model_status = None
    if status:
        model_status = ReportStatus(status.value)

    reports, total = await report_service.list_reports(
        page=page,
        page_size=page_size,
        status=model_status,
        infraction_id=infraction_id,
        city=city,
    )

    return ReportList(
        items=[_build_report_summary(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/markers",
    summary="Get report markers for map display (public)",
    description="Returns recent reports with coordinates for map display. No auth required.",
)
async def get_report_markers(
    db: DbSession,
    status: SchemaReportStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Public endpoint for map markers. Returns minimal data for map pins."""
    from sqlalchemy import select
    from app.models import Report, Infraction

    q = select(Report).join(Infraction, Report.infraction_id == Infraction.id)
    if status:
        q = q.where(Report.status == status.value)
    q = q.order_by(Report.created_at.desc()).limit(limit)

    result = await db.execute(q)
    reports = result.scalars().all()

    markers = []
    for r in reports:
        if r.latitude is None or r.longitude is None:
            continue
        infraction = await db.get(Infraction, r.infraction_id)
        markers.append({
            "id": str(r.id),
            "shortId": r.short_id or "",
            "latitude": r.latitude,
            "longitude": r.longitude,
            "infraction": infraction.name_en if infraction else "",
            "vehiclePlate": r.vehicle_plate or "",
            "status": r.status.value if hasattr(r.status, 'value') else r.status,
            "createdAt": r.created_at.isoformat() if r.created_at else "",
        })
    return markers


@router.get(
    "/evidence/{evidence_id}/url",
    summary="Get presigned URL for evidence image",
    description="Returns a temporary signed URL to access a private evidence image.",
)
async def get_evidence_url(
    evidence_id: int,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get a presigned URL for an evidence image. Requires authentication."""
    from sqlalchemy import select
    from app.models.report import Evidence
    from app.services.whatsapp.media import MediaService

    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    url = evidence.url
    # Ensure the URL includes the bucket name in the path
    if url and settings.STORAGE_BASE_URL and url.startswith(settings.STORAGE_BASE_URL):
        path_after_base = url[len(settings.STORAGE_BASE_URL):]
        if not path_after_base.startswith(f"/{settings.S3_BUCKET}/"):
            url = f"{settings.STORAGE_BASE_URL}/{settings.S3_BUCKET}{path_after_base}"

    return {"url": url, "expires_in": 900}


@router.get(
    "/pending-verification",
    response_model=ReportList,
    summary="Get reports pending verification",
    description="Get reports that need verification, excluding user's own reports.",
)
async def get_pending_verification(
    current_user: CurrentUser,
    db: DbSession,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> ReportList:
    """Get reports pending verification.

    Returns reports with pending status that the current user can verify
    (excludes their own reports).

    Args:
        current_user: The authenticated user.
        db: Database session.
        page: Page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        A paginated list of pending reports.
    """
    report_service = ReportService(db)

    reports, total = await report_service.get_pending_for_verification(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )

    return ReportList(
        items=[_build_report_summary(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/by-plate/{plate}",
    response_model=list[ReportSummary],
    summary="Get reports by vehicle plate",
    description="Get reports for a specific vehicle license plate (max 50).",
)
async def get_reports_by_plate(
    plate: str,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=100, description="Maximum results"),
) -> list[ReportSummary]:
    """Get reports for a vehicle plate.

    This is a public endpoint that returns reports associated with
    a specific vehicle license plate, limited for safety.

    Args:
        plate: The vehicle license plate number.
        db: Database session.
        limit: Maximum number of results.

    Returns:
        A list of report summaries for the specified plate.
    """
    report_service = ReportService(db)
    reports = await report_service.get_by_plate(plate)

    return [_build_report_summary(r) for r in reports[:limit]]


@router.get(
    "/{report_id}",
    response_model=ReportDetail,
    summary="Get report by ID",
    description="Get detailed information about a specific report.",
)
async def get_report(
    report_id: str,
    db: DbSession,
) -> ReportDetail:
    """Get a report by ID or short ID.

    This is a public endpoint that accepts both UUID and short ID formats.

    Args:
        report_id: The report's UUID or short ID (e.g., RPT-A1B2C3).
        db: Database session.

    Returns:
        The detailed report information.

    Raises:
        HTTPException: 404 if report is not found.
    """
    report_service = ReportService(db)

    # Try to parse as UUID first
    try:
        uuid_id = UUID(report_id)
        report = await report_service.get_by_id(uuid_id)
    except ValueError:
        # Not a UUID, try as short_id
        report = await report_service.get_by_short_id(report_id)

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    return _build_report_detail(report)


@router.post(
    "/{report_id}/evidence",
    response_model=EvidenceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add evidence to a report",
    description="Upload evidence (image/video) for a report. Only the report owner can add evidence.",
)
async def add_evidence(
    report_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
    evidence_type: EvidenceType = Query(..., description="Type of evidence"),
    url: str = Query(..., description="URL of the evidence file"),
    mime_type: str = Query(default="image/jpeg", description="MIME type of the file"),
    thumbnail_url: str | None = Query(default=None, description="Thumbnail URL"),
    file_size: int = Query(default=0, ge=0, description="File size in bytes"),
) -> EvidenceResponse:
    """Add evidence to a report.

    Only the report owner can add evidence. Evidence includes images or videos
    that support the traffic violation report.

    Args:
        report_id: The UUID of the report.
        current_user: The authenticated user (must be report owner).
        db: Database session.
        evidence_type: Type of evidence (image/video).
        url: URL of the uploaded evidence file.
        mime_type: MIME type of the evidence file.
        thumbnail_url: Optional thumbnail URL.
        file_size: Size of the file in bytes.

    Returns:
        The created EvidenceResponse.

    Raises:
        HTTPException: 404 if report not found, 403 if not the owner.
    """
    report_service = ReportService(db)

    # Get the report to verify ownership
    report = await report_service.get_by_id(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )

    if report.reporter_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the report owner can add evidence",
        )

    try:
        evidence = await report_service.add_evidence(
            report_id=report_id,
            evidence_data={
                "type": evidence_type.value,
                "url": url,
                "thumbnail_url": thumbnail_url,
                "mime_type": mime_type,
                "file_size": file_size,
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return _build_evidence_response(evidence)


@router.delete(
    "/{report_id}",
    response_model=MessageResponse,
    summary="Delete a report",
    description="Delete a report. Only the owner can delete, and only if status is pending.",
)
async def delete_report(
    report_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Delete a report.

    Only the report owner can delete a report, and only if the status is pending.
    Once a report has been verified or is under review, it cannot be deleted.

    Args:
        report_id: The UUID of the report to delete.
        current_user: The authenticated user (must be report owner).
        db: Database session.

    Returns:
        A success message.

    Raises:
        HTTPException: 404 if not found, 403 if not owner, 400 if not pending.
    """
    report_service = ReportService(db)

    try:
        await report_service.delete(report_id, current_user.id)
    except ValueError as e:
        error_message = str(e)
        if "not found" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_message,
            )
        elif "owner" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_message,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_message,
            )

    return MessageResponse(
        message="Report deleted successfully",
        success=True,
    )
