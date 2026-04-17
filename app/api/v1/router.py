"""API v1 main router.

This module contains the main router for API v1, aggregating all endpoint routers.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.oauth import router as oauth_router
from app.api.v1.authorities import router as authorities_router
from app.api.v1.blockchain import router as blockchain_router
from app.api.v1.gamification import router as gamification_router
from app.api.v1.infractions import router as infractions_router
from app.api.v1.leaderboard import router as leaderboard_router
from app.api.v1.reports import router as reports_router
from app.api.v1.users import router as users_router
from app.api.v1.vehicle_types import router as vehicle_types_router
from app.api.v1.uploads import router as uploads_router
from app.api.v1.verification import router as verification_router
from app.api.v1.wallet import router as wallet_router
from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.admin import router as admin_router
from app.api.v1.authority_mgmt import router as authority_mgmt_router
from app.api.v1.authority_review import router as authority_review_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.cities import router as cities_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.whatsapp import router as whatsapp_router
from app.api.v1.widgets import router as widgets_router
from app.api.v1.partners import router as partners_router
from app.api.v1.public_stats import (
    router as public_stats_router,
    public_authority_router,
)

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    """Root endpoint for API v1.

    Returns:
        A welcome message.
    """
    return {"message": "Welcome to Multando API v1"}


# Include sub-routers
router.include_router(auth_router)
router.include_router(oauth_router)
router.include_router(users_router)
router.include_router(reports_router)
router.include_router(infractions_router)
router.include_router(vehicle_types_router)
router.include_router(verification_router)
router.include_router(gamification_router)
router.include_router(blockchain_router)
router.include_router(authorities_router)
router.include_router(uploads_router)
router.include_router(wallet_router)
router.include_router(api_keys_router)
router.include_router(cities_router)
router.include_router(evidence_router)
router.include_router(admin_router)
router.include_router(authority_mgmt_router)
router.include_router(authority_review_router)
router.include_router(conversations_router)
router.include_router(webhooks_router)
router.include_router(whatsapp_router)
router.include_router(leaderboard_router)
router.include_router(widgets_router)
router.include_router(partners_router)
router.include_router(public_stats_router)
router.include_router(public_authority_router)
