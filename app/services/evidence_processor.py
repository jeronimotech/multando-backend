"""Evidence verification and watermarking processor.

Combines HMAC signature verification, freshness checks, GPS plausibility,
duplicate detection, and Pillow-based watermarking into a single pipeline
used by the chatbot engine when creating reports with photographic evidence.
"""

import base64
import hashlib
import hmac
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.report import Evidence

logger = logging.getLogger(__name__)


@dataclass
class EvidenceResult:
    """Result of evidence verification and watermarking."""

    processed_image: bytes
    image_hash: str
    verified: bool
    reasons: list[str] = field(default_factory=list)


class EvidenceProcessor:
    """Verify evidence integrity and apply watermark overlays.

    Verification is best-effort: if metadata (signature, GPS, timestamp) is
    missing (e.g. from a web upload without the SDK), the image is still
    processed but marked as *unverified*.
    """

    FRESHNESS_WINDOW_SECONDS = 300  # 5 minutes

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify_and_process(
        self,
        image_bytes: bytes,
        timestamp: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        signature: str | None = None,
        device_id: str | None = None,
        image_hash: str | None = None,
    ) -> EvidenceResult:
        """Verify signature, check freshness, watermark, return result.

        Args:
            image_bytes: Raw bytes of the evidence image.
            timestamp: ISO-format capture timestamp from the SDK.
            latitude: GPS latitude from the SDK.
            longitude: GPS longitude from the SDK.
            signature: HMAC-SHA256 signature from the SDK.
            device_id: Unique device identifier from the SDK.
            image_hash: SHA-256 hex digest of the original image bytes.

        Returns:
            An ``EvidenceResult`` with the watermarked image and status.
        """
        reasons: list[str] = []

        # Compute hash if not provided
        if not image_hash:
            image_hash = hashlib.sha256(image_bytes).hexdigest()

        # 1. Signature verification
        if signature and timestamp and latitude is not None and longitude is not None and device_id:
            if not self._verify_signature(image_hash, timestamp, latitude, longitude, device_id, signature):
                reasons.append("HMAC signature verification failed")
        else:
            reasons.append("Missing signature metadata -- cannot verify authenticity")

        # 2. Freshness check
        if timestamp:
            if not self._check_freshness(timestamp):
                reasons.append(
                    f"Timestamp is stale (older than {self.FRESHNESS_WINDOW_SECONDS}s)"
                )
        else:
            reasons.append("No timestamp provided -- freshness unknown")

        # 3. GPS plausibility
        if latitude is not None and longitude is not None:
            if not self._check_gps_plausibility(latitude, longitude):
                reasons.append("GPS coordinates are out of valid range")
        else:
            reasons.append("No GPS coordinates provided")

        # 4. Duplicate check
        is_dup = await self._check_duplicate(image_hash)
        if is_dup:
            reasons.append("Duplicate image -- hash already exists in database")

        verified = len(reasons) == 0

        # 5. Watermark
        ts_display = timestamp or datetime.now(timezone.utc).isoformat()
        lat_display = latitude
        lon_display = longitude

        watermarked = self._watermark_image(
            image_bytes,
            ts_display,
            lat_display,
            lon_display,
            verified,
            image_hash,
        )

        return EvidenceResult(
            processed_image=watermarked,
            image_hash=image_hash,
            verified=verified,
            reasons=reasons,
        )

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def _verify_signature(
        self,
        image_hash: str,
        timestamp: str,
        lat: float,
        lon: float,
        device_id: str,
        signature: str,
    ) -> bool:
        """Recompute HMAC-SHA256 and compare with the provided signature.

        The payload is ``image_hash|timestamp|lat|lon|device_id`` keyed with
        the server-side EVIDENCE_HMAC_SECRET.
        """
        # Structural check first
        if len(signature) != 64:
            return False
        try:
            int(signature, 16)
        except ValueError:
            return False

        server_secret = getattr(settings, "EVIDENCE_HMAC_SECRET", None)
        if server_secret:
            payload = "|".join([
                image_hash,
                timestamp,
                f"{lat:.8f}",
                f"{lon:.8f}",
                device_id,
            ])
            expected = hashlib.sha256(
                f"{server_secret}:{payload}".encode()
            ).hexdigest()
            return hmac.compare_digest(expected, signature)

        # No server secret configured -- accept structurally valid signatures
        return True

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------

    def _check_freshness(self, timestamp: str, max_age_seconds: int = 300) -> bool:
        """Check if *timestamp* is within *max_age_seconds* of now."""
        try:
            ts = datetime.fromisoformat(timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = abs((datetime.now(timezone.utc) - ts).total_seconds())
            return delta <= max_age_seconds
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # GPS plausibility
    # ------------------------------------------------------------------

    @staticmethod
    def _check_gps_plausibility(lat: float, lon: float) -> bool:
        """Validate that coordinates are within legal ranges."""
        return -90 <= lat <= 90 and -180 <= lon <= 180

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    async def _check_duplicate(self, image_hash: str) -> bool:
        """Check if this image hash already exists in the evidences table."""
        result = await self.db.execute(
            select(Evidence.id).where(Evidence.image_hash == image_hash).limit(1)
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Watermarking
    # ------------------------------------------------------------------

    def _watermark_image(
        self,
        image_bytes: bytes,
        timestamp: str,
        lat: float | None,
        lon: float | None,
        verified: bool,
        image_hash: str = "",
    ) -> bytes:
        """Apply semi-transparent text watermarks using Pillow.

        Layout:
        - Top-left:     "MULTANDO" branding (large, semi-transparent white)
        - Top-right:    "VERIFIED" or "UNVERIFIED" badge
        - Bottom-left:  Timestamp (ISO format)
        - Bottom-right: GPS coordinates
        - Below brand:  Truncated image hash for audit trail
        """
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        w, h = img.size

        # Create a transparent overlay for the text
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Font sizes scaled to image dimensions
        brand_size = max(24, w // 20)
        meta_size = max(14, w // 40)
        badge_size = max(18, w // 28)
        hash_size = max(10, w // 55)

        try:
            font_brand = ImageFont.load_default(size=brand_size)
            font_meta = ImageFont.load_default(size=meta_size)
            font_badge = ImageFont.load_default(size=badge_size)
            font_hash = ImageFont.load_default(size=hash_size)
        except TypeError:
            # Older Pillow without size= param -- fall back to default
            font_brand = ImageFont.load_default()
            font_meta = font_brand
            font_badge = font_brand
            font_hash = font_brand

        pad = max(8, w // 80)

        # Semi-transparent white / red / green
        white_t = (255, 255, 255, 160)
        green_t = (0, 200, 80, 180)
        red_t = (220, 50, 50, 180)
        shadow = (0, 0, 0, 120)

        # -- Top-left: Multando logo --
        logo_size = max(48, w // 12)
        try:
            from pathlib import Path
            logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
            if logo_path.exists():
                logo = Image.open(logo_path).convert("RGBA")
                logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
                # Apply 80% opacity to the logo
                alpha = logo.split()[3]
                alpha = alpha.point(lambda p: int(p * 0.85))
                logo.putalpha(alpha)
                # Paste with a subtle dark background circle for legibility
                bg_size = logo.size[0] + 16
                bg = Image.new("RGBA", (bg_size, bg_size), (0, 0, 0, 80))
                overlay.paste(bg, (pad, pad), bg)
                overlay.paste(logo, (pad + 8, pad + 8), logo)
        except Exception:
            # Fallback to text if logo loading fails
            draw.text((pad + 1, pad + 1), "MULTANDO", fill=shadow, font=font_brand)
            draw.text((pad, pad), "MULTANDO", fill=white_t, font=font_brand)

        # -- Top-right: VERIFIED / UNVERIFIED badge --
        badge_text = "VERIFIED" if verified else "UNVERIFIED"
        badge_color = green_t if verified else red_t
        bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
        badge_w = bbox[2] - bbox[0]
        draw.text((w - badge_w - pad + 1, pad + 1), badge_text, fill=shadow, font=font_badge)
        draw.text((w - badge_w - pad, pad), badge_text, fill=badge_color, font=font_badge)

        # -- Bottom-left: Timestamp --
        ts_text = f"TS: {timestamp}"
        bbox_ts = draw.textbbox((0, 0), ts_text, font=font_meta)
        ts_h = bbox_ts[3] - bbox_ts[1]
        draw.text((pad + 1, h - ts_h - pad + 1), ts_text, fill=shadow, font=font_meta)
        draw.text((pad, h - ts_h - pad), ts_text, fill=white_t, font=font_meta)

        # -- Bottom-right: GPS coordinates --
        gps_text = (
            f"GPS: {lat:.6f}, {lon:.6f}"
            if lat is not None and lon is not None
            else "GPS: N/A"
        )
        bbox_gps = draw.textbbox((0, 0), gps_text, font=font_meta)
        gps_w = bbox_gps[2] - bbox_gps[0]
        gps_h = bbox_gps[3] - bbox_gps[1]
        draw.text(
            (w - gps_w - pad + 1, h - gps_h - pad + 1),
            gps_text, fill=shadow, font=font_meta,
        )
        draw.text(
            (w - gps_w - pad, h - gps_h - pad),
            gps_text, fill=white_t, font=font_meta,
        )

        # -- Below logo: truncated hash for audit --
        if image_hash:
            hash_text = f"HASH: {image_hash[:16]}..."
            hash_y = pad + logo_size + 24
            draw.text((pad + 1, hash_y + 1), hash_text, fill=shadow, font=font_hash)
            draw.text((pad, hash_y), hash_text, fill=white_t, font=font_hash)

        # Composite the overlay onto the original image
        composite = Image.alpha_composite(img, overlay)
        # Convert to RGB for JPEG output
        result = composite.convert("RGB")

        buf = io.BytesIO()
        result.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
