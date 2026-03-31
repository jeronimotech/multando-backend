"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """Test successful user registration."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "securepass123",
            "username": "newuser",
            "display_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test registration with duplicate email fails."""
    user_data = {
        "email": "duplicate@example.com",
        "password": "securepass123",
        "username": "user1",
        "display_name": "User One",
    }
    # First registration
    await client.post("/api/v1/auth/register", json=user_data)
    # Duplicate
    response = await client.post(
        "/api/v1/auth/register",
        json={**user_data, "username": "user2"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Test successful login."""
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "securepass123",
            "username": "loginuser",
            "display_name": "Login User",
        },
    )
    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "securepass123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Test login with wrong password fails."""
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpw@example.com",
            "password": "securepass123",
            "username": "wrongpwuser",
            "display_name": "Wrong PW",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    """Test getting current user profile with valid token."""
    # Register and get token
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "password": "securepass123",
            "username": "meuser",
            "display_name": "Me User",
        },
    )
    token = reg.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    """Test getting profile without token fails."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient):
    """Test token refresh."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "securepass123",
            "username": "refreshuser",
            "display_name": "Refresh User",
        },
    )
    refresh = reg.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
