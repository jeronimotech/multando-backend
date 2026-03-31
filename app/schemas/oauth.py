"""OAuth schemas for social login endpoints."""

from pydantic import Field

from app.schemas.base import BaseSchema


class OAuthCodeRequest(BaseSchema):
    """OAuth authorization code request.

    Used by both Google and GitHub OAuth flows where the frontend
    sends the authorization code received from the provider.
    """

    code: str = Field(description="Authorization code from OAuth provider")
    redirect_uri: str = Field(
        default="", description="Redirect URI used in the OAuth flow"
    )
