from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.session import Base


class PostStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


class PostTone(str, enum.Enum):
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    STORYTELLING = "storytelling"
    BOLD = "bold"
    EDUCATIONAL = "educational"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    linkedin_account_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("linkedin_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # LinkedIn post ID returned after successful publish (for analytics later)
    linkedin_post_id: Mapped[str] = mapped_column(String(255), nullable=True)

    # Status lifecycle: draft → scheduled → published | failed
    status: Mapped[PostStatus] = mapped_column(
        SAEnum(PostStatus), default=PostStatus.DRAFT, index=True
    )

    # Scheduling
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # AI metadata
    ai_generated: Mapped[bool] = mapped_column(default=False)
    ai_tone: Mapped[str] = mapped_column(
        SAEnum(PostTone), nullable=True
    )
    ai_enhanced: Mapped[bool] = mapped_column(default=False)
    # ai_enhanced = True means user wrote it but toggled "enhance before posting"

    # Error tracking
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="posts")
    linkedin_account: Mapped["LinkedInAccount"] = relationship(
        "LinkedInAccount", back_populates="posts"
    )

    analytics:Mapped['Analytics'] = relationship("PostAnalytics", back_populates="post", uselist=False)

    def __repr__(self) -> str:
        return f"<Post id={self.id} status={self.status} scheduled_at={self.scheduled_at}>"
