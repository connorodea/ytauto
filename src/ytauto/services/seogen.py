"""SEO metadata generation using Claude or OpenAI."""

from __future__ import annotations

import json
import re

import anthropic
import openai

from ytauto.config.settings import Settings


def _extract_json(text: str) -> dict:
    """Extract JSON from text that may contain markdown code fences."""
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

    raise json.JSONDecodeError("No valid JSON found in response", text, 0)

SYSTEM_PROMPT = """\
You are a YouTube SEO expert. You optimize video metadata for maximum \
discoverability, click-through rate, and algorithm performance.

You MUST respond with valid JSON only — no markdown, no commentary."""

USER_PROMPT_TEMPLATE = """\
Generate optimized YouTube SEO metadata for a video about: {topic}

The video title is: {title}
The video has these sections: {section_headings}

Return a JSON object:
{{
  "title": "SEO-optimized title (under 70 chars, keyword-rich, curiosity-driven)",
  "description": "Full YouTube description (300-500 words). Include:\\n- Hook paragraph\\n- Video summary with timestamps\\n- Relevant keywords naturally woven in\\n- Call to action\\n- Related topics/hashtags at the end",
  "tags": ["15-20 highly relevant tags, mix of broad and specific"],
  "hashtags": ["3-5 hashtags for the description"]
}}"""


def generate_seo(
    topic: str,
    title: str,
    section_headings: list[str],
    engine: str = "claude",
    settings: Settings | None = None,
) -> dict:
    """Generate SEO-optimized metadata for a YouTube video."""
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    user_prompt = USER_PROMPT_TEMPLATE.format(
        topic=topic,
        title=title,
        section_headings=", ".join(section_headings),
    )

    if engine == "claude" and settings.has_anthropic():
        return _generate_claude(user_prompt, settings)
    elif settings.has_openai():
        return _generate_openai(user_prompt, settings)
    elif settings.has_anthropic():
        return _generate_claude(user_prompt, settings)
    else:
        raise RuntimeError("No LLM API key configured. Run 'ytauto setup'.")


def _generate_claude(prompt: str, settings: Settings) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_json(message.content[0].text)


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
