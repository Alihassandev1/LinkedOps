from fastapi import APIRouter
from app.api.v1.endpoints import auth, posts, linkedin, ai, scheduler, analytics

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(posts.router)
api_router.include_router(linkedin.router)
api_router.include_router(ai.router)
api_router.include_router(scheduler.router)
api_router.include_router(analytics.router)

# Future routers (uncomment as you build them):
# from app.api.v1.endpoints import analytics
# api_router.include_router(analytics.router)
