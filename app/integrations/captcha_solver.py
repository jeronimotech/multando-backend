"""2captcha API client for solving reCAPTCHA v2 challenges."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class CaptchaSolveError(Exception):
    """Raised when captcha solving fails."""

    def __init__(self, message: str, error_code: str | None = None):
        self.error_code = error_code
        super().__init__(message)


class CaptchaSolver:
    """Solves reCAPTCHA v2 using 2captcha service.

    Usage:
        solver = CaptchaSolver(api_key="your-2captcha-api-key")
        token = await solver.solve_recaptcha(
            site_key="6Le3HF...",
            page_url="https://example.com/form",
        )
    """

    API_URL = "http://2captcha.com/in.php"
    RESULT_URL = "http://2captcha.com/res.php"
    POLL_INTERVAL = 5  # seconds between polling attempts

    # Fatal errors that should not be retried
    FATAL_ERRORS = frozenset({
        "ERROR_WRONG_USER_KEY",
        "ERROR_KEY_DOES_NOT_EXIST",
        "ERROR_ZERO_BALANCE",
        "ERROR_PAGEURL",
        "ERROR_GOOGLEKEY",
        "IP_BANNED",
    })

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def solve_recaptcha(
        self,
        site_key: str,
        page_url: str,
        timeout: int = 120,
    ) -> str:
        """Solve a reCAPTCHA v2 challenge.

        Args:
            site_key: The reCAPTCHA site key from the page.
            page_url: The URL of the page with the captcha.
            timeout: Max seconds to wait for solution.

        Returns:
            The solved reCAPTCHA token string.

        Raises:
            CaptchaSolveError: If solving fails or times out.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            task_id = await self._create_task(client, site_key, page_url)
            return await self._poll_result(client, task_id, timeout)

    async def _create_task(
        self,
        client: httpx.AsyncClient,
        site_key: str,
        page_url: str,
    ) -> str:
        """Submit a captcha solve request and return the task ID."""
        logger.info("Submitting reCAPTCHA solve request to 2captcha")

        try:
            response = await client.post(
                self.API_URL,
                data={
                    "key": self.api_key,
                    "method": "userrecaptcha",
                    "googlekey": site_key,
                    "pageurl": page_url,
                    "json": "1",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CaptchaSolveError(
                f"HTTP error submitting captcha task: {exc}"
            ) from exc

        data = response.json()

        if data.get("status") != 1:
            error_text = data.get("request", "UNKNOWN_ERROR")
            raise CaptchaSolveError(
                f"2captcha rejected the task: {error_text}",
                error_code=error_text,
            )

        task_id = data["request"]
        logger.info("2captcha task created: %s", task_id)
        return task_id

    async def _poll_result(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        timeout: int,
    ) -> str:
        """Poll 2captcha for the solved token until ready or timeout."""
        elapsed = 0

        # Initial wait — 2captcha recommends waiting at least 15s before first poll
        initial_wait = min(15, timeout)
        await asyncio.sleep(initial_wait)
        elapsed += initial_wait

        while elapsed < timeout:
            try:
                response = await client.get(
                    self.RESULT_URL,
                    params={
                        "key": self.api_key,
                        "action": "get",
                        "id": task_id,
                        "json": "1",
                    },
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("HTTP error polling captcha result: %s", exc)
                await asyncio.sleep(self.POLL_INTERVAL)
                elapsed += self.POLL_INTERVAL
                continue

            data = response.json()

            if data.get("status") == 1:
                token = data["request"]
                logger.info("reCAPTCHA solved successfully (task %s)", task_id)
                return token

            error_text = data.get("request", "")

            if error_text == "CAPCHA_NOT_READY":
                logger.debug("Captcha not ready yet, polling again...")
                await asyncio.sleep(self.POLL_INTERVAL)
                elapsed += self.POLL_INTERVAL
                continue

            if error_text in self.FATAL_ERRORS:
                raise CaptchaSolveError(
                    f"2captcha fatal error: {error_text}",
                    error_code=error_text,
                )

            # Unknown error — treat as transient
            logger.warning("Unexpected 2captcha response: %s", data)
            await asyncio.sleep(self.POLL_INTERVAL)
            elapsed += self.POLL_INTERVAL

        raise CaptchaSolveError(
            f"Captcha solve timed out after {timeout}s (task {task_id})"
        )
