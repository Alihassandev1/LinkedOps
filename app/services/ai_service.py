"""
AI Content Generation Service
-------------------------------
Uses OpenRouter (OpenAI-compatible API) to generate LinkedIn post content.

Two entry points:
  1. generate_post_content()  → topic/tone/length → full new post (AI Writer page)
  2. enhance_post_content()   → existing draft → polished version (the "AI Enhance" toggle)

Both deduct from user.ai_credits. 1 generation = 1 credit.
"""

from openai import AsyncOpenAI
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.post import PostTone
from app.services.ai_prompt_builder import build_system_prompt, build_user_prompt

# OpenRouter exposes an OpenAI-compatible API — we just point the base_url at it.
_client = AsyncOpenAI(
    api_key=settings.OPENROUTER_API_KEY,
    base_url=settings.OPENROUTER_BASE_URL,
)


# ── Credit management ─────────────────────────────────────────────────────────
def _check_and_reserve_credit(user: User) -> None:
    """
    Raise 402 if the user has no AI credits left.
    Call this BEFORE making the API call so we don't waste a request
    on a user who can't afford it.
    """
    if user.plan == "agency":
        return  # Unlimited plan — no credit check needed

    if user.ai_credits <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="You're out of AI credits. Upgrade your plan or wait for next month's reset.",
        )


def _deduct_credit(user: User) -> None:
    """Deduct one credit after a successful generation. No-op for agency plan."""
    if user.plan != "agency":
        user.ai_credits -= 1


# ── Core generation call ──────────────────────────────────────────────────────
async def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Make the actual call to OpenRouter.
    Raises 502 if the AI provider fails or returns something unusable.
    """
    try:
        response = await _client.chat.completions.create(
            model=settings.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,   # Some creativity, but not wildly random
            max_tokens=800,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI generation failed: {str(e)}",
        )

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI returned an empty response. Please try again.",
        )

    return content.strip()


# ── Public: Generate a new post from a topic ──────────────────────────────────
async def generate_post_content(
    db: AsyncSession,
    user: User,
    topic: str,
    tone: PostTone,
    length: str,
    include_hashtags: bool,
    include_emoji: bool,
) -> str:
    """
    Generate a brand new LinkedIn post from a topic.
    Used by the AI Writer page.
    """
    _check_and_reserve_credit(user)

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(topic, tone, length, include_hashtags, include_emoji)

    content = await _call_llm(system_prompt, user_prompt)

    _deduct_credit(user)
    await db.flush()

    return content


# ── Public: Enhance an existing draft ─────────────────────────────────────────
async def enhance_post_content(
    db: AsyncSession,
    user: User,
    draft_content: str,
) -> str:
    """
    Take a user-written draft and polish grammar, tone, and structure
    WITHOUT changing the core message. Used by the "Enhance with AI" toggle
    on the Schedule page.
    """
    _check_and_reserve_credit(user)

    system_prompt = (
        "You are an expert LinkedIn editor. You improve grammar, clarity, flow, and "
        "formatting of LinkedIn posts WITHOUT changing the author's core message, voice, "
        "or intent. You do not add new claims or change the meaning. "
        "Output ONLY the improved post content. No preamble, no explanation."
    )
    user_prompt = (
        f"Improve this LinkedIn post draft. Fix grammar, improve readability with line "
        f"breaks, and tighten the wording. Keep the same message and length roughly the same:\n\n"
        f"{draft_content}"
    )

    content = await _call_llm(system_prompt, user_prompt)

    _deduct_credit(user)
    await db.flush()

    return content


# ── Regeneration (variation of the same topic) ────────────────────────────────
async def regenerate_post_content(
    db: AsyncSession,
    user: User,
    topic: str,
    tone: PostTone,
    length: str,
    include_hashtags: bool,
    include_emoji: bool,
    previous_content: str,
) -> str:
    """
    Generate a DIFFERENT variation for the same topic.
    Used by the "Regenerate" button in the AI Writer output.
    """
    _check_and_reserve_credit(user)

    system_prompt = build_system_prompt()
    base_prompt = build_user_prompt(topic, tone, length, include_hashtags, include_emoji)
    user_prompt = (
        f"{base_prompt}\n\n"
        f"IMPORTANT: Write a DIFFERENT angle or opening than this previous version "
        f"(don't repeat its structure or phrasing):\n\n{previous_content}"
    )

    content = await _call_llm(system_prompt, user_prompt)

    _deduct_credit(user)
    await db.flush()

    return content
