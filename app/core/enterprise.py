"""Enterprise license checker.

Simple module that gates premium features behind a license key check.
Community edition works fully without a license key — enterprise features
simply return 403 when accessed without a valid key.

License keys use the prefix "mlt_ent_" and must be at least 20 characters.
For MVP, any non-empty key with the correct prefix and minimum length is valid.
"""

from app.core.config import settings


def is_enterprise() -> bool:
    """Check if the current instance has an active enterprise license."""
    key = settings.ENTERPRISE_LICENSE_KEY
    return bool(key and key.startswith("mlt_ent_") and len(key) >= 20)


def get_edition() -> str:
    """Return 'enterprise' or 'community'."""
    return "enterprise" if is_enterprise() else "community"


def get_enterprise_features() -> list[str]:
    """Return the list of features available in the current edition."""
    if is_enterprise():
        return [
            "analytics",
            "heatmap",
            "trends",
            "reporter_stats",
            "authority_performance",
            "white_label",
            "multi_tenant",
        ]
    return []


def require_enterprise():
    """FastAPI dependency that raises 403 if not enterprise."""
    from fastapi import HTTPException

    if not is_enterprise():
        raise HTTPException(
            status_code=403,
            detail={
                "error": "enterprise_required",
                "message": (
                    "This feature requires an enterprise license. "
                    "Visit multando.com/enterprise for details."
                ),
                "edition": "community",
            },
        )
