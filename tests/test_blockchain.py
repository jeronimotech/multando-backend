"""Tests for blockchain endpoints."""

import pytest
from httpx import AsyncClient


async def _get_auth_token(client: AsyncClient) -> str:
    """Helper to register and return access token."""
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "blockchain@example.com",
            "password": "securepass123",
            "username": "blockchainuser",
            "display_name": "Blockchain User",
        },
    )
    return reg.json()["access_token"]


@pytest.mark.asyncio
async def test_get_balance_unauthenticated(client: AsyncClient):
    """Test balance endpoint requires auth."""
    response = await client.get("/api/v1/blockchain/balance")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_staking_info(client: AsyncClient):
    """Test getting staking info (public)."""
    response = await client.get("/api/v1/blockchain/staking-info")
    assert response.status_code == 200
    data = response.json()
    assert "apy" in data
    assert "min_stake" in data
    assert "lock_period_days" in data


@pytest.mark.asyncio
async def test_stake_unauthenticated(client: AsyncClient):
    """Test staking requires auth."""
    response = await client.post(
        "/api/v1/blockchain/stake",
        json={"amount": 10.0},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_transactions_unauthenticated(client: AsyncClient):
    """Test transaction history requires auth."""
    response = await client.get("/api/v1/blockchain/transactions")
    assert response.status_code in (401, 403)
