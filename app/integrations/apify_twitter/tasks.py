"""Celery tasks for the Apify-based Twitter (X) hashtag scraper.

The beat-scheduled :func:`scrape_all_hashtags` enumerates enabled
``TwitterHashtag`` rows and dispatches a :func:`scrape_hashtag` task for
each. The per-hashtag task:

1. Inserts a ``TwitterScrapeRun`` row with ``started_at=now``.
2. Calls Apify (via :class:`ApifyTwitterClient`) to fetch up to
   ``settings.APIFY_MAX_TWEETS_PER_RUN`` tweets newer than the last
   ingested ID.
3. For each new tweet: persists a ``TwitterScrapedTweet`` row, asks
   Claude to extract structured infraction data, and (if confidence
   clears the threshold and ``APIFY_AUTO_CREATE_REPORTS`` is on) calls
   the report builder to mint a ``Report``.
4. Updates the hashtag counters and the run row's ``ended_at`` /
   ``tweets_fetched`` / ``reports_created``.

Async↔sync bridging follows the same idiom as ``record_task.py`` /
``sdm_task.py``: a small ``_run_async`` helper.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery import celery_app
from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# async/sync bridge
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Apify item normalisation
# ---------------------------------------------------------------------------


def _coerce_tweet_id(item: dict[str, Any]) -> Optional[str]:
    """Pick the ``id_str`` (or numeric ``id``) out of an Apify item."""
    for key in ("id_str", "tweetId", "id", "rest_id"):
        v = item.get(key)
        if isinstance(v, (str, int)) and str(v):
            return str(v)
    return None


def _coerce_author(item: dict[str, Any]) -> str:
    """Resolve the ``screen_name`` of the tweet author."""
    user = item.get("user") or item.get("author") or {}
    if isinstance(user, dict):
        for key in ("screen_name", "screenName", "username", "handle"):
            v = user.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip().lstrip("@")
    handle = item.get("authorHandle") or item.get("username")
    if isinstance(handle, str):
        return handle.strip().lstrip("@")
    return "unknown"


def _coerce_text(item: dict[str, Any]) -> str:
    for key in ("full_text", "text", "fullText"):
        v = item.get(key)
        if isinstance(v, str):
            return v
    return ""


def _coerce_url(item: dict[str, Any], author: str, tweet_id: str) -> str:
    for key in ("url", "tweetUrl", "permalink"):
        v = item.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    return f"https://twitter.com/{author}/status/{tweet_id}"


def _coerce_posted_at(item: dict[str, Any]) -> datetime:
    """Twitter timestamps come in many flavours — try them all."""
    for key in ("created_at", "createdAt", "posted_at", "date"):
        v = item.get(key)
        if not v:
            continue
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, str):
            # ISO 8601
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                pass
            # Twitter's classic format: "Mon Jan 02 15:04:05 +0000 2006"
            try:
                return datetime.strptime(
                    v, "%a %b %d %H:%M:%S %z %Y"
                )
            except ValueError:
                pass
    return datetime.now(timezone.utc)


def _coerce_media_urls(item: dict[str, Any]) -> list[str]:
    """Same logic as the extractor module — kept here to avoid an import cycle."""
    urls: list[str] = []
    media = item.get("media") or item.get("entities", {}).get("media") or []
    for m in media:
        if not isinstance(m, dict):
            continue
        for k in ("media_url_https", "media_url", "url", "expanded_url"):
            v = m.get(k)
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
                break
    flat = item.get("mediaUrls")
    if isinstance(flat, list):
        for v in flat:
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ---------------------------------------------------------------------------
# Async core
# ---------------------------------------------------------------------------


async def _scrape_hashtag_async(hashtag_id: str) -> dict[str, Any]:
    """Async implementation of :func:`scrape_hashtag`."""
    from app.core.database import async_session_factory
    from app.integrations.apify_twitter.client import (
        ApifyClientError,
        ApifyTwitterClient,
    )
    from app.integrations.apify_twitter.extractor import (
        extract_infraction_data,
    )
    from app.integrations.apify_twitter.report_builder import (
        create_report_from_tweet,
    )
    from app.models.twitter_scrape import (
        TwitterHashtag,
        TwitterScrapedTweet,
        TwitterScrapeRun,
        TwitterTweetStatus,
    )

    started_at = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        # Hashtag lookup ---------------------------------------------------
        hashtag = await session.get(TwitterHashtag, UUID(hashtag_id))
        if hashtag is None:
            logger.error("Hashtag %s not found", hashtag_id)
            return {"success": False, "error": "Hashtag not found"}
        if not hashtag.enabled:
            logger.info("Hashtag #%s disabled — skipping", hashtag.hashtag)
            return {"success": False, "skipped": True, "reason": "Disabled"}

        # Run row ----------------------------------------------------------
        run = TwitterScrapeRun(
            hashtag_id=hashtag.id,
            started_at=started_at,
        )
        session.add(run)
        await session.flush()

        # Fetch from Apify -------------------------------------------------
        client = ApifyTwitterClient()
        try:
            apify_run_id, items = await client.scrape_hashtag(
                hashtag=hashtag.hashtag,
                max_tweets=settings.APIFY_MAX_TWEETS_PER_RUN,
                since_id=hashtag.last_tweet_id,
            )
        except ApifyClientError as exc:
            logger.warning(
                "Apify scrape failed for #%s: %s", hashtag.hashtag, exc
            )
            run.error_message = str(exc)[:500]
            run.ended_at = datetime.now(timezone.utc)
            await session.commit()
            return {"success": False, "error": str(exc)}

        run.apify_run_id = apify_run_id
        run.tweets_fetched = len(items)

        # Per-tweet processing --------------------------------------------
        new_count, reports_created = await _ingest_items(
            session=session,
            hashtag=hashtag,
            items=items,
            extract_fn=extract_infraction_data,
            create_report_fn=create_report_from_tweet,
        )

        # Hashtag counters / cursor ---------------------------------------
        hashtag.last_run_at = datetime.now(timezone.utc)
        hashtag.total_tweets_fetched = (
            (hashtag.total_tweets_fetched or 0) + new_count
        )
        hashtag.total_reports_created = (
            (hashtag.total_reports_created or 0) + reports_created
        )
        # Update cursor to the newest tweet id we just saw.
        if items:
            newest_id = max(
                (
                    _coerce_tweet_id(it)
                    for it in items
                    if _coerce_tweet_id(it)
                ),
                key=lambda s: int(s) if s and s.isdigit() else 0,
                default=None,
            )
            if newest_id and newest_id != hashtag.last_tweet_id:
                hashtag.last_tweet_id = newest_id

        # Run row finalisation
        run.reports_created = reports_created
        run.tweets_fetched = new_count or len(items)
        run.ended_at = datetime.now(timezone.utc)

        await session.commit()

        logger.info(
            "Twitter scrape #%s — fetched=%d new=%d reports=%d",
            hashtag.hashtag,
            len(items),
            new_count,
            reports_created,
        )
        return {
            "success": True,
            "hashtag": hashtag.hashtag,
            "fetched": len(items),
            "new_tweets": new_count,
            "reports_created": reports_created,
            "apify_run_id": apify_run_id,
        }


async def _ingest_items(
    session: AsyncSession,
    hashtag: Any,
    items: list[dict[str, Any]],
    extract_fn,
    create_report_fn,
) -> tuple[int, int]:
    """Persist new tweets, run extraction, optionally create reports.

    Returns ``(new_tweet_count, reports_created)``.
    """
    from app.models.twitter_scrape import (
        TwitterScrapedTweet,
        TwitterTweetStatus,
    )

    new_count = 0
    reports_created = 0

    for raw in items:
        tweet_id = _coerce_tweet_id(raw)
        if not tweet_id:
            continue

        # Skip if we've already ingested this tweet.
        existing = await session.execute(
            select(TwitterScrapedTweet).where(
                TwitterScrapedTweet.tweet_id == tweet_id
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        author = _coerce_author(raw)
        text = _coerce_text(raw)
        tweet_url = _coerce_url(raw, author, tweet_id)
        posted_at = _coerce_posted_at(raw)
        media_urls = _coerce_media_urls(raw)

        tweet_row = TwitterScrapedTweet(
            tweet_id=tweet_id,
            hashtag_id=hashtag.id,
            author_handle=author,
            tweet_text=text,
            tweet_url=tweet_url,
            media_urls=media_urls or None,
            posted_at=posted_at,
            raw_data=raw,
            status=TwitterTweetStatus.PENDING,
        )
        session.add(tweet_row)
        await session.flush()
        new_count += 1

        # Extraction ----------------------------------------------------
        try:
            extracted = await extract_fn(raw)
        except Exception as exc:  # never bring down the whole run
            logger.warning(
                "Claude extraction failed for tweet %s: %s",
                tweet_id,
                exc,
                exc_info=True,
            )
            tweet_row.status = TwitterTweetStatus.PENDING
            tweet_row.error_message = f"Extraction error: {exc}"[:500]
            continue

        tweet_row.confidence = extracted.get("confidence")
        tweet_row.extracted_data = extracted
        tweet_row.status = TwitterTweetStatus.EXTRACTED

        # Auto-create reports? -----------------------------------------
        if not settings.APIFY_AUTO_CREATE_REPORTS:
            # Just stamp the status and move on; admin will triage.
            continue

        try:
            report = await create_report_fn(tweet_row, session)
        except Exception as exc:
            logger.warning(
                "Report builder failed for tweet %s: %s",
                tweet_id,
                exc,
                exc_info=True,
            )
            tweet_row.error_message = (
                f"Report builder error: {exc}"
            )[:500]
            continue

        if report is not None:
            reports_created += 1

    return new_count, reports_created


# ---------------------------------------------------------------------------
# Celery task surface
# ---------------------------------------------------------------------------


@celery_app.task(name="app.integrations.apify_twitter.scrape_all_hashtags")
def scrape_all_hashtags() -> dict[str, Any]:
    """Beat-scheduled fan-out task — dispatch one task per enabled hashtag."""
    if not settings.APIFY_ENABLED:
        return {"dispatched": 0, "reason": "APIFY_ENABLED is false"}

    async def _list_enabled() -> list[str]:
        from app.core.database import async_session_factory
        from app.models.twitter_scrape import TwitterHashtag

        async with async_session_factory() as session:
            result = await session.execute(
                select(TwitterHashtag.id).where(
                    TwitterHashtag.enabled.is_(True)
                )
            )
            return [str(row[0]) for row in result.all()]

    ids = _run_async(_list_enabled())
    for hid in ids:
        scrape_hashtag.delay(hid)

    logger.info("Twitter scraper: dispatched %d hashtag tasks", len(ids))
    return {"dispatched": len(ids), "hashtag_ids": ids}


@celery_app.task(
    name="app.integrations.apify_twitter.scrape_hashtag",
    bind=True,
    max_retries=3,
    acks_late=True,
)
def scrape_hashtag(self: Task, hashtag_id: str) -> dict[str, Any]:
    """Scrape a single hashtag — see module docstring for the full flow."""
    if not settings.APIFY_ENABLED:
        return {"success": False, "skipped": True, "reason": "APIFY disabled"}

    try:
        return _run_async(_scrape_hashtag_async(hashtag_id))
    except Exception as exc:
        backoff = 60 * (2 ** self.request.retries)
        logger.warning(
            "scrape_hashtag(%s) failed (attempt %d/%d), retrying in %ds: %s",
            hashtag_id,
            self.request.retries + 1,
            self.max_retries + 1,
            backoff,
            exc,
        )
        try:
            raise self.retry(exc=exc, countdown=backoff)
        except self.MaxRetriesExceededError:
            logger.error(
                "scrape_hashtag(%s) exhausted retries", hashtag_id
            )
            return {"success": False, "error": str(exc)}
