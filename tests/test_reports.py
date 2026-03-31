"""Tests for report endpoints."""

import pytest
from httpx import AsyncClient


async def _get_auth_token(client: AsyncClient, suffix: str = "") -> str:
    """Helper to register a user and return the access token."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"reporter{suffix}@example.com",
            "password": "securepass123",
            "username": f"reporter{suffix}",
            "display_name": f"Reporter {suffix}",
        },
    )
    return reg.json()["access_token"]


@pytest.mark.asyncio
async def test_list_reports_public(client: AsyncClient):
    """Test listing reports (public endpoint)."""
    response = await client.get("/api/v1/reports")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_list_reports_with_pagination(client: AsyncClient):
    """Test listing reports with pagination params."""
    response = await client.get("/api/v1/reports?page=1&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 5


@pytest.mark.asyncio
async def test_create_report_unauthenticated(client: AsyncClient):
    """Test that creating a report without auth fails."""
    response = await client.post(
        "/api/v1/reports",
        json={
            "infraction_id": 1,
            "incident_datetime": "2024-01-15T10:30:00Z",
            "location": {"lat": 18.4861, "lon": -69.9312},
        },
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_report_not_found(client: AsyncClient):
    """Test getting a non-existent report."""
    response = await client.get("/api/v1/reports/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reports_by_plate_with_limit(client: AsyncClient):
    """Test reports by plate respects limit parameter."""
    response = await client.get("/api/v1/reports/by-plate/A123456?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) <= 5
