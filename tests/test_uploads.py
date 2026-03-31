"""Tests for upload endpoints."""

import pytest
from httpx import AsyncClient


async def _get_auth_token(client: AsyncClient) -> str:
    """Helper to register and return access token."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "uploader@example.com",
            "password": "securepass123",
            "username": "uploader",
            "display_name": "Uploader",
        },
    )
    return reg.json()["access_token"]


@pytest.mark.asyncio
async def test_presign_unauthenticated(client: AsyncClient):
    """Test presign endpoint requires auth."""
    response = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "test.jpg", "content_type": "image/jpeg"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_presign_success(client: AsyncClient):
    """Test successful presign URL generation."""
    token = await _get_auth_token(client)
    response = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "evidence.jpg", "content_type": "image/jpeg", "file_size": 1024},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "upload_url" in data
    assert "file_key" in data
    assert "public_url" in data
    assert data["expires_in"] == 3600


@pytest.mark.asyncio
async def test_presign_invalid_content_type(client: AsyncClient):
    """Test presign rejects invalid content types."""
    token = await _get_auth_token(client)
    response = await client.post(
        "/api/v1/uploads/presign",
        json={"filename": "malware.exe", "content_type": "application/x-msdownload"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_presign_file_too_large(client: AsyncClient):
    """Test presign rejects oversized files."""
    token = await _get_auth_token(client)
    response = await client.post(
        "/api/v1/uploads/presign",
        json={
            "filename": "huge.mp4",
            "content_type": "video/mp4",
            "file_size": 100 * 1024 * 1024,  # 100MB
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
