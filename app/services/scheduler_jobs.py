"""
Background Scheduler Jobs
----------------------------
These functions are NOT called from HTTP requests. They're invoked by APScheduler
on a timer (see app/core/scheduler.py). Each job opens and closes its own DB
session, since there's no request context to inherit one from.

Job 1: publish_due_posts()      — runs every 1 minute
Job 2: refresh_expiring_tokens() — runs once daily
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.post import Post, PostStatus
from app.models.linkedin_account import LinkedInAccount
from app.services.linkedin_publisher import publish_to_linkedin, LinkedInPublishError
from app.services.linkedin_service import refresh_linkedin_token

logger = logging.getLogger("linkedops.scheduler")

MAX_RETRY_ATTEMPTS = 3


async def _get_publish_account(db: AsyncSession, post: Post) -> LinkedInAccount | None:
    if post.linkedin_account_id:
        account_result = await db.execute(
            select(LinkedInAccount).where(LinkedInAccount.id == post.linkedin_account_id)
        )
        account = account_result.scalar_one_or_none()
        if account and account.is_active:
            return account

    account_result = await db.execute(
        select(LinkedInAccount)
        .where(
            LinkedInAccount.user_id == post.user_id,
            LinkedInAccount.is_active == True,  # noqa: E712
        )
        .order_by(LinkedInAccount.is_default.desc(), LinkedInAccount.connected_at.desc())
        .limit(1)
    )
    account = account_result.scalar_one_or_none()
    if account:
        post.linkedin_account_id = account.id
    return account


# ── Job 1: Publish posts whose scheduled time has arrived ────────────────────
async def publish_due_posts() -> None:
    """
    Find all SCHEDULED posts where scheduled_at <= now, and publish them.
    Runs every minute via APScheduler.

    Each post is processed independently — one failure doesn't block the others.
    Failed posts are retried up to MAX_RETRY_ATTEMPTS times, then marked FAILED.
    """
    async with AsyncSessionLocal() as db:
        try:
            now = datetime.now(timezone.utc)

            result = await db.execute(
                select(Post).where(
                    Post.status == PostStatus.SCHEDULED,
                    Post.scheduled_at <= now,
                    Post.retry_count < MAX_RETRY_ATTEMPTS,
                )
            )
            due_posts = result.scalars().all()

            if not due_posts:
                return  # Nothing to do — common case, no need to log every minute

            logger.info(f"Found {len(due_posts)} post(s) due for publishing.")

            for post in due_posts:
                await _publish_single_post(db, post)

            await db.commit()

        except Exception as e:
            logger.error(f"publish_due_posts job crashed: {e}")
            await db.rollback()


async def _publish_single_post(db: AsyncSession, post: Post) -> None:
    """
    Attempt to publish one post. Updates its status in place.
    Does NOT commit — the caller commits after processing the whole batch.
    """
    account = await _get_publish_account(db, post)

    if not account:
        post.status = PostStatus.FAILED
        post.error_message = "LinkedIn account is disconnected or inactive."
        logger.warning(f"Post {post.id} failed: account {post.linkedin_account_id} inactive.")
        return

    try:
        post_urn = await publish_to_linkedin(account, post.content)

        post.status = PostStatus.PUBLISHED
        post.published_at = datetime.now(timezone.utc)
        post.linkedin_post_id = post_urn
        post.error_message = None

        account.last_used_at = datetime.now(timezone.utc)

        logger.info(f"Post {post.id} published successfully → {post_urn}")

    except LinkedInPublishError as e:
        post.retry_count += 1
        post.error_message = e.message

        if e.status_code == 401:
            # Token is dead — don't keep retrying, mark account inactive too
            account.is_active = False
            post.status = PostStatus.FAILED
            logger.warning(f"Post {post.id} failed: token expired for account {account.id}.")
        elif post.retry_count >= MAX_RETRY_ATTEMPTS:
            post.status = PostStatus.FAILED
            logger.warning(f"Post {post.id} failed permanently after {post.retry_count} attempts.")
        else:
            # Leave status as SCHEDULED — will be retried on the next run
            logger.warning(
                f"Post {post.id} attempt {post.retry_count} failed, will retry: {e.message}"
            )

    except Exception as e:
        # Unexpected error — log it, count as a retry attempt
        post.retry_count += 1
        post.error_message = f"Unexpected error: {str(e)}"
        if post.retry_count >= MAX_RETRY_ATTEMPTS:
            post.status = PostStatus.FAILED
        logger.error(f"Post {post.id} unexpected error: {e}")


# ── Job 2: Refresh LinkedIn tokens before they expire ─────────────────────────
async def refresh_expiring_tokens() -> None:
    """
    Find LinkedIn accounts whose tokens expire within the next 7 days,
    and proactively refresh them. Runs once daily via APScheduler.

    This prevents users from ever seeing "account disconnected" due to
    silent token expiry — we refresh well before LinkedIn cuts us off.
    """
    async with AsyncSessionLocal() as db:
        try:
            soon = datetime.now(timezone.utc) + timedelta(days=7)

            result = await db.execute(
                select(LinkedInAccount).where(
                    LinkedInAccount.is_active == True,  # noqa: E712
                    LinkedInAccount.token_expires_at <= soon,
                )
            )
            accounts = result.scalars().all()

            if not accounts:
                logger.info("No LinkedIn tokens need refreshing today.")
                return

            logger.info(f"Refreshing {len(accounts)} LinkedIn token(s).")

            refreshed = 0
            failed = 0
            for account in accounts:
                success = await refresh_linkedin_token(db, account)
                if success:
                    refreshed += 1
                else:
                    failed += 1
                    logger.warning(
                        f"Failed to refresh token for account {account.id} "
                        f"(user {account.user_id}) — marked inactive, needs reconnection."
                    )

            await db.commit()
            logger.info(f"Token refresh complete: {refreshed} succeeded, {failed} failed.")

        except Exception as e:
            logger.error(f"refresh_expiring_tokens job crashed: {e}")
            await db.rollback()
