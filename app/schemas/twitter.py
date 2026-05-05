"""Pydantic schemas for the Apify Twitter scraping admin API."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema, TimestampSchema, UUIDSchema


class TwitterTweetStatus(str, Enum):
    """Mirror of :class:`app.models.twitter_scrape.TwitterTweetStatus`."""

    PENDING = "pending"
    EXTRACTED = "extracted"
    REPORT_CREATED = "report_created"
    DISMISSED = "dismissed"
    LOW_CONFIDENCE = "low_confidence"


# ---------------------------------------------------------------------------
# TwitterHashtag
# ---------------------------------------------------------------------------


class TwitterHashtagBase(BaseSchema):
    hashtag: str = Field(
        min_length=1,
        max_length=140,
        description="Hashtag without the '#' symbol, lowercase.",
    )
    jurisdiction_id: Optional[UUID] = Field(
        default=None,
        description="Optional jurisdiction (city) UUID. Null = global.",
    )
    enabled: bool = Field(default=True)

    @field_validator("hashtag", mode="before")
    @classmethod
    def _normalise_hashtag(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lstrip("#").strip().lower()
        return v


class TwitterHashtagCreate(TwitterHashtagBase):
    """Body for ``POST /admin/twitter/hashtags``."""


class TwitterHashtagUpdate(BaseSchema):
    """Body for ``PUT /admin/twitter/hashtags/{id}`` — every field optional."""

    hashtag: Optional[str] = Field(default=None, min_length=1, max_length=140)
    jurisdiction_id: Optional[UUID] = Field(default=None)
    enabled: Optional[bool] = Field(default=None)

    @field_validator("hashtag", mode="before")
    @classmethod
    def _normalise_hashtag(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lstrip("#").strip().lower()
        return v


class TwitterHashtagResponse(UUIDSchema, TimestampSchema):
    """Hashtag row as exposed to admins."""

    hashtag: str
    jurisdiction_id: Optional[UUID]
    enabled: bool
    last_run_at: Optional[datetime]
    last_tweet_id: Optional[str]
    total_tweets_fetched: int
    total_reports_created: int


# ---------------------------------------------------------------------------
# TwitterScrapedTweet
# ---------------------------------------------------------------------------


class TwitterScrapedTweetResponse(UUIDSchema, TimestampSchema):
    """Single scraped tweet — for admin triage views."""

    tweet_id: str
    hashtag_id: UUID
    author_handle: str
    tweet_text: str
    tweet_url: str
    media_urls: Optional[list[str]] = None
    posted_at: datetime
    confidence: Optional[float] = None
    extracted_data: Optional[dict[str, Any]] = None
    report_id: Optional[UUID] = None
    status: TwitterTweetStatus
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# TwitterScrapeRun
# ---------------------------------------------------------------------------


class TwitterScrapeRunResponse(UUIDSchema, TimestampSchema):
    """Audit-log row for one scrape execution."""

    hashtag_id: UUID
    started_at: datetime
    ended_at: Optional[datetime] = None
    tweets_fetched: int
    reports_created: int
    error_message: Optional[str] = None
    apify_run_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Action responses
# ---------------------------------------------------------------------------


class RunNowResponse(BaseSchema):
    """Returned by ``POST /admin/twitter/hashtags/{id}/run-now``."""

    hashtag_id: UUID
    task_id: Optional[str] = Field(
        default=None, description="Celery task ID if dispatched"
    )
    dispatched: bool


class ManualReportResponse(BaseSchema):
    """Returned by manual ``create-report`` / ``dismiss`` admin actions."""

    tweet_id: UUID
    status: TwitterTweetStatus
    report_id: Optional[UUID] = None
    message: str
