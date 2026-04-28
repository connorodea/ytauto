"""Channel profile model for consistent brand voice across videos."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChannelProfile(BaseModel):
    """A YouTube channel profile that defines brand voice, style, and defaults."""
    id: str = "default"
    name: str = "Default Channel"
    niche: str = ""
    target_audience: str = ""
    tone: str = "authoritative"
    visual_style: str = "dark cinematic, high contrast, dramatic lighting"
    voice_profile: str = "onyx"
    content_pillars: list[str] = Field(default_factory=list)
    brand_promises: list[str] = Field(default_factory=list)
    default_duration: str = "medium"
    default_privacy: str = "private"
    intro_template: str = ""
    outro_template: str = "If this opened your eyes, smash that subscribe button and hit the bell."
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    def to_prompt_context(self) -> str:
        """Generate a context string for AI prompt injection."""
        parts = [f"Channel: {self.name}"]
        if self.niche:
            parts.append(f"Niche: {self.niche}")
        if self.target_audience:
            parts.append(f"Target Audience: {self.target_audience}")
        if self.tone:
            parts.append(f"Tone: {self.tone}")
        if self.content_pillars:
            parts.append(f"Content Pillars: {', '.join(self.content_pillars)}")
        if self.brand_promises:
            parts.append(f"Brand Promises: {', '.join(self.brand_promises)}")
        if self.outro_template:
            parts.append(f"Outro CTA: {self.outro_template}")
        return "\n".join(parts)
