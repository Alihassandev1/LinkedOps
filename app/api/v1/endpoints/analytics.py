from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.deps import get_current_active_user
from app.services.analytics_service import (
    get_post_performance, get_growth_trend, get_ai_usage_summary
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db), user=Depends(get_current_active_user)):
    return {
        "posts": await get_post_performance(db, user.id),
        "growth": await get_growth_trend(db, user.id),
        "ai_usage": await get_ai_usage_summary(db, user.id),
    }

@router.get("/posts")
async def posts(db: AsyncSession = Depends(get_db), user=Depends(get_current_active_user)):
    return await get_post_performance(db, user.id)

@router.get("/growth")
async def growth(db: AsyncSession = Depends(get_db), user=Depends(get_current_active_user)):
    return await get_growth_trend(db, user.id)

@router.get("/ai-usage")
async def ai_usage(db: AsyncSession = Depends(get_db), user=Depends(get_current_active_user)):
    return await get_ai_usage_summary(db, user.id)