"""
LinkedIn OAuth Endpoints
------------------------
GET  /api/v1/linkedin/connect           → Returns the LinkedIn auth URL for the frontend to redirect to
GET  /api/v1/linkedin/callback          → LinkedIn redirects here after user authorizes
GET  /api/v1/linkedin/accounts          → List all connected LinkedIn accounts
DELETE /api/v1/linkedin/accounts/{id}  → Disconnect an account
PATCH /api/v1/linkedin/accounts/{id}/default → Set as default posting account
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.deps import get_current_active_user
from app.core.config import settings
from app.models.user import User
from app.schemas.linkedin import LinkedInAccountOut, SetDefaultAccount
from app.services.linkedin_service import (
    build_linkedin_auth_url,
    validate_oauth_state,
    exchange_code_for_tokens,
    fetch_linkedin_profile,
    save_linkedin_account,
    get_user_accounts,
    disconnect_account,
    set_default_account,
)

router = APIRouter(prefix="/linkedin", tags=["linkedin"])


# ── Step 1: Initiate OAuth ────────────────────────────────────────────────────
@router.get("/connect")
async def connect_linkedin(
    current_user: User = Depends(get_current_active_user),
):
    """
    Returns the LinkedIn authorization URL.
    Frontend should redirect the user to this URL.

    Example frontend usage:
        const res = await fetch('/api/v1/linkedin/connect', { headers: { Authorization: ... } })
        const { auth_url } = await res.json()
        window.location.href = auth_url
    """
    auth_url = build_linkedin_auth_url(user_id=current_user.id)
    return {"auth_url": auth_url}


# ── Step 2: Handle OAuth callback from LinkedIn ───────────────────────────────
@router.get("/callback")
async def linkedin_callback(
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
    db: AsyncSession = Depends(get_db),
):
    """
    LinkedIn redirects here after the user grants (or denies) permission.

    Query params LinkedIn sends:
      - code:  authorization code (on success)
      - state: our CSRF state token we sent in Step 1
      - error: present if user denied or something went wrong
      - error_description: human-readable error

    On success: redirects to frontend /accounts page.
    On failure: redirects to frontend /accounts?error=... page.
    """
    # Handle user denying access or LinkedIn error
    if error:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/accounts?error={error_description or error}"
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/accounts?error=missing_code_or_state"
        )

    # Validate the CSRF state token → get the user_id
    user_id = validate_oauth_state(state)

    # Exchange the authorization code for tokens
    token_data = await exchange_code_for_tokens(code)

    # Fetch the user's LinkedIn profile using the new access token
    profile = await fetch_linkedin_profile(token_data["access_token"])

    # Save (or update) the account with encrypted tokens
    await save_linkedin_account(db, user_id, token_data, profile)

    # Redirect user back to the frontend accounts page — connected successfully
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/accounts?connected=true"
    )


# ── Account Management ────────────────────────────────────────────────────────
@router.get("/accounts", response_model=list[LinkedInAccountOut])
async def list_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all LinkedIn accounts connected to the current user."""
    return await get_user_accounts(db, current_user.id)


@router.delete("/accounts/{account_id}", status_code=204)
async def disconnect(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Disconnect a LinkedIn account.
    If it was the default, the next account is automatically promoted.
    """
    await disconnect_account(db, account_id, current_user.id)


@router.patch("/accounts/{account_id}/default", response_model=LinkedInAccountOut)
async def set_default(
    account_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Set a specific LinkedIn account as the default for new posts."""
    return await set_default_account(db, account_id, current_user.id)
