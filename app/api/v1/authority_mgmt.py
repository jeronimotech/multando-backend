"""Authority-admin management endpoints.

All endpoints require the current user to hold an ADMIN role within their authority
(via the AuthorityAdmin dependency).
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthorityAdmin, DbSession
from app.schemas.admin import (
    AddStaffRequest,
    AuthorityDashboardResponse,
    AuthorityDetailResponse,
    StaffMemberResponse,
    UpdateStaffRoleRequest,
)
from app.schemas.city import CityResponse
from app.services.admin import AdminService

router = APIRouter(prefix="/authority-mgmt", tags=["authority-mgmt"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _authority_detail(authority) -> AuthorityDetailResponse:
    """Build a detail response from a loaded Authority object."""
    city_info = None
    if authority.city_rel:
        city_info = CityResponse.model_validate(authority.city_rel)

    staff = [
        StaffMemberResponse(
            user_id=au.user_id,
            email=au.user.email if au.user else None,
            display_name=au.user.display_name if au.user else None,
            role=au.role,
            joined_at=au.created_at,
        )
        for au in (authority.users or [])
    ]

    return AuthorityDetailResponse(
        id=authority.id,
        name=authority.name,
        code=authority.code,
        country=authority.country,
        city=authority.city,
        city_id=authority.city_id,
        city_info=city_info,
        subscription_tier=authority.subscription_tier,
        subscription_expires_at=authority.subscription_expires_at,
        rate_limit=authority.rate_limit,
        contact_email=authority.contact_email,
        contact_name=authority.contact_name,
        created_at=authority.created_at,
        staff=staff,
    )


# ---------------------------------------------------------------------------
# My authority info
# ---------------------------------------------------------------------------


@router.get(
    "/my-authority",
    response_model=AuthorityDetailResponse,
    summary="Get current user's authority info",
)
async def my_authority(
    auth: AuthorityAdmin,
    db: DbSession,
) -> AuthorityDetailResponse:
    user, authority = auth
    svc = AdminService(db)
    detail = await svc.get_authority_detail(authority.id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authority not found",
        )
    return _authority_detail(detail)


# ---------------------------------------------------------------------------
# Staff management
# ---------------------------------------------------------------------------


@router.get(
    "/staff",
    response_model=list[StaffMemberResponse],
    summary="List staff in my authority",
)
async def list_staff(
    auth: AuthorityAdmin,
    db: DbSession,
) -> list[StaffMemberResponse]:
    _, authority = auth
    svc = AdminService(db)
    detail = await svc.get_authority_detail(authority.id)
    if not detail:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authority not found",
        )
    return [
        StaffMemberResponse(
            user_id=au.user_id,
            email=au.user.email if au.user else None,
            display_name=au.user.display_name if au.user else None,
            role=au.role,
            joined_at=au.created_at,
        )
        for au in (detail.users or [])
    ]


@router.post(
    "/staff",
    response_model=StaffMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user to my authority",
)
async def add_staff(
    body: AddStaffRequest,
    auth: AuthorityAdmin,
    db: DbSession,
) -> StaffMemberResponse:
    _, authority = auth
    svc = AdminService(db)
    try:
        au = await svc.add_staff_to_authority(authority.id, body.email, body.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return StaffMemberResponse(
        user_id=au.user_id,
        email=au.user.email if au.user else body.email,
        display_name=au.user.display_name if au.user else None,
        role=au.role,
        joined_at=au.created_at,
    )


@router.put(
    "/staff/{user_id}",
    response_model=StaffMemberResponse,
    summary="Update a staff member's role",
)
async def update_staff_role(
    user_id: UUID,
    body: UpdateStaffRoleRequest,
    auth: AuthorityAdmin,
    db: DbSession,
) -> StaffMemberResponse:
    _, authority = auth
    svc = AdminService(db)
    au = await svc.update_staff_role(authority.id, user_id, body.role)
    if not au:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff member not found in this authority",
        )
    await db.refresh(au, attribute_names=["user"])
    return StaffMemberResponse(
        user_id=au.user_id,
        email=au.user.email if au.user else None,
        display_name=au.user.display_name if au.user else None,
        role=au.role,
        joined_at=au.created_at,
    )


@router.delete(
    "/staff/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove a staff member from my authority",
)
async def remove_staff(
    user_id: UUID,
    auth: AuthorityAdmin,
    db: DbSession,
) -> dict:
    _, authority = auth
    svc = AdminService(db)
    removed = await svc.remove_staff(authority.id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff member not found in this authority",
        )
    return {"detail": "Staff member removed"}


# ---------------------------------------------------------------------------
# Authority dashboard
# ---------------------------------------------------------------------------


@router.get(
    "/dashboard",
    response_model=AuthorityDashboardResponse,
    summary="Authority dashboard stats",
)
async def authority_dashboard(
    auth: AuthorityAdmin,
    db: DbSession,
) -> AuthorityDashboardResponse:
    _, authority = auth
    svc = AdminService(db)
    data = await svc.get_authority_dashboard(authority)
    return AuthorityDashboardResponse(**data)
