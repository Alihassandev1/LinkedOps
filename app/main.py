import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router
from app.db.session import engine, Base
from app.core.scheduler import start_scheduler, stop_scheduler
import app.models  # noqa: F401 — registers all models with SQLAlchemy

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup / shutdown.
    In production, use Alembic migrations instead of create_all.
    create_all here is for local dev convenience only.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start background jobs (post publisher + token refresher).
    # Disabled during pytest runs via APP_ENV=test to avoid jobs firing
    # against the test database mid-test-suite.
    if settings.APP_ENV != "test":
        start_scheduler()

    yield

    if settings.APP_ENV != "test":
        stop_scheduler()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="LinkedIn automation SaaS — schedule posts, AI content, OAuth.",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ───────────────────────────────────────────────────────────────
    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "app": settings.APP_NAME}

    return app


app = create_app()
