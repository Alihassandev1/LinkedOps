from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class LinkedInAccountOut(BaseModel):
    """What we return to the frontend for each connected account."""
    id: int
    linkedin_id: str
    name: str
    email: Optional[str]
    profile_picture_url: Optional[str]
    headline: Optional[str]
    is_active: bool
    is_default: bool
    token_expires_at: Optional[datetime]
    connected_at: datetime
    last_used_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SetDefaultAccount(BaseModel):
    account_id: int


class LinkedInOAuthState(BaseModel):
    """
    We encode this as a signed JWT and pass it as 'state' in the OAuth redirect.
    LinkedIn returns it back on callback — we decode it to get the user_id.
    This prevents CSRF attacks on the OAuth flow.
    """
    user_id: int
