"""Tests for health check and root endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    """Test root endpoint returns welcome message."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert "docs" in data


@pytest.mark.asyncio
async def test_api_v1_root(client: AsyncClient):
    """Test API v1 root endpoint."""
    response = await client.get("/api/v1/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
