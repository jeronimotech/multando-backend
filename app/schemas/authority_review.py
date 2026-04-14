"""Schemas for the authority review workflow.

Authorities consume the review queue to validate reports into official
comparendos. Community verification is a signal that feeds into the
``confidence_score`` — the final legal decision lives with the authority.
"""

from pydantic import Field

from app.schemas.base import BaseSchema


class AuthorityApproveRequest(BaseSchema):
    """Body for approving a report as a valid comparendo."""

    notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional free-text notes from the validating authority.",
    )


class AuthorityRejectRequest(BaseSchema):
    """Body for rejecting a report from the authority queue."""

    reason: str = Field(
        min_length=5,
        max_length=2000,
        description="Explanation shown to the reporter for the rejection.",
    )
