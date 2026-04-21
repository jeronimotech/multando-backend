"""OAuth service for exchanging provider tokens/codes for user info."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


@dataclass(frozen=True)
class GoogleUserInfo:
    """User information returned by Google OAuth."""

    email: str
    name: str
    picture_url: str | None
    google_id: str  # The 'sub' claim


class GoogleOAuthError(Exception):
    """Raised when a Google OAuth operation fails."""


class GoogleOAuthService:
    """Exchange Google auth code or ID token for user info."""

    async def exchange_code(
        self, code: str, redirect_uri: str
    ) -> GoogleUserInfo:
        """Exchange an authorization code for tokens, then fetch user info.

        This is the standard web OAuth flow: the frontend redirects the user
        to Google, receives a code, and sends it to this backend.

        Args:
            code: The authorization code from Google.
            redirect_uri: The redirect URI that was used in the auth request.

        Returns:
            GoogleUserInfo with the user's email, name, picture, and Google ID.

        Raises:
            GoogleOAuthError: If the exchange or user-info fetch fails.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Step 1: Exchange code for access token
            token_resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.error(
                    "Google token exchange failed: %s %s",
                    token_resp.status_code,
                    token_resp.text,
                )
                raise GoogleOAuthError(
                    f"Google token exchange failed ({token_resp.status_code})"
                )

            token_data = token_resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise GoogleOAuthError("No access_token in Google response")

            # Step 2: Fetch user info using the access token
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error(
                    "Google userinfo fetch failed: %s %s",
                    userinfo_resp.status_code,
                    userinfo_resp.text,
                )
                raise GoogleOAuthError(
                    f"Google userinfo fetch failed ({userinfo_resp.status_code})"
                )

            info = userinfo_resp.json()
            return GoogleUserInfo(
                email=info["email"],
                name=info.get("name", ""),
                picture_url=info.get("picture"),
                google_id=info["id"],
            )

    async def verify_id_token(self, id_token: str) -> GoogleUserInfo:
        """Verify a Google ID token (typically from mobile Google Sign-In).

        The mobile SDK provides an ID token directly; we validate it via
        Google's tokeninfo endpoint rather than downloading public keys.

        Args:
            id_token: The JWT ID token from Google Sign-In.

        Returns:
            GoogleUserInfo with the user's email, name, picture, and Google ID.

        Raises:
            GoogleOAuthError: If the token is invalid or verification fails.
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GOOGLE_TOKENINFO_URL,
                params={"id_token": id_token},
            )
            if resp.status_code != 200:
                logger.error(
                    "Google ID token verification failed: %s %s",
                    resp.status_code,
                    resp.text,
                )
                raise GoogleOAuthError(
                    f"Google ID token verification failed ({resp.status_code})"
                )

            data = resp.json()

            # Verify the token was issued for our client
            aud = data.get("aud", "")
            if aud != settings.GOOGLE_CLIENT_ID:
                raise GoogleOAuthError(
                    "ID token audience mismatch: expected "
                    f"{settings.GOOGLE_CLIENT_ID}, got {aud}"
                )

            email = data.get("email")
            if not email:
                raise GoogleOAuthError("No email in Google ID token")

            return GoogleUserInfo(
                email=email,
                name=data.get("name", ""),
                picture_url=data.get("picture"),
                google_id=data["sub"],
            )
