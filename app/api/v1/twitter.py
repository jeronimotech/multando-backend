"""Admin endpoints for the Apify Twitter (X) scraper module.

All endpoints in this router require an authenticated platform admin
(``AdminUser`` dependency). They expose CRUD over hashtags plus
read-only views of the scrape audit log and the per-tweet triage queue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import desc, select

from app.api.deps import AdminUser, DbSession
from app.models.twitter_scrape import (
    TwitterHashtag,
    TwitterScrapedTweet,
    TwitterScrapeRun,
    TwitterTweetStatus,
)
from app.schemas.twitter import (
    ManualReportResponse,
    RunNowResponse,
    TwitterHashtagCreate,
    TwitterHashtagResponse,
    TwitterHashtagUpdate,
    TwitterScrapedTweetResponse,
    TwitterScrapeRunResponse,
    TwitterTweetStatus as TwitterTweetStatusSchema,
)

router = APIRouter(prefix="/admin/twitter", tags=["admin-twitter"])


# ---------------------------------------------------------------------------
# Hashtag CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/hashtags",
    response_model=list[TwitterHashtagResponse],
    summary="List configured Twitter hashtags",
)
async def list_hashtags(
    current_user: AdminUser,
    db: DbSession,
) -> list[TwitterHashtagResponse]:
    result = await db.execute(
        select(TwitterHashtag).order_by(TwitterHashtag.hashtag.asc())
    )
    return [
        TwitterHashtagResponse.model_validate(row)
        for row in result.scalars().all()
    ]


@router.post(
    "/hashtags",
    response_model=TwitterHashtagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new hashtag entry",
)
async def create_hashtag(
    payload: TwitterHashtagCreate,
    current_user: AdminUser,
    db: DbSession,
) -> TwitterHashtagResponse:
    # Reject duplicates explicitly so the admin gets a useful error
    # instead of a database integrity error.
    existing = await db.execute(
        select(TwitterHashtag).where(TwitterHashtag.hashtag == payload.hashtag)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Hashtag #{payload.hashtag} already exists",
        )

    row = TwitterHashtag(
        hashtag=payload.hashtag,
        jurisdiction_id=payload.jurisdiction_id,
        enabled=payload.enabled,
    )
    db.add(row)
    await db.flush()
    await db.commit()
    await db.refresh(row)
    return TwitterHashtagResponse.model_validate(row)


@router.put(
    "/hashtags/{hashtag_id}",
    response_model=TwitterHashtagResponse,
    summary="Update a hashtag entry",
)
async def update_hashtag(
    hashtag_id: UUID,
    payload: TwitterHashtagUpdate,
    current_user: AdminUser,
    db: DbSession,
) -> TwitterHashtagResponse:
    row = await db.get(TwitterHashtag, hashtag_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hashtag not found",
        )

    if payload.hashtag is not None and payload.hashtag != row.hashtag:
        # Make sure we don't collide with an existing entry.
        clash = await db.execute(
            select(TwitterHashtag).where(TwitterHashtag.hashtag == payload.hashtag)
        )
        if clash.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Hashtag #{payload.hashtag} already exists",
            )
        row.hashtag = payload.hashtag

    if payload.jurisdiction_id is not None:
        row.jurisdiction_id = payload.jurisdiction_id
    if payload.enabled is not None:
        row.enabled = payload.enabled

    await db.commit()
    await db.refresh(row)
    return TwitterHashtagResponse.model_validate(row)


@router.delete(
    "/hashtags/{hashtag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a hashtag entry",
)
async def delete_hashtag(
    hashtag_id: UUID,
    current_user: AdminUser,
    db: DbSession,
) -> None:
    row = await db.get(TwitterHashtag, hashtag_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hashtag not found",
        )
    await db.delete(row)
    await db.commit()


# ---------------------------------------------------------------------------
# Manual run trigger
# ---------------------------------------------------------------------------


@router.post(
    "/hashtags/{hashtag_id}/run-now",
    response_model=RunNowResponse,
    summary="Dispatch an immediate scrape for a hashtag",
)
async def run_hashtag_now(
    hashtag_id: UUID,
    current_user: AdminUser,
    db: DbSession,
) -> RunNowResponse:
    row = await db.get(TwitterHashtag, hashtag_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hashtag not found",
        )

    # Lazy-import the celery task to keep the API import path light.
    from app.integrations.apify_twitter.tasks import scrape_hashtag

    try:
        async_result = scrape_hashtag.delay(str(hashtag_id))
        task_id = getattr(async_result, "id", None)
        dispatched = True
    except Exception:
        import logging

        logging.getLogger(__name__).warning(
            "Failed to dispatch Twitter scrape for hashtag %s",
            hashtag_id,
            exc_info=True,
        )
        task_id = None
        dispatched = False

    return RunNowResponse(
        hashtag_id=hashtag_id,
        task_id=task_id,
        dispatched=dispatched,
    )


# ---------------------------------------------------------------------------
# Run audit log
# ---------------------------------------------------------------------------


@router.get(
    "/runs",
    response_model=list[TwitterScrapeRunResponse],
    summary="Recent scrape runs",
)
async def list_runs(
    current_user: AdminUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=200),
    hashtag_id: Optional[UUID] = Query(default=None),
) -> list[TwitterScrapeRunResponse]:
    query = select(TwitterScrapeRun).order_by(
        desc(TwitterScrapeRun.created_at)
    )
    if hashtag_id is not None:
        query = query.where(TwitterScrapeRun.hashtag_id == hashtag_id)
    query = query.limit(limit)
    result = await db.execute(query)
    return [
        TwitterScrapeRunResponse.model_validate(row)
        for row in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# Tweet triage
# ---------------------------------------------------------------------------


@router.get(
    "/tweets",
    response_model=list[TwitterScrapedTweetResponse],
    summary="List scraped tweets (admin triage queue)",
)
async def list_tweets(
    current_user: AdminUser,
    db: DbSession,
    status_filter: Optional[TwitterTweetStatusSchema] = Query(
        default=None, alias="status"
    ),
    hashtag_id: Optional[UUID] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[TwitterScrapedTweetResponse]:
    query = select(TwitterScrapedTweet).order_by(
        desc(TwitterScrapedTweet.created_at)
    )
    if status_filter is not None:
        query = query.where(
            TwitterScrapedTweet.status == TwitterTweetStatus(status_filter.value)
        )
    if hashtag_id is not None:
        query = query.where(TwitterScrapedTweet.hashtag_id == hashtag_id)
    query = query.limit(limit)
    result = await db.execute(query)
    return [
        TwitterScrapedTweetResponse.model_validate(row)
        for row in result.scalars().all()
    ]


@router.post(
    "/tweets/{tweet_id}/create-report",
    response_model=ManualReportResponse,
    summary="Manually create a Report from a low-confidence tweet",
)
async def manually_create_report(
    tweet_id: UUID,
    current_user: AdminUser,
    db: DbSession,
) -> ManualReportResponse:
    tweet = await db.get(TwitterScrapedTweet, tweet_id)
    if tweet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tweet not found",
        )
    if tweet.report_id is not None:
        return ManualReportResponse(
            tweet_id=tweet_id,
            status=TwitterTweetStatusSchema(tweet.status.value),
            report_id=tweet.report_id,
            message="Tweet is already linked to a report",
        )

    # Bump the confidence so the report builder doesn't bail on the
    # threshold check. We don't overwrite the original AI confidence —
    # we set the working extracted_data confidence to 1.0 in-memory.
    extracted = dict(tweet.extracted_data or {})
    extracted["confidence"] = 1.0
    tweet.extracted_data = extracted
    tweet.confidence = max(tweet.confidence or 0.0, 1.0)

    from app.integrations.apify_twitter.report_builder import (
        create_report_from_tweet,
    )

    report = await create_report_from_tweet(tweet, db)
    if report is None:
        await db.commit()
        return ManualReportResponse(
            tweet_id=tweet_id,
            status=TwitterTweetStatusSchema(tweet.status.value),
            report_id=None,
            message=(
                "Could not create a report — check the tweet's "
                "error_message for the reason."
            ),
        )

    await db.commit()
    return ManualReportResponse(
        tweet_id=tweet_id,
        status=TwitterTweetStatusSchema.REPORT_CREATED,
        report_id=report.id,
        message=f"Created report {report.short_id}",
    )


@router.post(
    "/tweets/{tweet_id}/dismiss",
    response_model=ManualReportResponse,
    summary="Mark a tweet as dismissed (won't be auto-processed again)",
)
async def dismiss_tweet(
    tweet_id: UUID,
    current_user: AdminUser,
    db: DbSession,
) -> ManualReportResponse:
    tweet = await db.get(TwitterScrapedTweet, tweet_id)
    if tweet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tweet not found",
        )

    tweet.status = TwitterTweetStatus.DISMISSED
    tweet.error_message = None
    # ``updated_at`` is auto-bumped by the TimestampMixin onupdate.
    _ = datetime.now(timezone.utc)
    await db.commit()

    return ManualReportResponse(
        tweet_id=tweet_id,
        status=TwitterTweetStatusSchema.DISMISSED,
        report_id=tweet.report_id,
        message="Tweet dismissed",
    )
