"""Script generation service using Claude or OpenAI."""

from __future__ import annotations

import json
import re

import anthropic
import openai

from ytauto.config.settings import Settings
from ytauto.services.retry import retry


def _extract_json(text: str) -> dict:
    """Extract JSON from text that may contain markdown code fences."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return json.loads(text[start:end])

    raise json.JSONDecodeError("No valid JSON found in response", text, 0)

# Duration presets: (target_minutes, section_count, words_approx)
DURATION_PRESETS = {
    "short": (5, 4, 750),
    "medium": (10, 6, 1500),
    "long": (18, 8, 2700),
}

SYSTEM_PROMPT = """\
You are an expert YouTube scriptwriter who creates highly engaging, \
retention-optimized video scripts. You write scripts that hook viewers \
in the first 10 seconds and maintain tension throughout.

You MUST respond with valid JSON only — no markdown, no commentary."""

USER_PROMPT_TEMPLATE = """\
Write a YouTube video script about: {topic}

Target duration: ~{minutes} minutes ({words} words)
Number of sections: {sections}

Return a JSON object with this exact structure:
{{
  "title": "compelling YouTube title (under 70 chars, curiosity-driven)",
  "hook": "the first 10-second hook — shocking statement or question",
  "sections": [
    {{
      "heading": "section title",
      "narration": "the full narration text for this section",
      "visual_prompt": "a detailed image generation prompt for the visual accompanying this section (cinematic, 16:9, dark dramatic lighting)"
    }}
  ],
  "outro": "closing statement with call to action (subscribe, like, comment)",
  "description": "YouTube video description (2-3 paragraphs, SEO-optimized, include relevant keywords)",
  "tags": ["tag1", "tag2", "tag3", "...up to 15 relevant tags"]
}}

Requirements:
- Hook must create immediate curiosity or shock
- Each section should end with a mini-cliffhanger or transition
- Narration should be conversational but authoritative
- Visual prompts should be detailed enough for AI image generation
- Title should trigger curiosity gap
- Description should be SEO-optimized with natural keyword usage
- Tags should cover primary topic, related topics, and trending terms"""


def generate_script(
    topic: str,
    duration: str = "medium",
    engine: str = "claude",
    settings: Settings | None = None,
    channel_context: str | None = None,
) -> dict:
    """Generate a video script using AI.

    Args:
        channel_context: Optional channel profile context to inject into the prompt
            for brand-consistent voice and style.

    Returns a dict with: title, hook, sections, outro, description, tags.
    """
    if settings is None:
        from ytauto.config.settings import get_settings
        settings = get_settings()

    minutes, sections, words = DURATION_PRESETS.get(duration, DURATION_PRESETS["medium"])

    user_prompt = USER_PROMPT_TEMPLATE.format(
        topic=topic, minutes=minutes, words=words, sections=sections
    )

    if channel_context:
        user_prompt += f"\n\nChannel context (match this brand voice):\n{channel_context}"

    if engine == "claude" and settings.has_anthropic():
        return _generate_claude(user_prompt, settings)
    elif settings.has_openai():
        return _generate_openai(user_prompt, settings)
    elif settings.has_anthropic():
        return _generate_claude(user_prompt, settings)
    else:
        raise RuntimeError(
            "No LLM API key configured. Run 'ytauto setup' to add your API keys."
        )


@retry(max_attempts=3)
def _generate_claude(prompt: str, settings: Settings) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text
    return _extract_json(raw)


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
        max_tokens=4096,
    )
    raw = response.choices[0].message.content
    return _extract_json(raw)
