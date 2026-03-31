"""Common response schemas for the Multando API.

This module contains generic response schemas used across multiple endpoints.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.schemas.base import BaseSchema

T = TypeVar("T")


class MessageResponse(BaseSchema):
    """Generic message response schema."""

    message: str
    success: bool = True


class ErrorResponse(BaseSchema):
    """Error response schema for API errors."""

    detail: str
    error_code: str | None = None


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Number of items per page"
    )


class PaginatedResponse(BaseSchema, Generic[T]):
    """Generic paginated response schema."""

    items: list[T]
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of items per page")
    pages: int = Field(description="Total number of pages")

    @classmethod
    def create(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> "PaginatedResponse[T]":
        """Create a paginated response from items and pagination info."""
        pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )
