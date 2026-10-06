import os

import pytest_asyncio

os.environ.update(
    {
        "APP_ENV": "test",
        "DEBUG": "true",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "JWT_SECRET_KEY": "test-only-secret-key-that-is-long-enough",
        "LINKEDIN_CLIENT_ID": "test-client-id",
        "LINKEDIN_CLIENT_SECRET": "test-client-secret",
        "LINKEDIN_REDIRECT_URI": "http://localhost:8000/api/v1/linkedin/callback",
        "OPENROUTER_API_KEY": "test-api-key",
        "FERNET_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    }
)

import app.models  # noqa: E402, F401
from app.db.session import Base, engine  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield

    await engine.dispose()