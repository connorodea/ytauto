"""Shorts-specific script generation — punchy, hook-driven, 30-60 second format."""

from __future__ import annotations

import json

import anthropic
import openai

from ytauto.config.settings import Settings
from ytauto.services.retry import retry

SYSTEM_PROMPT = """\
You are an expert YouTube Shorts scriptwriter. You create viral, punchy, \
hook-driven scripts optimized for 30-60 second vertical videos. \
Your scripts stop scrollers in the first 2 seconds, deliver rapid-fire value, \
and end with a strong call to action.

You MUST respond with valid JSON only — no markdown, no commentary."""

USER_PROMPT_TEMPLATE = """\
Write a YouTube Shorts script (30-60 seconds, {words} words max) about: {topic}

Return a JSON object:
{{
  "title": "viral Shorts title (under 60 chars, use CAPS for emphasis, add emoji)",
  "hook": "opening 2-second hook — shocking statement, bold claim, or provocative question that stops scrolling",
  "sections": [
    {{
      "narration": "2-3 sentences of punchy narration for this beat",
      "visual_prompt": "vertical 9:16 cinematic image prompt — dramatic, dark, high contrast, close-up or abstract"
    }}
  ],
  "outro": "strong 5-second closer — call to action (follow for more, save this)",
  "description": "Short YouTube description with hashtags",
  "tags": ["8-12 viral tags"]
}}

Requirements:
- Hook MUST be shocking, bold, or contrarian — stop the scroll
- Keep each section to 2-3 sentences max — rapid pace
- Total narration should be {words} words or less
- 3-5 sections (beats) that build tension rapidly
- Conversational but authoritative tone — like telling a secret
- End with urgency: "follow for more" or "save this before it's taken down"
- Visual prompts must be VERTICAL (portrait, 9:16) with dramatic close-ups"""


def _extract_json(text: str) -> dict:
    import re
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])
    raise json.JSONDecodeError("No valid JSON found", text, 0)


def generate_shorts_script(
    topic: str,
    target_seconds: int = 45,
    engine: str = "claude",
    settings: Settings | None = None,
    channel_context: str | None = None,
) -> dict:
    """Generate a viral YouTube Shorts script."""
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    # ~2.5 words per second for punchy delivery
    words = int(target_seconds * 2.5)

    user_prompt = USER_PROMPT_TEMPLATE.format(topic=topic, words=words)
    if channel_context:
        user_prompt += f"\n\nChannel context:\n{channel_context}"

    if engine == "claude" and settings.has_anthropic():
        return _generate_claude(user_prompt, settings)
    elif settings.has_openai():
        return _generate_openai(user_prompt, settings)
    elif settings.has_anthropic():
        return _generate_claude(user_prompt, settings)
    else:
        raise RuntimeError("No LLM API key configured. Run 'ytauto setup'.")


@retry(max_attempts=3)
def _generate_claude(prompt: str, settings: Settings) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(message.content[0].text)


@retry(max_attempts=3)
def _generate_openai(prompt: str, settings: Settings) -> dict:
    client = openai.OpenAI(api_key=settings.openai_api_key.get_secret_value())
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
    )
    return _extract_json(response.choices[0].message.content)
