from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.core.deps import get_current_active_user
from app.models.user import User
from app.models.post import Post, PostStatus
from app.models.linkedin_account import LinkedInAccount
from app.schemas.post import PostCreate, PostUpdate, PostOut

router = APIRouter(prefix="/posts", tags=["posts"])


async def resolve_post_account_id(
    db: AsyncSession,
    user_id: int,
    requested_account_id: int | None,
    require_account: bool,
) -> int | None:
    if requested_account_id is not None:
        result = await db.execute(
            select(LinkedInAccount).where(
                LinkedInAccount.id == requested_account_id,
                LinkedInAccount.user_id == user_id,
                LinkedInAccount.is_active == True,  # noqa: E712
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LinkedIn account not found or inactive.",
            )
        return requested_account_id

    result = await db.execute(
        select(LinkedInAccount)
        .where(
            LinkedInAccount.user_id == user_id,
            LinkedInAccount.is_active == True,  # noqa: E712
        )
        .order_by(LinkedInAccount.is_default.desc(), LinkedInAccount.connected_at.desc())
        .limit(1)
    )
    account = result.scalar_one_or_none()
    if account:
        return account.id
    if require_account:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect an active LinkedIn account before scheduling a post.",
        )
    return None


@router.post("/", response_model=PostOut, status_code=201)
async def create_post(
    data: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Create a new post. If scheduled_at is provided → status = SCHEDULED.
    Otherwise → status = DRAFT.
    """
    post_status = PostStatus.SCHEDULED if data.scheduled_at else PostStatus.DRAFT
    linkedin_account_id = await resolve_post_account_id(
        db,
        current_user.id,
        data.linkedin_account_id,
        require_account=bool(data.scheduled_at),
    )

    post = Post(
        user_id=current_user.id,
        linkedin_account_id=linkedin_account_id,
        content=data.content,
        scheduled_at=data.scheduled_at,
        ai_enhanced=data.ai_enhanced,
        status=post_status,
    )
    db.add(post)
    await db.flush()
    return post


@router.get("/", response_model=List[PostOut])
async def list_posts(
    status: PostStatus = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all posts for the current user.
    Optionally filter by status: draft | scheduled | published | failed
    """
    query = select(Post).where(Post.user_id == current_user.id)
    if status:
        query = query.where(Post.status == status)
    query = query.order_by(Post.created_at.desc())
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.user_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")
    return post


@router.patch("/{post_id}", response_model=PostOut)
async def update_post(
    post_id: int,
    data: PostUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Update a draft or scheduled post. Cannot edit published posts.
    """
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.user_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Published posts cannot be edited.",
        )

    update_data = data.model_dump(exclude_unset=True)
    next_scheduled_at = update_data.get("scheduled_at", post.scheduled_at)

    if "linkedin_account_id" in update_data:
        update_data["linkedin_account_id"] = await resolve_post_account_id(
            db,
            current_user.id,
            update_data["linkedin_account_id"],
            require_account=bool(next_scheduled_at),
        )
    elif "scheduled_at" in update_data and update_data["scheduled_at"] and post.linkedin_account_id is None:
        update_data["linkedin_account_id"] = await resolve_post_account_id(
            db,
            current_user.id,
            None,
            require_account=True,
        )

    for field, value in update_data.items():
        setattr(post, field, value)

    # Auto-update status if scheduled_at is set/removed
    if "scheduled_at" in update_data and update_data["scheduled_at"]:
        post.status = PostStatus.SCHEDULED
    elif "scheduled_at" in update_data and update_data["scheduled_at"] is None and post.status == PostStatus.SCHEDULED:
        post.status = PostStatus.DRAFT

    return post


@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    result = await db.execute(
        select(Post).where(Post.id == post_id, Post.user_id == current_user.id)
    )
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found.")
    if post.status == PostStatus.PUBLISHED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a published post.",
        )
    await db.delete(post)
