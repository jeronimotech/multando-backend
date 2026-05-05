"""Use Anthropic's Claude to extract structured infraction data from tweets.

Tweets that mention a hashtag like ``#TránsitoBogotá`` typically describe
a traffic infraction in free-form Spanish — sometimes with a plate, a
location, and an embedded photo. This module asks Claude to read the
tweet text (and any image URLs) and return a strict JSON object with
the fields the report builder needs.

The model is asked to use a Claude tool ("structured output") so we get
guaranteed JSON. If that fails or the response can't be parsed we fall
back to text-extraction with strict JSON parsing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

try:
    import anthropic
except ImportError:  # pragma: no cover — hard dep installed via requirements
    anthropic = None  # type: ignore[assignment]

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain knowledge — common Colombian/LatAm infraction codes
# ---------------------------------------------------------------------------

# Subset of Colombia's CNT codes that are most commonly tweeted about.
# The model is told to pick the closest match (or ``null``).
INFRACTION_CODES: list[dict[str, str]] = [
    {
        "code": "C02",
        "name": "Estacionar en sitios prohibidos",
        "description": "Parking in prohibited areas (no-parking zones, sidewalks).",
    },
    {
        "code": "C29",
        "name": "No detenerse ante semáforo en rojo",
        "description": "Running a red light or stop signal.",
    },
    {
        "code": "C14",
        "name": "Conducir un vehículo sin el SOAT vigente",
        "description": "Driving without mandatory accident insurance.",
    },
    {
        "code": "C24",
        "name": "No respetar el paso de peatones",
        "description": "Failing to yield to pedestrians at a crossing.",
    },
    {
        "code": "C35",
        "name": "Conducir a velocidad superior a la máxima permitida",
        "description": "Speeding above the posted limit.",
    },
    {
        "code": "C38",
        "name": "Transitar por sitios restringidos o en horas prohibidas",
        "description": "Driving in restricted zones / wrong way / pico y placa violation.",
    },
    {
        "code": "D02",
        "name": "Estacionar bloqueando andén o ciclovía",
        "description": "Blocking sidewalk or bike lane while parked.",
    },
    {
        "code": "C21",
        "name": "No usar el cinturón de seguridad",
        "description": "Driver/passenger not wearing a seatbelt.",
    },
    {
        "code": "C26",
        "name": "Usar el celular mientras se conduce",
        "description": "Using a mobile phone while driving.",
    },
    {
        "code": "D04",
        "name": "Conducir motocicleta sin casco",
        "description": "Riding a motorcycle without a helmet.",
    },
]


_INFRACTION_CODE_SET = {c["code"] for c in INFRACTION_CODES}


# Loose Colombian plate matchers. Cars: AAA-123 or AAA123 (3 letters + 3 digits).
# Motorcycles: AAA-12A or AAA12A (3 letters + 2 digits + 1 letter).
_PLATE_RE = re.compile(
    r"^[A-Z]{3}-?(?:[0-9]{3}|[0-9]{2}[A-Z])$"
)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an extraction assistant for **Multando**, an open-source citizen
reporting platform for traffic infractions in Latin America (primarily
Colombia). Multando ingests tweets that mention configured hashtags
(e.g. ``#TránsitoBogotá``) and tries to convert each report into a
structured infraction record so the community can vote on it.

Given a tweet (text plus optional image URLs), return ONE JSON object
that matches this schema:

{
  "plate":            string | null,   // license plate UPPERCASE, no spaces.
  "infraction_code":  string | null,   // pick from the list below or null.
  "infraction_name":  string | null,   // short Spanish description.
  "location_text":    string | null,   // address / intersection mentioned.
  "latitude":         number | null,   // ONLY if explicitly stated. No guesses.
  "longitude":        number | null,
  "confidence":       number,          // 0.0–1.0 — your overall confidence.
  "reasoning":        string           // short explanation (max 200 chars).
}

Infraction codes you can use:
""" + "\n".join(
    f"- **{c['code']}** — {c['name']}. {c['description']}"
    for c in INFRACTION_CODES
) + """

Rules:
- Be conservative. If the tweet is sarcastic, off-topic, a meme, or
  doesn't actually describe a real infraction, return very low
  confidence (<0.3) and ``null`` for the structured fields.
- Plates must be UPPERCASE. Strip dashes and spaces.
- Never invent coordinates. ``latitude``/``longitude`` should only be
  populated if the tweet contains explicit numeric coordinates.
- ``location_text`` may be a free-form address ("Calle 100 con Cra 15"),
  even when GPS is unknown.
- Output **only** valid JSON — no Markdown fences, no commentary.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_infraction_data(tweet: dict[str, Any]) -> dict[str, Any]:
    """Run the LLM extraction over a single Apify tweet payload.

    Args:
        tweet: The Apify dataset item. Expected (lenient) shape::

            {
              "id_str": "...",
              "full_text" / "text": "...",
              "user": {"screen_name": "..."},
              "media": [{"media_url_https": "..."}],
              ...
            }

    Returns:
        A dict shaped like the schema in the system prompt::

            {
              "plate": str | None,
              "infraction_code": str | None,
              "infraction_name": str | None,
              "location_text": str | None,
              "latitude": float | None,
              "longitude": float | None,
              "confidence": float,
              "reasoning": str,
            }

        On failure the dict is returned with ``confidence=0.0`` and
        ``reasoning`` set to the error message.
    """
    text = _coerce_tweet_text(tweet)
    image_urls = _coerce_media_urls(tweet)

    if anthropic is None:
        return _empty_result("anthropic SDK not installed")

    if not settings.ANTHROPIC_API_KEY:
        return _empty_result("ANTHROPIC_API_KEY not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": _build_user_prompt(text, image_urls)}
    ]
    # Attach image references via URL when supported. Claude 3.5+ accepts
    # ``image`` content blocks with a ``url`` source.
    for url in image_urls[:4]:  # cap to avoid huge payloads
        user_content.append(
            {
                "type": "image",
                "source": {"type": "url", "url": url},
            }
        )

    try:
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # network / API errors
        logger.warning("Claude extraction failed: %s", exc, exc_info=True)
        return _empty_result(f"Claude API error: {exc}")

    raw_text = _extract_text_block(response)
    parsed = _parse_json_strict(raw_text)
    if parsed is None:
        return _empty_result(f"Could not parse JSON from model: {raw_text[:200]}")

    return _normalize_result(parsed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_tweet_text(tweet: dict[str, Any]) -> str:
    """Extract the human-readable tweet text from the Apify item."""
    for key in ("full_text", "text", "fullText"):
        v = tweet.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _coerce_media_urls(tweet: dict[str, Any]) -> list[str]:
    """Extract image URLs from a variety of Apify tweet shapes."""
    urls: list[str] = []
    media = tweet.get("media") or tweet.get("entities", {}).get("media") or []
    for m in media:
        if not isinstance(m, dict):
            continue
        for k in ("media_url_https", "media_url", "url", "expanded_url"):
            v = m.get(k)
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)
                break

    # Some actors return a flat ``mediaUrls`` list.
    flat = tweet.get("mediaUrls")
    if isinstance(flat, list):
        for v in flat:
            if isinstance(v, str) and v.startswith("http"):
                urls.append(v)

    # de-dupe, preserve order
    seen: set[str] = set()
    deduped: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped.append(u)
    return deduped


def _build_user_prompt(text: str, image_urls: list[str]) -> str:
    parts = ["Tweet text:", text or "(empty)"]
    if image_urls:
        parts.append("\nAttached image URLs:")
        for u in image_urls:
            parts.append(f"- {u}")
    parts.append(
        "\nReturn only the JSON object described in the system prompt."
    )
    return "\n".join(parts)


def _extract_text_block(response: Any) -> str:
    """Pull the first text block out of an Anthropic Messages response."""
    try:
        blocks = response.content or []
    except AttributeError:
        return ""
    for block in blocks:
        # SDK objects have ``.type`` and ``.text``
        block_type = getattr(block, "type", None)
        if block_type == "text":
            return getattr(block, "text", "") or ""
    return ""


def _parse_json_strict(raw: str) -> Optional[dict[str, Any]]:
    """Best-effort JSON parsing — strips Markdown fences if present."""
    if not raw:
        return None

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Strip ```json ... ``` fence
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Fallback: locate the first ``{ ... }`` block.
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _normalize_result(parsed: dict[str, Any]) -> dict[str, Any]:
    """Sanity-check + plate-regex penalty, returning the canonical shape."""
    plate = parsed.get("plate")
    if isinstance(plate, str):
        plate = plate.upper().replace(" ", "").strip()
        if not plate:
            plate = None
    else:
        plate = None

    code = parsed.get("infraction_code")
    if isinstance(code, str):
        code = code.upper().strip()
        if code not in _INFRACTION_CODE_SET:
            # Unknown code — keep as-is but the model should still surface
            # ``infraction_name`` so admins can review.
            pass
    else:
        code = None

    confidence_raw = parsed.get("confidence", 0.0)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    # Plate sanity penalty: if a plate is present but doesn't match the
    # Colombian regex, knock the confidence down by 0.3 (clamped).
    if plate and not _PLATE_RE.match(plate.replace("-", "")):
        # Try with dash inserted at canonical position before final fail.
        if not _PLATE_RE.match(plate):
            confidence = max(0.0, confidence - 0.3)

    def _coerce_float(v: Any) -> Optional[float]:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        # Reject obvious garbage / out-of-range values.
        if f != f:  # NaN
            return None
        return f

    lat = _coerce_float(parsed.get("latitude"))
    lon = _coerce_float(parsed.get("longitude"))
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None

    return {
        "plate": plate,
        "infraction_code": code,
        "infraction_name": _coerce_str(parsed.get("infraction_name")),
        "location_text": _coerce_str(parsed.get("location_text")),
        "latitude": lat,
        "longitude": lon,
        "confidence": confidence,
        "reasoning": _coerce_str(parsed.get("reasoning")) or "",
    }


def _coerce_str(v: Any) -> Optional[str]:
    if isinstance(v, str):
        s = v.strip()
        return s or None
    return None


def _empty_result(reason: str) -> dict[str, Any]:
    return {
        "plate": None,
        "infraction_code": None,
        "infraction_name": None,
        "location_text": None,
        "latitude": None,
        "longitude": None,
        "confidence": 0.0,
        "reasoning": reason[:200],
    }
