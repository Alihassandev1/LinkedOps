"""
LinkedIn OAuth 2.0 Service
--------------------------
Flow:
  1. Frontend calls GET /api/v1/linkedin/connect
     → We build the LinkedIn authorization URL (with CSRF state token)
     → We return the URL; frontend redirects the user there

  2. User authorizes on LinkedIn, LinkedIn redirects to our callback URL:
     GET /api/v1/linkedin/callback?code=...&state=...
     → We validate the state (CSRF check)
     → We exchange the code for access + refresh tokens
     → We fetch the user's LinkedIn profile
     → We encrypt the tokens and save to linkedin_accounts table
     → We redirect the user back to the frontend dashboard

  3. Token refresh (runs via APScheduler daily):
     → We check accounts whose token_expires_at < now + 7 days
     → We call LinkedIn's refresh endpoint
     → We re-encrypt and update the stored tokens
"""

import httpx
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token, create_access_token, decode_token
from app.models.linkedin_account import LinkedInAccount
from jose import JWTError

# ── LinkedIn API constants ────────────────────────────────────────────────────
LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_PROFILE_URL = "https://api.linkedin.com/v2/userinfo"  # OpenID Connect endpoint

# Scopes we need:
# openid + profile + email → basic profile info
# w_member_social           → create posts on behalf of the user
LINKEDIN_SCOPES = "openid profile email w_member_social"


# ── Step 1: Build the OAuth authorization URL ─────────────────────────────────
def build_linkedin_auth_url(user_id: int) -> str:
    """
    Build the LinkedIn OAuth authorization URL.
    The 'state' param is a short-lived JWT containing the user_id.
    LinkedIn will return this exact state string on callback,
    allowing us to verify it and know which user is connecting.
    """
    # Use a short-lived JWT (10 min) as the CSRF state token
    state_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=10)
    )

    params = {
        "response_type": "code",
        "client_id": settings.LINKEDIN_CLIENT_ID,
        "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
        "scope": LINKEDIN_SCOPES,
        "state": state_token,
    }
    return f"{LINKEDIN_AUTH_URL}?{urlencode(params)}"


# ── Step 2a: Validate the state token returned by LinkedIn ───────────────────
def validate_oauth_state(state: str) -> int:
    """
    Decode the JWT state token from the callback.
    Returns the user_id if valid. Raises 400 if tampered or expired.
    """
    try:
        payload = decode_token(state)
        user_id = int(payload["sub"])
        return user_id
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state. Please try connecting again.",
        )


# ── Step 2b: Exchange authorization code for tokens ──────────────────────────
async def exchange_code_for_tokens(code: str) -> dict:
    """
    Call LinkedIn's token endpoint to exchange the authorization code
    for an access token (and optionally a refresh token).

    Returns raw token data dict from LinkedIn:
    {
        "access_token": "...",
        "expires_in": 5183999,       # seconds (~60 days)
        "refresh_token": "...",      # only if refresh_token scope granted
        "refresh_token_expires_in": 31536000,
        "token_type": "Bearer"
    }
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.LINKEDIN_REDIRECT_URI,
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LinkedIn token exchange failed: {response.text}",
        )
    return response.json()


# ── Step 2c: Fetch the LinkedIn user's profile ────────────────────────────────
async def fetch_linkedin_profile(access_token: str) -> dict:
    """
    Fetch basic profile info using the OpenID Connect /userinfo endpoint.
    Returns: { sub, name, email, picture, headline (if available) }
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            LINKEDIN_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch LinkedIn profile: {response.text}",
        )
    return response.json()


# ── Step 2d: Save or update the LinkedIn account in DB ───────────────────────
async def save_linkedin_account(
    db: AsyncSession,
    user_id: int,
    token_data: dict,
    profile: dict,
) -> LinkedInAccount:
    """
    Upsert the LinkedIn account record:
    - If this LinkedIn ID is already connected to this user → update tokens.
    - If it's new → create a new record.

    Tokens are ALWAYS stored encrypted. Never plain text.
    """
    linkedin_id = profile["sub"]  # LinkedIn's unique user identifier

    # Check if this account already exists for this user
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.linkedin_id == linkedin_id,
            LinkedInAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()

    # Calculate token expiry from expires_in (seconds)
    expires_in = token_data.get("expires_in", 5183999)  # Default ~60 days
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Encrypt both tokens before storing
    encrypted_access = encrypt_token(token_data["access_token"])
    encrypted_refresh = (
        encrypt_token(token_data["refresh_token"])
        if token_data.get("refresh_token")
        else None
    )

    if account:
        # Update existing account with fresh tokens
        account.access_token_encrypted = encrypted_access
        account.refresh_token_encrypted = encrypted_refresh
        account.token_expires_at = token_expires_at
        account.name = profile.get("name", account.name)
        account.email = profile.get("email", account.email)
        account.profile_picture_url = profile.get("picture", account.profile_picture_url)
        account.is_active = True
    else:
        # Create new account
        # If this is the user's first account, make it the default
        existing_count_result = await db.execute(
            select(LinkedInAccount).where(LinkedInAccount.user_id == user_id)
        )
        is_first_account = len(existing_count_result.scalars().all()) == 0

        account = LinkedInAccount(
            user_id=user_id,
            linkedin_id=linkedin_id,
            name=profile.get("name", "LinkedIn User"),
            email=profile.get("email"),
            profile_picture_url=profile.get("picture"),
            headline=profile.get("headline"),
            access_token_encrypted=encrypted_access,
            refresh_token_encrypted=encrypted_refresh,
            token_expires_at=token_expires_at,
            is_default=is_first_account,
        )
        db.add(account)

    await db.flush()
    return account


# ── Token refresh (called by APScheduler) ────────────────────────────────────
async def refresh_linkedin_token(db: AsyncSession, account: LinkedInAccount) -> bool:
    """
    Use the stored refresh token to get a new access token from LinkedIn.
    Called by the background scheduler before the token expires.
    Returns True if successful, False if the refresh token is also expired.
    """
    if not account.refresh_token_encrypted:
        return False  # No refresh token stored — user must reconnect manually

    try:
        refresh_token = decrypt_token(account.refresh_token_encrypted)
    except Exception:
        return False

    async with httpx.AsyncClient() as client:
        response = await client.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.LINKEDIN_CLIENT_ID,
                "client_secret": settings.LINKEDIN_CLIENT_SECRET,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15.0,
        )

    if response.status_code != 200:
        # Refresh token is likely expired — mark account as needing reconnection
        account.is_active = False
        await db.flush()
        return False

    token_data = response.json()
    expires_in = token_data.get("expires_in", 5183999)

    account.access_token_encrypted = encrypt_token(token_data["access_token"])
    if token_data.get("refresh_token"):
        account.refresh_token_encrypted = encrypt_token(token_data["refresh_token"])
    account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    account.is_active = True

    await db.flush()
    return True


# ── Account management helpers ────────────────────────────────────────────────
async def get_user_accounts(db: AsyncSession, user_id: int) -> list[LinkedInAccount]:
    result = await db.execute(
        select(LinkedInAccount)
        .where(LinkedInAccount.user_id == user_id)
        .order_by(LinkedInAccount.connected_at.desc())
    )
    return result.scalars().all()


async def get_account_by_id(
    db: AsyncSession, account_id: int, user_id: int
) -> Optional[LinkedInAccount]:
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def set_default_account(
    db: AsyncSession, account_id: int, user_id: int
) -> LinkedInAccount:
    """Set one account as default, unset all others for this user."""
    # Get all accounts for this user
    result = await db.execute(
        select(LinkedInAccount).where(LinkedInAccount.user_id == user_id)
    )
    accounts = result.scalars().all()

    target = None
    for acc in accounts:
        if acc.id == account_id:
            acc.is_default = True
            target = acc
        else:
            acc.is_default = False

    if not target:
        raise HTTPException(status_code=404, detail="Account not found.")

    await db.flush()
    return target


async def disconnect_account(
    db: AsyncSession, account_id: int, user_id: int
) -> None:
    """
    Disconnect a LinkedIn account.
    Deletes the record — user must re-authorize to reconnect.
    """
    result = await db.execute(
        select(LinkedInAccount).where(
            LinkedInAccount.id == account_id,
            LinkedInAccount.user_id == user_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found.")

    # If deleting the default, promote the next account to default
    if account.is_default:
        other_result = await db.execute(
            select(LinkedInAccount).where(
                LinkedInAccount.user_id == user_id,
                LinkedInAccount.id != account_id,
            ).limit(1)
        )
        next_account = other_result.scalar_one_or_none()
        if next_account:
            next_account.is_default = True

    await db.delete(account)
