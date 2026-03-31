"""Tests for gamification endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_badges(client: AsyncClient):
    """Test getting all badges."""
    response = await client.get("/api/v1/gamification/badges")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_get_badges_with_limit(client: AsyncClient):
    """Test badges endpoint respects limit parameter."""
    response = await client.get("/api/v1/gamification/badges?limit=5&offset=0")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_levels(client: AsyncClient):
    """Test getting all levels."""
    response = await client.get("/api/v1/gamification/levels")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_infractions(client: AsyncClient):
    """Test getting all infraction types."""
    response = await client.get("/api/v1/infractions")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


@pytest.mark.asyncio
async def test_get_vehicle_types(client: AsyncClient):
    """Test getting all vehicle types."""
    response = await client.get("/api/v1/vehicle-types")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
