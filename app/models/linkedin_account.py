from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class LinkedInAccount(Base):
    __tablename__ = "linkedin_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # LinkedIn profile info (fetched after OAuth)
    linkedin_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    profile_picture_url: Mapped[str] = mapped_column(Text, nullable=True)
    headline: Mapped[str] = mapped_column(String(500), nullable=True)

    # OAuth tokens — ALWAYS stored encrypted via Fernet
    # Never store plain text tokens in the database
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Account state
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # When is_default=True, new posts use this account unless specified

    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="linkedin_accounts")
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="linkedin_account")

    def __repr__(self) -> str:
        return f"<LinkedInAccount id={self.id} name={self.name} user_id={self.user_id}>"
