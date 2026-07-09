"""
LinkedIn Post Publisher
-------------------------
Publishes a Post record to LinkedIn using the UGC Posts API.

LinkedIn's UGC (User Generated Content) API requires:
  - The author's URN: "urn:li:person:{linkedin_id}"
  - A valid (decrypted) access token with w_member_social scope
  - A specific JSON payload shape (shareCommentary, shareMediaCategory, visibility)

Docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api
"""

import httpx
from datetime import datetime, timezone

from app.core.security import decrypt_token
from app.models.linkedin_account import LinkedInAccount

LINKEDIN_UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
LINKEDIN_API_VERSION = "202401"  # LinkedIn requires a versioned API header


class LinkedInPublishError(Exception):
    """Raised when LinkedIn rejects or fails to process a publish request."""
    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def publish_to_linkedin(account: LinkedInAccount, content: str) -> str:
    """
    Publish a text post to LinkedIn on behalf of the given account.

    Args:
        account: The LinkedInAccount with encrypted tokens
        content: The post text to publish

    Returns:
        The LinkedIn post URN (e.g. "urn:li:share:123456789") on success.

    Raises:
        LinkedInPublishError: if the token is invalid/expired or LinkedIn rejects the post.
    """
    try:
        access_token = decrypt_token(account.access_token_encrypted)
    except Exception:
        raise LinkedInPublishError(
            "Could not decrypt stored access token. The account may need to be reconnected."
        )

    author_urn = f"urn:li:person:{account.linkedin_id}"

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
        "LinkedIn-Version": LINKEDIN_API_VERSION,
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                LINKEDIN_UGC_POSTS_URL,
                json=payload,
                headers=headers,
                timeout=20.0,
            )
        except httpx.RequestError as e:
            raise LinkedInPublishError(f"Network error reaching LinkedIn: {str(e)}")

    if response.status_code == 401:
        raise LinkedInPublishError(
            "LinkedIn access token expired or invalid. Account needs to be reconnected.",
            status_code=401,
        )
    if response.status_code == 403:
        raise LinkedInPublishError(
            "LinkedIn rejected this request — missing 'w_member_social' permission.",
            status_code=403,
        )
    if response.status_code == 429:
        raise LinkedInPublishError(
            "LinkedIn rate limit hit. Will retry later.",
            status_code=429,
        )
    if response.status_code not in (200, 201):
        raise LinkedInPublishError(
            f"LinkedIn API error ({response.status_code}): {response.text}",
            status_code=response.status_code,
        )

    # LinkedIn returns the post URN in the 'x-restli-id' response header
    post_urn = response.headers.get("x-restli-id", "")
    return post_urn
