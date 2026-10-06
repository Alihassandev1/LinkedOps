"""
Basic auth endpoint tests.
Run with: pytest tests/ -v
"""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_register_and_login():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Register
        response = await client.post("/api/v1/auth/register", json={
            "full_name": "Ali Hassan",
            "email": "ali@test.com",
            "username": "ali_hassan",
            "password": "securepass123",
        })
        assert response.status_code == 201
        tokens = response.json()
        assert "access_token" in tokens

        # Login
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "ali@test.com", "password": "securepass123"},
        )
        assert response.status_code == 200

        # Get current user
        tokens = response.json()
        access_token = tokens["access_token"]
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "ali@test.com"

        # Refresh tokens must not authorize protected endpoints
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_accepts_json_body():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/api/v1/auth/register", json={
            "full_name": "Json Login",
            "email": "json-login@test.com",
            "username": "json_login",
            "password": "securepass123",
        })

        response = await client.post("/api/v1/auth/login", json={
            "email": "json-login@test.com",
            "password": "securepass123",
        })

        assert response.status_code == 200
        tokens = response.json()
        assert tokens["token_type"] == "bearer"
        assert "access_token" in tokens
        assert "refresh_token" in tokens
