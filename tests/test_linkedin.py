"""
LinkedIn OAuth flow tests.
These tests mock the LinkedIn API calls so no real credentials are needed.
Run with: pytest tests/test_linkedin.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import create_access_token, encrypt_token
from datetime import timedelta


# ── Helpers ───────────────────────────────────────────────────────────────────
async def get_auth_header(client: AsyncClient) -> dict:
    """Register a test user and return their auth header."""
    await client.post("/api/v1/auth/register", json={
        "full_name": "Test User",
        "email": "oauth_test@test.com",
        "username": "oauth_tester",
        "password": "testpass123",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": "oauth_test@test.com",
        "password": "testpass123",
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Tests ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_connect_returns_auth_url():
    """GET /linkedin/connect should return a LinkedIn authorization URL."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_header(client)
        response = await client.get("/api/v1/linkedin/connect", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "auth_url" in data
    assert "linkedin.com/oauth" in data["auth_url"]
    assert "state=" in data["auth_url"]


@pytest.mark.asyncio
async def test_callback_with_bad_state_redirects_with_error():
    """Callback with a tampered state should redirect with an error."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        response = await client.get(
            "/api/v1/linkedin/callback",
            params={"code": "fake_code", "state": "tampered_state_token"},
        )

    assert response.status_code in (302, 307)
    assert "error" in response.headers["location"]


@pytest.mark.asyncio
async def test_callback_user_denied_redirects_with_error():
    """If LinkedIn sends error=access_denied, redirect to frontend with error."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        response = await client.get(
            "/api/v1/linkedin/callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
        )

    assert response.status_code in (302, 307)
    assert "User+cancelled" in response.headers["location"] or "User" in response.headers["location"]


@pytest.mark.asyncio
async def test_list_accounts_empty():
    """New user should have zero connected accounts."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_header(client)
        response = await client.get("/api/v1/linkedin/accounts", headers=headers)

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_connect_requires_auth():
    """Unauthenticated request to /connect should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/linkedin/connect")
    assert response.status_code == 401
