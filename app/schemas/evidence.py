"""Evidence schemas for the Multando API.

This module contains schemas for evidence files attached to reports.
"""

from datetime import datetime
from enum import Enum

from pydantic import Field

from app.schemas.base import BaseSchema


class EvidenceType(str, Enum):
    """Evidence type categories."""

    IMAGE = "image"
    VIDEO = "video"


class EvidenceBase(BaseSchema):
    """Base schema for evidence data."""

    type: EvidenceType = Field(description="Type of evidence (image/video)")
    url: str = Field(description="URL to the evidence file")
    thumbnail_url: str | None = Field(
        default=None, description="URL to thumbnail image"
    )
    mime_type: str = Field(description="MIME type of the evidence file")


class EvidenceCreate(BaseSchema):
    """Schema for creating evidence (used with file upload)."""

    type: EvidenceType = Field(description="Type of evidence (image/video)")
    # Note: The actual file will be processed separately via multipart form


class EvidenceResponse(EvidenceBase):
    """Schema for evidence response."""

    id: int = Field(description="Evidence unique identifier")
    ipfs_hash: str | None = Field(
        default=None, description="IPFS hash for decentralized storage"
    )
    created_at: datetime = Field(description="When the evidence was uploaded")


class EvidenceUploadResponse(BaseSchema):
    """Schema for evidence upload response."""

    id: int = Field(description="Evidence unique identifier")
    url: str = Field(description="URL to the uploaded evidence")
    thumbnail_url: str | None = Field(
        default=None, description="URL to thumbnail image"
    )
    ipfs_hash: str | None = Field(
        default=None, description="IPFS hash for decentralized storage"
    )
