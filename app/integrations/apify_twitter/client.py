"""Async HTTP client for the Apify Twitter (X) scraper actor.

Uses the public Apify v2 REST API with bearer-token auth. The default
actor is ``apidojo/tweet-scraper`` (configurable via
``settings.APIFY_TWITTER_ACTOR_ID``) which accepts a list of search
terms (``searchTerms``) and a ``maxItems`` cap.

The :meth:`ApifyTwitterClient.start_scrape_run` method launches a new
actor run; :meth:`get_run_results` polls the run until it finishes
(or fails) and returns the dataset items.

Reference:
    https://docs.apify.com/api/v2#/reference/actors/run-collection
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class ApifyClientError(Exception):
    """Raised when the Apify API rejects a request or a run fails."""


class ApifyTwitterClient:
    """Thin async wrapper over the Apify v2 actor-runs API."""

    BASE_URL = "https://api.apify.com/v2"

    # Total time budget for a single hashtag scrape (covers both starting
    # the run and polling for results).
    TOTAL_TIMEOUT_SECONDS = 5 * 60
    POLL_INTERVAL_SECONDS = 5.0

    # Statuses returned by the Apify run lifecycle.
    _TERMINAL_OK = {"SUCCEEDED"}
    _TERMINAL_FAIL = {"FAILED", "ABORTED", "TIMED-OUT"}

    def __init__(
        self,
        api_token: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> None:
        self.api_token = api_token or settings.APIFY_API_TOKEN
        self.actor_id = actor_id or settings.APIFY_TWITTER_ACTOR_ID

        if not self.api_token:
            logger.warning(
                "Apify API token is not configured — calls will fail "
                "until APIFY_API_TOKEN is set."
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_scrape_run(
        self,
        hashtag: str,
        max_tweets: int,
        since_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Launch a new Apify actor run for the given hashtag.

        Args:
            hashtag: Hashtag to search for, **without** the leading ``#``.
            max_tweets: Cap on the number of tweets to fetch.
            since_id: Optional Twitter ``id_str`` of the most recent tweet
                we've already ingested. The actor doesn't always honor
                this directly, so we pass it in ``startUrls``-style query
                hints when possible. Tweets older than this are filtered
                client-side after the run completes.

        Returns:
            The Apify ``run`` dict (contains ``id``, ``status``, etc.).

        Raises:
            ApifyClientError: On HTTP failure or invalid response.
        """
        # apidojo/tweet-scraper accepts ``searchTerms``: list[str]
        # The hashtag must include the ``#`` prefix in the search term.
        search_term = f"#{hashtag.lstrip('#')}"

        payload: dict[str, Any] = {
            "searchTerms": [search_term],
            "maxItems": max_tweets,
            "tweetLanguage": "es",
            "sort": "Latest",
            "includeSearchTerms": True,
        }
        if since_id:
            # Hint to the actor — many community Twitter actors honor
            # the ``sinceId`` field; safe to include even if ignored.
            payload["sinceId"] = since_id

        url = f"{self.BASE_URL}/acts/{self._encoded_actor_id()}/runs"
        params = {"token": self.api_token}

        logger.info(
            "Apify: starting scrape run actor=%s hashtag=%s max=%d",
            self.actor_id,
            hashtag,
            max_tweets,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, params=params, json=payload)
        except httpx.HTTPError as exc:
            raise ApifyClientError(
                f"Failed to start Apify run for #{hashtag}: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise ApifyClientError(
                f"Apify start-run returned HTTP {resp.status_code}: "
                f"{resp.text[:300]}"
            )

        body = resp.json()
        run = body.get("data") or body
        if not isinstance(run, dict) or "id" not in run:
            raise ApifyClientError(
                f"Apify start-run returned unexpected payload: {body}"
            )

        logger.info(
            "Apify: run started run_id=%s status=%s",
            run.get("id"),
            run.get("status"),
        )
        return run

    async def get_run_results(self, run_id: str) -> list[dict[str, Any]]:
        """Poll the run until it terminates, then fetch dataset items.

        Args:
            run_id: The run ID returned by :meth:`start_scrape_run`.

        Returns:
            List of tweet dicts (the actor's dataset items).

        Raises:
            ApifyClientError: If the run fails, aborts, or exceeds the
                module-level timeout.
        """
        deadline = asyncio.get_event_loop().time() + self.TOTAL_TIMEOUT_SECONDS

        run_status = await self._poll_until_finished(run_id, deadline)

        if run_status in self._TERMINAL_FAIL:
            raise ApifyClientError(
                f"Apify run {run_id} ended with status={run_status}"
            )

        return await self._fetch_dataset_items(run_id)

    async def scrape_hashtag(
        self,
        hashtag: str,
        max_tweets: int,
        since_id: Optional[str] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Convenience wrapper: start a run and return ``(run_id, items)``."""
        run = await self.start_scrape_run(
            hashtag=hashtag, max_tweets=max_tweets, since_id=since_id
        )
        run_id = run["id"]
        items = await self.get_run_results(run_id)
        return run_id, items

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _encoded_actor_id(self) -> str:
        """Apify actor IDs use ``user/actor`` slug — encode the slash."""
        return quote(self.actor_id, safe="")

    async def _poll_until_finished(
        self, run_id: str, deadline: float
    ) -> str:
        """Poll ``/v2/actor-runs/{id}`` until status is terminal."""
        url = f"{self.BASE_URL}/actor-runs/{run_id}"
        params = {"token": self.api_token}

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                if asyncio.get_event_loop().time() > deadline:
                    raise ApifyClientError(
                        f"Apify run {run_id} did not finish before "
                        f"{self.TOTAL_TIMEOUT_SECONDS}s timeout"
                    )

                try:
                    resp = await client.get(url, params=params)
                except httpx.HTTPError as exc:
                    raise ApifyClientError(
                        f"Failed to poll Apify run {run_id}: {exc}"
                    ) from exc

                if resp.status_code >= 400:
                    raise ApifyClientError(
                        f"Apify poll returned HTTP {resp.status_code}: "
                        f"{resp.text[:300]}"
                    )

                run = (resp.json() or {}).get("data") or {}
                status = (run.get("status") or "").upper()

                if status in self._TERMINAL_OK:
                    logger.info(
                        "Apify run %s succeeded (items expected in dataset)",
                        run_id,
                    )
                    return status
                if status in self._TERMINAL_FAIL:
                    logger.warning(
                        "Apify run %s ended with status=%s", run_id, status
                    )
                    return status

                logger.debug(
                    "Apify run %s status=%s — sleeping %.1fs",
                    run_id,
                    status,
                    self.POLL_INTERVAL_SECONDS,
                )
                await asyncio.sleep(self.POLL_INTERVAL_SECONDS)

    async def _fetch_dataset_items(
        self, run_id: str
    ) -> list[dict[str, Any]]:
        """Fetch the items produced by a finished run."""
        url = f"{self.BASE_URL}/actor-runs/{run_id}/dataset/items"
        params = {"token": self.api_token, "format": "json", "clean": "true"}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise ApifyClientError(
                f"Failed to fetch dataset for run {run_id}: {exc}"
            ) from exc

        if resp.status_code >= 400:
            raise ApifyClientError(
                f"Apify dataset fetch returned HTTP {resp.status_code}: "
                f"{resp.text[:300]}"
            )

        items = resp.json()
        if not isinstance(items, list):
            raise ApifyClientError(
                f"Apify dataset response was not a list: {type(items)}"
            )

        logger.info(
            "Apify run %s returned %d dataset items", run_id, len(items)
        )
        return items
