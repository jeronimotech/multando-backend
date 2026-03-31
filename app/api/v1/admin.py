"""Super-admin API endpoints.

All endpoints require UserRole.ADMIN (platform super-admin).
Covers authority CRUD, staff management, city management, and platform stats.
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser, DbSession
from app.models.city import City
from app.schemas.admin import (
    AddStaffRequest,
    AuthorityCreateRequest,
    AuthorityCreatedAdminResponse,
    AuthorityDetailResponse,
    AuthorityListItem,
    AuthorityListResponse,
    AuthorityUpdateRequest,
    CityCreateRequest,
    CityUpdateRequest,
    PlatformStatsResponse,
    StaffMemberResponse,
    UpdateStaffRoleRequest,
)
from app.schemas.city import CityResponse
from app.services.admin import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _authority_detail(authority) -> AuthorityDetailResponse:
    """Map an Authority ORM object (with loaded relations) to a response."""
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
# Authority management
# ---------------------------------------------------------------------------


@router.post(
    "/authorities",
    response_model=AuthorityCreatedAdminResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new authority",
)
async def create_authority(
    body: AuthorityCreateRequest,
    admin: AdminUser,
    db: DbSession,
) -> AuthorityCreatedAdminResponse:
    svc = AdminService(db)

    # Validate city exists
    city = await db.get(City, body.city_id)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"City with id {body.city_id} not found",
        )

    try:
        authority, api_key = await svc.create_authority(
            name=body.name,
            code=body.code,
            city_id=body.city_id,
            country=body.country,
            contact_email=body.contact_email,
            contact_name=body.contact_name,
            subscription_tier=body.subscription_tier,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    detail = await svc.get_authority_detail(authority.id)
    return AuthorityCreatedAdminResponse(
        authority=_authority_detail(detail),
        api_key=api_key,
    )


@router.get(
    "/authorities",
    response_model=AuthorityListResponse,
    summary="List all authorities (paginated)",
)
async def list_authorities(
    admin: AdminUser,
    db: DbSession,
    page: int = 1,
    page_size: int = 20,
) -> AuthorityListResponse:
    svc = AdminService(db)
    authorities, total = await svc.list_authorities(page, page_size)
    items = [
        AuthorityListItem(
            id=a.id,
            name=a.name,
            code=a.code,
            country=a.country,
            city=a.city,
            city_id=a.city_id,
            subscription_tier=a.subscription_tier,
            contact_email=a.contact_email,
            staff_count=len(a.users) if a.users else 0,
            created_at=a.created_at,
        )
        for a in authorities
    ]
    return AuthorityListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/authorities/{authority_id}",
    response_model=AuthorityDetailResponse,
    summary="Get authority detail with staff list",
)
async def get_authority(
    authority_id: int,
    admin: AdminUser,
    db: DbSession,
) -> AuthorityDetailResponse:
    svc = AdminService(db)
    authority = await svc.get_authority_detail(authority_id)
    if not authority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authority not found",
        )
    return _authority_detail(authority)


@router.put(
    "/authorities/{authority_id}",
    response_model=AuthorityDetailResponse,
    summary="Update an authority",
)
async def update_authority(
    authority_id: int,
    body: AuthorityUpdateRequest,
    admin: AdminUser,
    db: DbSession,
) -> AuthorityDetailResponse:
    svc = AdminService(db)
    updates = body.model_dump(exclude_unset=True)
    authority = await svc.update_authority(authority_id, updates)
    if not authority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authority not found",
        )
    detail = await svc.get_authority_detail(authority.id)
    return _authority_detail(detail)


@router.delete(
    "/authorities/{authority_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate an authority",
)
async def deactivate_authority(
    authority_id: int,
    admin: AdminUser,
    db: DbSession,
) -> dict:
    svc = AdminService(db)
    authority = await svc.deactivate_authority(authority_id)
    if not authority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authority not found",
        )
    return {"detail": "Authority deactivated"}


# ---------------------------------------------------------------------------
# Authority staff management (super admin)
# ---------------------------------------------------------------------------


@router.post(
    "/authorities/{authority_id}/users",
    response_model=StaffMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a user to an authority",
)
async def add_staff(
    authority_id: int,
    body: AddStaffRequest,
    admin: AdminUser,
    db: DbSession,
) -> StaffMemberResponse:
    from app.models import Authority as AuthModel

    svc = AdminService(db)

    # Ensure authority exists
    authority = await db.get(AuthModel, authority_id)
    if not authority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Authority not found",
        )

    try:
        au = await svc.add_staff_to_authority(authority_id, body.email, body.role)
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


@router.delete(
    "/authorities/{authority_id}/users/{user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove a user from an authority",
)
async def remove_staff(
    authority_id: int,
    user_id: UUID,
    admin: AdminUser,
    db: DbSession,
) -> dict:
    svc = AdminService(db)
    removed = await svc.remove_staff(authority_id, user_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff member not found in this authority",
        )
    return {"detail": "Staff member removed"}


@router.put(
    "/authorities/{authority_id}/users/{user_id}",
    response_model=StaffMemberResponse,
    summary="Update a staff member's role",
)
async def update_staff_role(
    authority_id: int,
    user_id: UUID,
    body: UpdateStaffRoleRequest,
    admin: AdminUser,
    db: DbSession,
) -> StaffMemberResponse:
    svc = AdminService(db)
    au = await svc.update_staff_role(authority_id, user_id, body.role)
    if not au:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff member not found in this authority",
        )
    # Reload user relation
    await db.refresh(au, attribute_names=["user"])
    return StaffMemberResponse(
        user_id=au.user_id,
        email=au.user.email if au.user else None,
        display_name=au.user.display_name if au.user else None,
        role=au.role,
        joined_at=au.created_at,
    )


# ---------------------------------------------------------------------------
# City management (super admin)
# ---------------------------------------------------------------------------


@router.post(
    "/cities",
    response_model=CityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new city",
)
async def create_city(
    body: CityCreateRequest,
    admin: AdminUser,
    db: DbSession,
) -> CityResponse:
    svc = AdminService(db)
    try:
        city = await svc.create_city(
            name=body.name,
            country_code=body.country_code,
            state_province=body.state_province,
            latitude=body.latitude,
            longitude=body.longitude,
            timezone=body.timezone,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return CityResponse.model_validate(city)


@router.put(
    "/cities/{city_id}",
    response_model=CityResponse,
    summary="Update a city",
)
async def update_city(
    city_id: int,
    body: CityUpdateRequest,
    admin: AdminUser,
    db: DbSession,
) -> CityResponse:
    svc = AdminService(db)
    updates = body.model_dump(exclude_unset=True)
    city = await svc.update_city(city_id, updates)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found",
        )
    return CityResponse.model_validate(city)


@router.delete(
    "/cities/{city_id}",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a city",
)
async def deactivate_city(
    city_id: int,
    admin: AdminUser,
    db: DbSession,
) -> dict:
    svc = AdminService(db)
    city = await svc.deactivate_city(city_id)
    if not city:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="City not found",
        )
    return {"detail": "City deactivated"}


# ---------------------------------------------------------------------------
# Platform stats
# ---------------------------------------------------------------------------


@router.get(
    "/stats",
    response_model=PlatformStatsResponse,
    summary="Platform-wide statistics",
)
async def platform_stats(
    admin: AdminUser,
    db: DbSession,
) -> PlatformStatsResponse:
    svc = AdminService(db)
    data = await svc.get_platform_stats()
    return PlatformStatsResponse(**data)
