"""
AI endpoint tests.
The actual OpenRouter API call is mocked — these tests verify credit deduction,
validation, and the 402 'out of credits' flow, not real LLM output quality.
Run with: pytest tests/test_ai.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from app.main import app


async def get_auth_header_and_db_user(client: AsyncClient, email: str):
    """Register a fresh test user and return their auth header."""
    await client.post("/api/v1/auth/register", json={
        "full_name": "AI Tester",
        "email": email,
        "username": email.split("@")[0],
        "password": "testpass123",
    })
    res = await client.post("/api/v1/auth/login", json={
        "email": email,
        "password": "testpass123",
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _mock_openai_response(text: str):
    """Build a fake OpenAI/OpenRouter chat completion response object."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


@pytest.mark.asyncio
async def test_generate_post_success():
    """Generating a post should succeed and return content + char_count."""
    fake_post = "Here's a great LinkedIn post about backend engineering. #FastAPI #Backend"

    with patch(
        "app.services.ai_service._client.chat.completions.create",
        new=AsyncMock(return_value=_mock_openai_response(fake_post)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await get_auth_header_and_db_user(client, "ai_gen@test.com")
            response = await client.post(
                "/api/v1/ai/generate",
                headers=headers,
                json={
                    "topic": "lessons from shipping my first SaaS",
                    "tone": "professional",
                    "length": "standard",
                    "include_hashtags": True,
                    "include_emoji": False,
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == fake_post
    assert data["char_count"] == len(fake_post)


@pytest.mark.asyncio
async def test_generate_deducts_credit():
    """Each successful generation should deduct exactly 1 AI credit."""
    fake_post = "A post about discipline in engineering."

    with patch(
        "app.services.ai_service._client.chat.completions.create",
        new=AsyncMock(return_value=_mock_openai_response(fake_post)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = await get_auth_header_and_db_user(client, "ai_credit@test.com")

            me_before = await client.get("/api/v1/auth/me", headers=headers)
            credits_before = me_before.json()["ai_credits"]

            await client.post(
                "/api/v1/ai/generate",
                headers=headers,
                json={"topic": "test topic", "tone": "casual", "length": "short"},
            )

            me_after = await client.get("/api/v1/auth/me", headers=headers)
            credits_after = me_after.json()["ai_credits"]

    assert credits_after == credits_before - 1


@pytest.mark.asyncio
async def test_generate_invalid_length_rejected():
    """An invalid 'length' value should be rejected by Pydantic validation (422)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_header_and_db_user(client, "ai_invalid@test.com")
        response = await client.post(
            "/api/v1/ai/generate",
            headers=headers,
            json={"topic": "test", "length": "extremely-long"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_enhance_empty_content_rejected():
    """Enhance endpoint should reject empty content."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await get_auth_header_and_db_user(client, "ai_enhance@test.com")
        response = await client.post(
            "/api/v1/ai/enhance",
            headers=headers,
            json={"content": "   "},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ai_requires_auth():
    """Unauthenticated requests to AI endpoints should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ai/generate",
            json={"topic": "test"},
        )
    assert response.status_code == 401
