from sqlalchemy import select, func
from app.models.analytics import PostAnalytics, AccountSnapshot, AIUsageLog
from app.models.post import Post

async def get_post_performance(db, user_id: str):
    result = await db.execute(
        select(Post.id, Post.content, PostAnalytics.likes, PostAnalytics.comments, PostAnalytics.shares)
        .join(PostAnalytics, Post.id == PostAnalytics.post_id)
        .where(Post.user_id == user_id)
        .order_by(PostAnalytics.captured_at.desc())
    )
    return [dict(r._mapping) for r in result.all()]

async def get_growth_trend(db, user_id: str):
    result = await db.execute(
        select(AccountSnapshot)
        .where(AccountSnapshot.user_id == user_id)
        .order_by(AccountSnapshot.captured_at.asc())
    )
    return [
        {"date": s.captured_at, "connections": s.connections, "profile_views": s.profile_views}
        for s in result.scalars().all()
    ]

async def get_ai_usage_summary(db, user_id: str):
    result = await db.execute(
        select(
            func.count(AIUsageLog.id),
            func.sum(AIUsageLog.tokens_used),
            func.avg(AIUsageLog.generation_success)
        ).where(AIUsageLog.user_id == user_id)
    )
    count, tokens, success_rate = result.one()
    return {"generations": count or 0, "tokens_used": tokens or 0, "success_rate": round((success_rate or 0) * 100, 1)}