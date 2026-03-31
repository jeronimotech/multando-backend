"""Submits verified Multando reports to the Ministerio de Transporte RECORD form.

The RECORD (Registro de Condiciones de Riesgo en los Desplazamientos) form is
a public form where citizens can report road safety conditions. This module
automates the submission using Playwright for browser automation and 2captcha
for solving the reCAPTCHA challenge.
"""

import logging
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from playwright.async_api import Page, async_playwright

from app.core.config import settings
from app.integrations.captcha_solver import CaptchaSolveError, CaptchaSolver

logger = logging.getLogger(__name__)


class RecordSubmissionError(Exception):
    """Raised when RECORD form submission fails."""

    pass


class RecordSubmitter:
    """Submits verified Multando reports to the Ministerio de Transporte RECORD form."""

    RECORD_URL = (
        "https://mintransporte.gov.co/publicaciones/11627/"
        "registro-de-condiciones-de-riesgo-en-los-desplazamientos-record/"
    )
    RECAPTCHA_SITE_KEY = "6Le3HFUUAAAAAG1G2sUAAtiNSVI5K4oGQPO4VPZH"
    FORM_SELECTOR = "#KeywordDspForm-105"
    SUBMIT_TIMEOUT_MS = 30_000

    def __init__(self, report_id: str | None = None) -> None:
        self.captcha_solver = CaptchaSolver(api_key=settings.TWOCAPTCHA_API_KEY)
        self.report_id = report_id or uuid.uuid4().hex[:12]
        self.screenshots: list[dict[str, str]] = []  # {step, local_path, s3_url}

    async def submit_report(self, report: dict[str, Any]) -> dict[str, Any]:
        """Submit a verified report to RECORD.

        Args:
            report: Dict with keys:
                - department: str (e.g. "Cundinamarca")
                - city: str (e.g. "Bogotá D.C")
                - event_date: str (dd/mm/yy)
                - event_time: str (HH:MM)
                - evidence_urls: list[str] (S3 URLs of evidence files)
                - reporter_name: str (optional)
                - reporter_phone: str (optional)

        Returns:
            Dict with submission status and details:
                - success: bool
                - message: str
                - response_text: str (page content after submission)

        Raises:
            RecordSubmissionError: If any step of the submission fails.
        """
        downloaded_files: list[Path] = []

        try:
            # Download evidence files to temporary directory
            evidence_urls = report.get("evidence_urls") or []
            if evidence_urls:
                downloaded_files = await self._download_evidence_files(evidence_urls)

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                    ],
                )
                context = await browser.new_context(
                    locale="es-CO",
                    viewport={"width": 1280, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()

                try:
                    result = await self._fill_and_submit(
                        page, report, downloaded_files
                    )
                    return result
                finally:
                    await context.close()
                    await browser.close()

        except CaptchaSolveError as exc:
            raise RecordSubmissionError(
                f"Failed to solve reCAPTCHA: {exc}"
            ) from exc
        except Exception as exc:
            if isinstance(exc, RecordSubmissionError):
                raise
            raise RecordSubmissionError(
                f"Unexpected error during RECORD submission: {exc}"
            ) from exc
        finally:
            # Clean up temp files
            for f in downloaded_files:
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass

    async def _take_screenshot(self, page: Page, step: str) -> dict[str, str]:
        """Capture a screenshot and upload to S3.

        Args:
            page: Playwright page instance.
            step: Description of the step (e.g. "form_filled", "submission_complete").

        Returns:
            Dict with step, local_path, and s3_url.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"record_{self.report_id}_{step}_{timestamp}.png"
        local_path = Path(tempfile.gettempdir()) / filename

        await page.screenshot(path=str(local_path), full_page=True)
        logger.info("Screenshot captured: %s (%s)", step, local_path)

        # Upload to S3
        s3_key = f"record-screenshots/{self.report_id}/{filename}"
        s3_url = await self._upload_screenshot_to_s3(local_path, s3_key)

        entry = {"step": step, "local_path": str(local_path), "s3_url": s3_url}
        self.screenshots.append(entry)
        return entry

    async def _upload_screenshot_to_s3(self, local_path: Path, s3_key: str) -> str:
        """Upload a screenshot file to S3.

        Args:
            local_path: Path to the local PNG file.
            s3_key: The S3 object key.

        Returns:
            Public URL of the uploaded screenshot.
        """
        if settings.AWS_ACCESS_KEY_ID:
            try:
                import boto3

                s3 = boto3.client(
                    "s3",
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION,
                )
                s3.upload_file(
                    str(local_path),
                    settings.S3_BUCKET,
                    s3_key,
                    ExtraArgs={"ContentType": "image/png"},
                )
                url = f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
                logger.info("Screenshot uploaded to S3: %s", url)
                return url
            except Exception as exc:
                logger.warning("Failed to upload screenshot to S3: %s", exc)

        # Dev fallback
        return f"{settings.STORAGE_BASE_URL}/{s3_key}"

    async def _fill_and_submit(
        self,
        page: Page,
        report: dict[str, Any],
        evidence_files: list[Path],
    ) -> dict[str, Any]:
        """Navigate to the form, fill it, solve captcha, and submit."""
        # 1. Navigate to the RECORD page
        logger.info("Navigating to RECORD form: %s", self.RECORD_URL)
        await page.goto(self.RECORD_URL, wait_until="networkidle", timeout=60_000)

        # Wait for form to be present
        await page.wait_for_selector(self.FORM_SELECTOR, timeout=30_000)
        logger.info("RECORD form loaded")

        # 2. Select department
        department = report["department"]
        logger.info("Selecting department: %s", department)
        await page.select_option(
            "select[name='fieldFrm715']",
            label=department,
        )

        # 3. Wait for city dropdown to populate (AJAX dependent on department)
        logger.info("Waiting for city dropdown to load...")
        await page.wait_for_function(
            """() => {
                const sel = document.querySelector("select[name='fieldFrm715Ciudad']");
                return sel && sel.options.length > 1;
            }""",
            timeout=15_000,
        )

        # 4. Select city
        city = report["city"]
        logger.info("Selecting city: %s", city)
        await page.select_option(
            "select[name='fieldFrm715Ciudad']",
            label=city,
        )

        # 5. Fill event date (dd/mm/yy)
        event_date = report["event_date"]
        logger.info("Filling event date: %s", event_date)
        await page.fill("input[name='fieldFrm716']", event_date)

        # 6. Fill event time
        event_time = report["event_time"]
        logger.info("Filling event time: %s", event_time)
        await page.fill("input[name='fieldFrm717']", event_time)

        # 7. Upload evidence files
        if evidence_files:
            await self._upload_evidence(page, evidence_files)

        # 8. Fill optional fields
        reporter_name = report.get("reporter_name")
        if reporter_name:
            logger.info("Filling reporter name")
            await page.fill("input[name='fieldFrm719']", reporter_name)

        reporter_phone = report.get("reporter_phone")
        if reporter_phone:
            logger.info("Filling reporter phone")
            await page.fill("input[name='fieldFrm720']", reporter_phone)

        # Screenshot: form filled (before captcha)
        await self._take_screenshot(page, "01_form_filled")

        # 9. Check terms checkbox
        logger.info("Checking terms checkbox")
        terms_checkbox = page.locator(
            f"{self.FORM_SELECTOR} input[type='checkbox']"
        ).first
        if not await terms_checkbox.is_checked():
            await terms_checkbox.check()

        # 10. Solve reCAPTCHA
        logger.info("Solving reCAPTCHA via 2captcha...")
        captcha_token = await self.captcha_solver.solve_recaptcha(
            site_key=self.RECAPTCHA_SITE_KEY,
            page_url=self.RECORD_URL,
        )

        # Inject the solved token
        await page.evaluate(
            """(token) => {
                const textarea = document.getElementById('g-recaptcha-response');
                if (textarea) {
                    textarea.style.display = 'block';
                    textarea.value = token;
                }
                // Also try setting via grecaptcha callback if available
                if (typeof grecaptcha !== 'undefined') {
                    try {
                        const widgetId = grecaptcha.getWidgetId
                            ? grecaptcha.getWidgetId()
                            : 0;
                        grecaptcha.enterprise
                            ? grecaptcha.enterprise.execute(widgetId)
                            : null;
                    } catch(e) {}
                }
                // Trigger any callback attached to the recaptcha
                if (typeof ___grecaptcha_cfg !== 'undefined') {
                    try {
                        const clients = ___grecaptcha_cfg.clients;
                        for (const key in clients) {
                            const client = clients[key];
                            for (const prop in client) {
                                const item = client[prop];
                                if (item && item.callback) {
                                    item.callback(token);
                                }
                            }
                        }
                    } catch(e) {}
                }
            }""",
            captcha_token,
        )
        logger.info("reCAPTCHA token injected")

        # Screenshot: captcha solved, ready to submit
        await self._take_screenshot(page, "02_captcha_solved")

        # 11. Submit the form
        logger.info("Submitting RECORD form")

        # Listen for the AJAX response
        async with page.expect_response(
            lambda resp: "ajaxResolveForm" in resp.url,
            timeout=self.SUBMIT_TIMEOUT_MS,
        ) as response_info:
            submit_button = page.locator(
                f"{self.FORM_SELECTOR} button[type='submit'], "
                f"{self.FORM_SELECTOR} input[type='submit']"
            ).first
            await submit_button.click()

        response = await response_info.value
        response_status = response.status

        try:
            response_body = await response.json()
        except Exception:
            response_body = await response.text()

        logger.info(
            "RECORD form submitted — HTTP %d, response: %s",
            response_status,
            str(response_body)[:500],
        )

        # Screenshot: after submission (confirmation or error)
        await self._take_screenshot(page, "03_submission_result")

        success = response_status == 200
        return {
            "success": success,
            "http_status": response_status,
            "message": "RECORD submission successful" if success else "Submission failed",
            "response_data": response_body,
            "screenshots": [
                {"step": s["step"], "url": s["s3_url"]}
                for s in self.screenshots
            ],
        }

    async def _upload_evidence(
        self,
        page: Page,
        evidence_files: list[Path],
    ) -> None:
        """Upload evidence files to the RECORD form."""
        # First file goes into fieldFrm718[]
        if len(evidence_files) >= 1:
            logger.info("Uploading evidence file 1: %s", evidence_files[0].name)
            file_input_1 = page.locator("input[name='fieldFrm718[]']").first
            await file_input_1.set_input_files(str(evidence_files[0]))

        # Second file goes into fieldFrm722
        if len(evidence_files) >= 2:
            logger.info("Uploading evidence file 2: %s", evidence_files[1].name)
            file_input_2 = page.locator("input[name='fieldFrm722']").first
            await file_input_2.set_input_files(str(evidence_files[1]))

    async def _download_evidence_files(
        self,
        urls: list[str],
    ) -> list[Path]:
        """Download evidence files from S3 URLs to temporary files.

        Returns a list of Path objects pointing to the downloaded files.
        Only downloads up to 2 files (the max the form accepts).
        """
        downloaded: list[Path] = []
        urls_to_download = urls[:2]  # RECORD form accepts max 2 files

        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
        ) as client:
            for url in urls_to_download:
                try:
                    logger.info("Downloading evidence: %s", url)
                    response = await client.get(url)
                    response.raise_for_status()

                    # Determine file extension from URL or content type
                    suffix = self._get_file_suffix(url, response)
                    tmp = tempfile.NamedTemporaryFile(
                        delete=False,
                        suffix=suffix,
                        prefix="multando_evidence_",
                    )
                    tmp.write(response.content)
                    tmp.close()
                    downloaded.append(Path(tmp.name))
                    logger.info("Downloaded evidence to: %s", tmp.name)

                except httpx.HTTPError as exc:
                    logger.error("Failed to download evidence %s: %s", url, exc)
                    # Continue with other files — partial evidence is acceptable

        return downloaded

    @staticmethod
    def _get_file_suffix(url: str, response: httpx.Response) -> str:
        """Determine file extension from URL path or Content-Type header."""
        # Try URL path
        from urllib.parse import urlparse

        path = urlparse(url).path
        if "." in path.split("/")[-1]:
            return "." + path.split(".")[-1].lower()

        # Fall back to content type
        content_type = response.headers.get("content-type", "")
        type_to_ext = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "application/pdf": ".pdf",
        }
        for mime, ext in type_to_ext.items():
            if mime in content_type:
                return ext

        return ".bin"
