"""
AI Prompt Builder
------------------
Builds the system + user prompt sent to the LLM for LinkedIn post generation.
Kept separate from ai_service.py so prompt tuning doesn't touch API logic.
"""

from app.models.post import PostTone

# Approximate character targets per length option
LENGTH_TARGETS = {
    "short": "under 300 characters — a punchy, single-idea post",
    "standard": "between 300 and 1000 characters — a well-developed post with a clear narrative arc",
    "long": "over 1000 characters — a long-form post with multiple paragraphs, like a mini-article",
}

TONE_GUIDANCE = {
    PostTone.PROFESSIONAL: "polished, credible, and business-appropriate — suitable for a corporate audience",
    PostTone.CASUAL: "conversational and relaxed, like talking to a colleague over coffee",
    PostTone.STORYTELLING: "narrative-driven, opening with a hook, building tension, landing on a takeaway",
    PostTone.BOLD: "confident, opinionated, and a little provocative — designed to spark discussion",
    PostTone.EDUCATIONAL: "clear and instructive, breaking down a concept step by step",
}


def build_system_prompt() -> str:
    return (
        "You are an expert LinkedIn ghostwriter. You write posts that get high engagement "
        "without sounding like generic corporate marketing. You avoid clichés like "
        "'In today's fast-paced world' or 'I'm excited to announce'. You write the way "
        "real, respected professionals write — direct, specific, and with a clear point of view. "
        "Output ONLY the post content. No preamble, no explanation, no markdown formatting, "
        "no quotation marks around the output."
    )


def build_user_prompt(
    topic: str,
    tone: PostTone,
    length: str,
    include_hashtags: bool,
    include_emoji: bool,
) -> str:
    tone_desc = TONE_GUIDANCE.get(tone, TONE_GUIDANCE[PostTone.PROFESSIONAL])
    length_desc = LENGTH_TARGETS.get(length, LENGTH_TARGETS["standard"])

    instructions = [
        f"Write a LinkedIn post about: {topic}",
        f"Tone: {tone_desc}.",
        f"Length: {length_desc}.",
    ]

    if include_hashtags:
        instructions.append(
            "End with 2-4 relevant, specific hashtags (not generic ones like #motivation)."
        )
    else:
        instructions.append("Do not include any hashtags.")

    if include_emoji:
        instructions.append("You may use 1-3 emojis naturally where they add emphasis.")
    else:
        instructions.append("Do not use any emojis.")

    instructions.append(
        "Use line breaks between ideas for readability, as is standard for LinkedIn posts."
    )

    return "\n".join(instructions)
