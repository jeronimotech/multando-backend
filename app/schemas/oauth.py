"""OAuth schemas for social login endpoints and OAuth 2.0 provider."""

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


# ---------------------------------------------------------------------------
# OAuth 2.0 Provider schemas (Multando as authorization server)
# ---------------------------------------------------------------------------


class OAuthAuthorizeRequest(BaseSchema):
    """Query parameters for GET /oauth/authorize (consent screen info)."""

    client_id: str = Field(description="API key of the third-party application")
    redirect_uri: str = Field(description="URI to redirect to after authorization")
    scope: str = Field(description="Comma-separated requested scopes")
    state: str | None = Field(default=None, description="Opaque value for CSRF protection")
    response_type: str = Field(default="code", description="Must be 'code'")


class OAuthAuthorizeResponse(BaseSchema):
    """Response after user authorizes; contains the redirect URL with code."""

    redirect_url: str = Field(description="Full redirect URI with code and state params")


class OAuthTokenRequest(BaseSchema):
    """Body for POST /oauth/token."""

    grant_type: str = Field(description="'authorization_code' or 'refresh_token'")
    code: str | None = Field(default=None, description="Authorization code (for authorization_code grant)")
    client_id: str | None = Field(default=None, description="API key of the third-party application")
    redirect_uri: str | None = Field(default=None, description="Must match the original redirect_uri")
    refresh_token: str | None = Field(default=None, description="Refresh token (for refresh_token grant)")


class OAuthTokenResponse(BaseSchema):
    """Token response returned by POST /oauth/token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    scope: str = Field(description="Granted scopes, comma-separated")


class OAuthConsentInfo(BaseSchema):
    """Information rendered on the consent screen."""

    client_name: str = Field(description="Human-readable name of the third-party app")
    scopes: list[str] = Field(description="Requested permission scopes")
