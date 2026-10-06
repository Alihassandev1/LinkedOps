from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, timezone
from app.db.session import Base

class PostAnalytics(Base):
    __tablename__ = "post_analytics"

    id = Column(String, primary_key=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), nullable=False)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    captured_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    post = relationship("Post", back_populates="analytics")


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    connections = Column(Integer, default=0)
    profile_views = Column(Integer, default=0)
    search_appearances = Column(Integer, default=0)
    captured_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    model_used = Column(String, nullable=False)
    tokens_used = Column(Integer, default=0)
    generation_success = Column(Integer, default=1)  # 1/0 as lightweight bool
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))