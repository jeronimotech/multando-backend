"""Confidence scoring service for traffic violation reports.

Produces a 0-100 integer score describing how likely a report is to be a
genuine, valid infraction. The score is a composite of:

    - signed evidence (secure capture HMAC verified)
    - presence of photo/image evidence
    - valid Colombian GPS bounds
    - valid Colombian plate format
    - reporter reputation (historical approval ratio)
    - community verification votes
    - community rejection votes

The scorer is intentionally pure: it takes already-loaded data and returns
a dataclass so it can be called from any async/sync context.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from app.models import Evidence, Report, User

logger = logging.getLogger(__name__)


# Colombian plate formats:
#   private cars:        AAA123 or AAA12A
#   motorbikes:          AAA12A / AAA123A
#   public service:      AAA1234 (some cities)
# We accept 3 letters + 2-4 digits + optional trailing letter after
# stripping separators.
_PLATE_RE = re.compile(r"^[A-Z]{3}[0-9]{2,4}[A-Z]?$")


@dataclass
class ConfidenceResult:
    """Result of a confidence scoring pass.

    Attributes:
        score: Final clamped score in [0, 100].
        factors: Mapping of factor name to signed points contribution.
                 Useful for UI explanations and debugging.
    """

    score: int
    factors: dict


class ConfidenceScorer:
    """Pure scoring helper. All methods are static."""

    @staticmethod
    def score(
        report: Report,
        evidences: Iterable[Evidence],
        reporter: User | None,
        verification_count: int = 0,
        rejection_count: int = 0,
    ) -> ConfidenceResult:
        """Compute a confidence score for ``report``.

        Args:
            report: The report being scored.
            evidences: Evidence objects attached to the report.
            reporter: The user who submitted the report. May be ``None``
                if the reporter cannot be loaded.
            verification_count: Number of community verification votes.
            rejection_count: Number of community rejection votes.

        Returns:
            A :class:`ConfidenceResult`.
        """
        score = 50
        factors: dict[str, int] = {}

        evidences_list = list(evidences or [])

        # --- Signed / secure-capture evidence: +30 -----------------------
        if any(getattr(e, "capture_verified", False) for e in evidences_list):
            score += 30
            factors["signed_evidence"] = 30

        # --- Has a photo / image evidence: +10 --------------------------
        def _type_str(e: Evidence) -> str:
            t = getattr(e, "type", None)
            if t is None:
                return ""
            # Enum or plain string both supported
            return str(getattr(t, "value", t)).lower()

        if any(_type_str(e) in ("image", "photo") for e in evidences_list):
            score += 10
            factors["has_photo"] = 10

        # --- Valid Colombian GPS bounds: +10 ----------------------------
        lat = getattr(report, "latitude", None)
        lon = getattr(report, "longitude", None)
        if (
            lat is not None
            and lon is not None
            and -5 < lat < 13
            and -82 < lon < -66
        ):
            score += 10
            factors["valid_gps"] = 10

        # --- Valid Colombian plate format: +10 --------------------------
        plate = getattr(report, "vehicle_plate", None)
        if plate:
            normalized = plate.replace("-", "").replace(" ", "").upper()
            if _PLATE_RE.match(normalized):
                score += 10
                factors["valid_plate"] = 10

        # --- Reporter reputation: up to +15 -----------------------------
        # The User model doesn't have denormalised report counts, so we
        # fall back to any loaded ``reports`` collection when available.
        if reporter is not None:
            total = getattr(reporter, "reports_count", None)
            verified = getattr(reporter, "verified_reports_count", None)
            if total is None or verified is None:
                loaded_reports = getattr(reporter, "reports", None)
                if loaded_reports is not None:
                    # ``reports`` can be an async-unloaded attribute; guard.
                    try:
                        items = list(loaded_reports)
                        total = len(items)
                        # Count anything considered "positive" outcome.
                        verified = sum(
                            1
                            for r in items
                            if _type_str_like(r, "status")
                            in ("verified", "community_verified", "approved")
                        )
                    except Exception:  # pragma: no cover - defensive
                        total = None
                        verified = None

            if total and total > 0 and verified is not None:
                ratio = max(0.0, min(1.0, verified / total))
                bonus = int(ratio * 15)
                if bonus:
                    score += bonus
                    factors["reporter_reputation"] = bonus

        # --- Community verifications: +5 each (max +20) -----------------
        if verification_count > 0:
            bonus = min(verification_count * 5, 20)
            score += bonus
            factors["community_verifications"] = bonus

        # --- Community rejections: -10 each (min -30) -------------------
        if rejection_count > 0:
            penalty = max(rejection_count * -10, -30)
            score += penalty
            factors["community_rejections"] = penalty

        # --- Clamp to [0, 100] ------------------------------------------
        clamped = max(0, min(score, 100))
        if clamped != score:
            factors["clamped"] = clamped - score
            score = clamped

        logger.debug(
            "ConfidenceScorer result: report=%s score=%d factors=%s",
            getattr(report, "id", None),
            score,
            factors,
        )
        return ConfidenceResult(score=score, factors=factors)


def _type_str_like(obj, attr: str) -> str:
    """Return the lowercase string form of ``obj.attr`` for enum-or-str."""
    val = getattr(obj, attr, None)
    if val is None:
        return ""
    return str(getattr(val, "value", val)).lower()
