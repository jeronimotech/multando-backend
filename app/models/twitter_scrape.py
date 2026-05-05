"""Models for Apify-based Twitter (X) hashtag scraping.

Three tables work together to ingest tweets matching admin-configured
hashtags, run AI-driven infraction extraction, and (optionally)
auto-create pending Reports for community voting:

- :class:`TwitterHashtag` — admin-managed list of hashtags to monitor.
- :class:`TwitterScrapedTweet` — every tweet observed via Apify, with
  Claude-extracted infraction data and a link to the auto-created Report
  if confidence cleared the threshold.
- :class:`TwitterScrapeRun` — audit log of each scheduled scrape, one row
  per ``(hashtag, run)``.

Conventions follow ``app/models/sdm_submission.py`` and
``app/models/record_submission.py`` (UUID PKs, ``Mapped[]`` syntax,
``TimestampMixin``).
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TwitterTweetStatus(str, enum.Enum):
    """Lifecycle status for a scraped tweet."""

    PENDING = "pending"  # newly inserted, not yet extracted
    EXTRACTED = "extracted"  # Claude returned data but not yet a report
    REPORT_CREATED = "report_created"  # auto-created a Report
    DISMISSED = "dismissed"  # admin marked as not actionable
    LOW_CONFIDENCE = "low_confidence"  # extraction below threshold


class TwitterHashtag(TimestampMixin, Base):
    """Admin-managed hashtag to scrape on a schedule.

    ``jurisdiction_id`` is a soft reference to the ``cities`` table
    (which acts as the jurisdiction primitive in this codebase). It is
    nullable — null means the hashtag is global and reports created
    from its tweets will be assigned a city by GPS-resolution at report
    creation time.
    """

    __tablename__ = "twitter_hashtags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    hashtag: Mapped[str] = mapped_column(
        String(140),
        unique=True,
        nullable=False,
        index=True,
    )
    # Kept as UUID per spec; stored as a soft reference (no hard FK) so
    # ops can repoint to a future ``jurisdictions`` table without a
    # migration on this row.
    jurisdiction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    last_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_tweet_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )

    total_tweets_fetched: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    total_reports_created: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Relationships
    tweets: Mapped[list["TwitterScrapedTweet"]] = relationship(
        "TwitterScrapedTweet",
        back_populates="hashtag",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["TwitterScrapeRun"]] = relationship(
        "TwitterScrapeRun",
        back_populates="hashtag",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TwitterHashtag #{self.hashtag} enabled={self.enabled}>"


class TwitterScrapedTweet(TimestampMixin, Base):
    """A single tweet returned by Apify for one of our tracked hashtags."""

    __tablename__ = "twitter_scraped_tweets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    tweet_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )

    hashtag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("twitter_hashtags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    author_handle: Mapped[str] = mapped_column(String(100), nullable=False)
    tweet_text: Mapped[str] = mapped_column(Text, nullable=False)
    tweet_url: Mapped[str] = mapped_column(String(500), nullable=False)

    media_urls: Mapped[Optional[list]] = mapped_column(
        JSONB, nullable=True
    )

    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    raw_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )

    confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    extracted_data: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )

    report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[TwitterTweetStatus] = mapped_column(
        Enum(TwitterTweetStatus, native_enum=False, length=20),
        default=TwitterTweetStatus.PENDING,
        nullable=False,
        index=True,
    )

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    hashtag: Mapped["TwitterHashtag"] = relationship(
        "TwitterHashtag", back_populates="tweets"
    )
    report = relationship("Report", foreign_keys=[report_id])

    def __repr__(self) -> str:
        return (
            f"<TwitterScrapedTweet id={self.tweet_id} "
            f"status={self.status.value if hasattr(self.status, 'value') else self.status}>"
        )


class TwitterScrapeRun(TimestampMixin, Base):
    """One execution of the periodic scrape for a single hashtag."""

    __tablename__ = "twitter_scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    hashtag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("twitter_hashtags.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tweets_fetched: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    reports_created: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    apify_run_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    # Relationships
    hashtag: Mapped["TwitterHashtag"] = relationship(
        "TwitterHashtag", back_populates="runs"
    )

    def __repr__(self) -> str:
        return (
            f"<TwitterScrapeRun hashtag_id={self.hashtag_id} "
            f"fetched={self.tweets_fetched} created={self.reports_created}>"
        )
