"""
Scheduler job tests.
Tests the job FUNCTIONS directly (not via HTTP), since they're not request-bound.
LinkedIn API calls are mocked — these test our retry/status logic, not LinkedIn itself.
Run with: pytest tests/test_scheduler_jobs.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.linkedin_account import LinkedInAccount
from app.models.post import Post, PostStatus
from app.core.security import hash_password, encrypt_token
from app.services.scheduler_jobs import publish_due_posts, MAX_RETRY_ATTEMPTS
from app.services.linkedin_publisher import LinkedInPublishError


async def _create_test_user_with_account_and_post(scheduled_minutes_ago: int = 1):
    """
    Helper: creates a user, a connected LinkedIn account, and one SCHEDULED post
    that is already due (scheduled_at in the past). Returns the post's id.
    """
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"sched_test_{datetime.now().timestamp()}@test.com",
            username=f"sched_{int(datetime.now().timestamp())}",
            full_name="Scheduler Test",
            hashed_password=hash_password("testpass123"),
        )
        db.add(user)
        await db.flush()

        account = LinkedInAccount(
            user_id=user.id,
            linkedin_id=f"li_{user.id}",
            name="Test LinkedIn",
            access_token_encrypted=encrypt_token("fake_access_token"),
            refresh_token_encrypted=encrypt_token("fake_refresh_token"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True,
            is_default=True,
        )
        db.add(account)
        await db.flush()

        post = Post(
            user_id=user.id,
            linkedin_account_id=account.id,
            content="Test post content for scheduler job.",
            status=PostStatus.SCHEDULED,
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=scheduled_minutes_ago),
        )
        db.add(post)
        await db.flush()

        await db.commit()
        return post.id, account.id


@pytest.mark.asyncio
async def test_publish_due_posts_success():
    """A due post should be published and marked PUBLISHED."""
    post_id, account_id = await _create_test_user_with_account_and_post()

    with patch(
        "app.services.scheduler_jobs.publish_to_linkedin",
        new=AsyncMock(return_value="urn:li:share:123456"),
    ):
        await publish_due_posts()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()

    assert post.status == PostStatus.PUBLISHED
    assert post.linkedin_post_id == "urn:li:share:123456"
    assert post.published_at is not None


@pytest.mark.asyncio
async def test_publish_due_posts_retries_on_failure():
    """A failed publish attempt should increment retry_count, not immediately fail."""
    post_id, account_id = await _create_test_user_with_account_and_post()

    with patch(
        "app.services.scheduler_jobs.publish_to_linkedin",
        new=AsyncMock(side_effect=LinkedInPublishError("Temporary network issue", status_code=500)),
    ):
        await publish_due_posts()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()

    assert post.status == PostStatus.SCHEDULED  # Still scheduled, will retry
    assert post.retry_count == 1
    assert "Temporary network issue" in post.error_message


@pytest.mark.asyncio
async def test_publish_due_posts_marks_failed_after_max_retries():
    """After MAX_RETRY_ATTEMPTS failures, the post should be marked FAILED."""
    post_id, account_id = await _create_test_user_with_account_and_post()

    # Manually set retry_count to one below the max
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()
        post.retry_count = MAX_RETRY_ATTEMPTS - 1
        await db.commit()

    with patch(
        "app.services.scheduler_jobs.publish_to_linkedin",
        new=AsyncMock(side_effect=LinkedInPublishError("Still failing", status_code=500)),
    ):
        await publish_due_posts()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()

    assert post.status == PostStatus.FAILED
    assert post.retry_count == MAX_RETRY_ATTEMPTS


@pytest.mark.asyncio
async def test_publish_due_posts_401_marks_account_inactive():
    """A 401 (expired token) should immediately fail the post AND deactivate the account."""
    post_id, account_id = await _create_test_user_with_account_and_post()

    with patch(
        "app.services.scheduler_jobs.publish_to_linkedin",
        new=AsyncMock(
            side_effect=LinkedInPublishError("Token expired", status_code=401)
        ),
    ):
        await publish_due_posts()

    async with AsyncSessionLocal() as db:
        post_result = await db.execute(select(Post).where(Post.id == post_id))
        post = post_result.scalar_one()
        account_result = await db.execute(
            select(LinkedInAccount).where(LinkedInAccount.id == account_id)
        )
        account = account_result.scalar_one()

    assert post.status == PostStatus.FAILED
    assert account.is_active is False


@pytest.mark.asyncio
async def test_publish_due_posts_ignores_future_posts():
    """Posts scheduled in the future should NOT be published yet."""
    post_id, account_id = await _create_test_user_with_account_and_post(
        scheduled_minutes_ago=-60  # scheduled 60 min in the FUTURE
    )

    with patch(
        "app.services.scheduler_jobs.publish_to_linkedin",
        new=AsyncMock(return_value="urn:li:share:should_not_be_called"),
    ) as mock_publish:
        await publish_due_posts()
        mock_publish.assert_not_called()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Post).where(Post.id == post_id))
        post = result.scalar_one()

    assert post.status == PostStatus.SCHEDULED
