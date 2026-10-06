from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from app.models.post import PostStatus, PostTone


class PostCreate(BaseModel):
    content: str
    linkedin_account_id: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    ai_enhanced: bool = False

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Post content cannot be empty.")
        if len(v) > 3000:
            raise ValueError("LinkedIn posts cannot exceed 3000 characters.")
        return v


class PostUpdate(BaseModel):
    content: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    linkedin_account_id: Optional[int] = None
    ai_enhanced: Optional[bool] = None


class PostOut(BaseModel):
    id: int
    content: str
    status: PostStatus
    scheduled_at: Optional[datetime]
    published_at: Optional[datetime]
    linkedin_account_id: Optional[int]
    linkedin_post_id: Optional[str]
    error_message: Optional[str]
    retry_count: int
    ai_generated: bool
    ai_tone: Optional[PostTone]
    created_at: datetime

    model_config = {"from_attributes": True}


class AIGenerateRequest(BaseModel):
    topic: str
    tone: PostTone = PostTone.PROFESSIONAL
    length: str = "standard"   # short | standard | long
    include_hashtags: bool = True
    include_emoji: bool = False

    @field_validator("length")
    @classmethod
    def valid_length(cls, v: str) -> str:
        if v not in ("short", "standard", "long"):
            raise ValueError("length must be 'short', 'standard', or 'long'.")
        return v


class AIGenerateResponse(BaseModel):
    content: str
    tone: str
    char_count: int


class AIEnhanceRequest(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Content cannot be empty.")
        if len(v) > 3000:
            raise ValueError("Content cannot exceed 3000 characters.")
        return v


class AIRegenerateRequest(BaseModel):
    topic: str
    tone: PostTone = PostTone.PROFESSIONAL
    length: str = "standard"
    include_hashtags: bool = True
    include_emoji: bool = False
    previous_content: str

    @field_validator("length")
    @classmethod
    def valid_length(cls, v: str) -> str:
        if v not in ("short", "standard", "long"):
            raise ValueError("length must be 'short', 'standard', or 'long'.")
        return v
