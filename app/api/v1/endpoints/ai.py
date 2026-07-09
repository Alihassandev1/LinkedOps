"""
AI Content Generation Endpoints
---------------------------------
POST /api/v1/ai/generate    → New post from a topic (AI Writer page)
POST /api/v1/ai/enhance     → Polish an existing draft (Schedule page toggle)
POST /api/v1/ai/regenerate  → New variation of a previous generation

All endpoints deduct 1 AI credit per call (except 'agency' plan users).
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.deps import get_current_active_user
from app.models.user import User
from app.schemas.post import (
    AIGenerateRequest,
    AIGenerateResponse,
    AIEnhanceRequest,
    AIRegenerateRequest,
)
from app.services.ai_service import (
    generate_post_content,
    enhance_post_content,
    regenerate_post_content,
)

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate", response_model=AIGenerateResponse)
async def generate(
    data: AIGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate a new LinkedIn post from a topic.
    Costs 1 AI credit. Returns 402 if the user is out of credits.
    """
    content = await generate_post_content(
        db=db,
        user=current_user,
        topic=data.topic,
        tone=data.tone,
        length=data.length,
        include_hashtags=data.include_hashtags,
        include_emoji=data.include_emoji,
    )
    return AIGenerateResponse(
        content=content,
        tone=data.tone.value,
        char_count=len(content),
    )


@router.post("/enhance", response_model=AIGenerateResponse)
async def enhance(
    data: AIEnhanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Polish grammar, tone, and structure of a user-written draft
    without changing its core message. Costs 1 AI credit.
    """
    content = await enhance_post_content(
        db=db,
        user=current_user,
        draft_content=data.content,
    )
    return AIGenerateResponse(
        content=content,
        tone="enhanced",
        char_count=len(content),
    )


@router.post("/regenerate", response_model=AIGenerateResponse)
async def regenerate(
    data: AIRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Generate a different variation for the same topic.
    Costs 1 AI credit.
    """
    content = await regenerate_post_content(
        db=db,
        user=current_user,
        topic=data.topic,
        tone=data.tone,
        length=data.length,
        include_hashtags=data.include_hashtags,
        include_emoji=data.include_emoji,
        previous_content=data.previous_content,
    )
    return AIGenerateResponse(
        content=content,
        tone=data.tone.value,
        char_count=len(content),
    )
