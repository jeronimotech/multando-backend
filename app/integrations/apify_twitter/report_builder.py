"""Convert an extracted ``TwitterScrapedTweet`` into a ``Report`` row.

The Apify scraper persists every tweet it sees in ``twitter_scraped_tweets``.
For each tweet that cleared the confidence threshold this module:

1. Looks up the matching :class:`Infraction` row by ``code`` (with a
   sensible default when the code isn't recognised).
2. Resolves a Twitter "bot" :class:`User` to act as the (anonymous-from
   the citizen's perspective) reporter — using a real user keeps the
   ``Report.reporter_id`` non-null FK happy and lets admins audit / dial
   back access for the bot.
3. Downloads each ``media_url`` to S3 using the existing
   :class:`MediaService` static helper.
4. Inserts a :class:`Report` row with ``source=ReportSource.TWITTER`` and
   ``status=ReportStatus.PENDING`` and links it back via
   ``TwitterScrapedTweet.report_id``.

If extraction confidence is below
``settings.APIFY_MIN_CONFIDENCE_THRESHOLD`` the tweet is left in
``low_confidence`` state for admin triage and ``None`` is returned.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import (
    EvidenceType,
    ReportSource,
    ReportStatus,
    UserRole,
    VehicleCategory,
)
from app.models.report import Evidence, Infraction, Report
from app.models.twitter_scrape import TwitterScrapedTweet, TwitterTweetStatus
from app.models.user import User
from app.services.whatsapp.media import MediaService

logger = logging.getLogger(__name__)


# ``Report.reporter_id`` is non-null. To represent "anonymous from
# Twitter" we get-or-create a single platform user with a stable email
# and CITIZEN role. Admins can disable / repoint this user via the DB.
_TWITTER_BOT_EMAIL = "twitter-bot@multando.internal"
_TWITTER_BOT_USERNAME = "twitter-bot"
_TWITTER_BOT_DISPLAY_NAME = "Twitter Scraper"


def _generate_short_id() -> str:
    """Generate a short ID like ``RPT-A1B2C3`` (mirrors ReportService)."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"RPT-{suffix}"


async def _get_or_create_twitter_bot_user(db: AsyncSession) -> User:
    """Resolve the Twitter scraper system user, creating it if missing."""
    result = await db.execute(
        select(User).where(User.email == _TWITTER_BOT_EMAIL)
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        email=_TWITTER_BOT_EMAIL,
        username=_TWITTER_BOT_USERNAME,
        display_name=_TWITTER_BOT_DISPLAY_NAME,
        role=UserRole.CITIZEN,
        is_active=True,
        is_verified=False,
        auth_provider="system",
    )
    db.add(user)
    await db.flush()
    logger.info("Created Twitter scraper system user id=%s", user.id)
    return user


async def _resolve_infraction(
    db: AsyncSession, code: Optional[str]
) -> Optional[Infraction]:
    """Look up an :class:`Infraction` row by code (case-insensitive).

    Falls back to ``None`` if neither the requested code nor a generic
    "other" infraction can be found — the caller should leave the tweet
    in ``EXTRACTED`` state for admin review.
    """
    candidates: list[str] = []
    if code:
        candidates.append(code)
        candidates.append(code.lower())
    # Generic fallbacks the project may have seeded.
    candidates.extend(
        [
            "other",
            "illegal_parking",
            "OTHER",
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        result = await db.execute(
            select(Infraction).where(Infraction.code == candidate)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row
    return None


async def _download_media(url: str) -> Optional[tuple[bytes, str]]:
    """Download a media URL, returning ``(bytes, content_type)`` or None."""
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", "image/jpeg")
    except httpx.HTTPError as exc:
        logger.warning("Failed to download Twitter media %s: %s", url, exc)
        return None


async def create_report_from_tweet(
    tweet: TwitterScrapedTweet,
    db: AsyncSession,
) -> Optional[Report]:
    """Convert an extracted tweet into a pending :class:`Report`.

    Returns ``None`` (and updates the tweet status) when:

    - extraction confidence is below the configured threshold,
    - the corresponding :class:`Infraction` cannot be resolved,
    - the tweet has already been linked to a report.

    Side effects:
        - Inserts a Report (and Evidence rows for downloaded media).
        - Updates the tweet's ``status`` and ``report_id`` columns.
        - Does **not** call :meth:`session.commit()` — the caller (the
          Celery task) owns the transaction.
    """
    if tweet.report_id is not None:
        logger.debug("Tweet %s already linked to report", tweet.tweet_id)
        return None

    extracted = tweet.extracted_data or {}
    confidence = tweet.confidence or 0.0
    threshold = float(settings.APIFY_MIN_CONFIDENCE_THRESHOLD)

    if confidence < threshold:
        tweet.status = TwitterTweetStatus.LOW_CONFIDENCE
        return None

    # 1. Resolve the infraction row.
    infraction = await _resolve_infraction(
        db, extracted.get("infraction_code")
    )
    if infraction is None:
        logger.warning(
            "No matching Infraction for tweet %s (code=%r) — leaving for "
            "admin review.",
            tweet.tweet_id,
            extracted.get("infraction_code"),
        )
        tweet.status = TwitterTweetStatus.EXTRACTED
        tweet.error_message = (
            f"No infraction row for code={extracted.get('infraction_code')!r}"
        )
        return None

    # 2. Resolve the bot user.
    bot_user = await _get_or_create_twitter_bot_user(db)

    # 3. Build the Report row.
    short_id = _generate_short_id()
    # Avoid collisions on the unique short_id.
    existing = await db.execute(
        select(Report).where(Report.short_id == short_id)
    )
    while existing.scalar_one_or_none() is not None:
        short_id = _generate_short_id()
        existing = await db.execute(
            select(Report).where(Report.short_id == short_id)
        )

    incident_dt = tweet.posted_at or datetime.now(timezone.utc)
    lat = extracted.get("latitude")
    lon = extracted.get("longitude")
    # Fallback when GPS isn't in the tweet — use 0,0 so the row passes
    # the non-null Float check. Admins triage these in the UI by
    # filtering "missing coordinates".
    if lat is None or lon is None:
        lat, lon = 0.0, 0.0

    description_lines = [
        f"Auto-imported from Twitter (@{tweet.author_handle}).",
        f"Tweet: {tweet.tweet_url}",
    ]
    if extracted.get("location_text"):
        description_lines.append(f"Reported location: {extracted['location_text']}")
    if extracted.get("reasoning"):
        description_lines.append(f"AI rationale: {extracted['reasoning']}")
    rejection_or_notes = "\n".join(description_lines)

    report = Report(
        short_id=short_id,
        reporter_id=bot_user.id,
        source=ReportSource.TWITTER,
        infraction_id=infraction.id,
        vehicle_plate=extracted.get("plate"),
        vehicle_category=VehicleCategory.PRIVATE,
        latitude=float(lat),
        longitude=float(lon),
        location_address=extracted.get("location_text"),
        location_country="CO",
        incident_datetime=incident_dt,
        status=ReportStatus.PENDING,
        # Stash the AI rationale and tweet provenance in
        # ``confidence_factors`` (a JSONB column) — keeps the audit
        # trail without needing a fresh column on ``reports``.
        confidence_score=int(round(confidence * 100)),
        confidence_factors={
            "source": "twitter",
            "tweet_id": tweet.tweet_id,
            "tweet_url": tweet.tweet_url,
            "author_handle": tweet.author_handle,
            "ai_confidence": confidence,
            "ai_reasoning": extracted.get("reasoning"),
            "extracted_data": extracted,
            "notes": rejection_or_notes,
        },
    )
    db.add(report)
    await db.flush()

    # 4. Download evidence and insert Evidence rows.
    media_urls: list[str] = list(tweet.media_urls or [])
    for idx, media_url in enumerate(media_urls[:4]):  # cap at 4 like Twitter
        downloaded = await _download_media(media_url)
        if downloaded is None:
            continue
        data_bytes, content_type = downloaded
        # Normalize content-type (Twitter sometimes sends ``image/jpeg`` for
        # GIFs; we don't try to be clever).
        if not content_type.startswith("image/") and not content_type.startswith(
            "video/"
        ):
            content_type = "image/jpeg"

        ext = content_type.split("/")[-1].split(";")[0]
        s3_key = f"evidence/twitter/{report.id}/{idx:02d}.{ext}"
        try:
            url = await MediaService.upload_evidence(
                s3_key, data_bytes, content_type
            )
        except Exception:
            logger.warning(
                "Failed to upload Twitter evidence to S3 for tweet %s",
                tweet.tweet_id,
                exc_info=True,
            )
            continue

        evidence = Evidence(
            report_id=report.id,
            type=(
                EvidenceType.VIDEO
                if content_type.startswith("video/")
                else EvidenceType.IMAGE
            ),
            url=url,
            mime_type=content_type,
            file_size=len(data_bytes),
        )
        db.add(evidence)

    # 5. Wire the tweet → report link.
    tweet.report_id = report.id
    tweet.status = TwitterTweetStatus.REPORT_CREATED
    tweet.error_message = None
    await db.flush()

    logger.info(
        "Created report %s from tweet %s (confidence=%.2f)",
        short_id,
        tweet.tweet_id,
        confidence,
    )
    return report
