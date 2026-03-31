"""City schemas for the Multando API."""

from pydantic import Field

from app.schemas.base import BaseSchema


class CityResponse(BaseSchema):
    """Schema for city data returned by the API."""

    id: int = Field(description="City unique identifier")
    name: str = Field(description="City name")
    country_code: str = Field(description="ISO 3166-1 alpha-2 country code")
    state_province: str | None = Field(default=None, description="State or province")
    latitude: float = Field(description="City center latitude")
    longitude: float = Field(description="City center longitude")
    timezone: str = Field(description="IANA timezone identifier")


class CityListResponse(BaseSchema):
    """Schema for a list of cities."""

    items: list[CityResponse] = Field(description="List of cities")


class CityStatsResponse(BaseSchema):
    """Schema for public city statistics."""

    city: CityResponse = Field(description="City information")
    total_reports: int = Field(description="Total number of reports in this city")
    verified_reports: int = Field(description="Number of verified reports")
    active_reporters: int = Field(description="Number of users who have filed reports")
