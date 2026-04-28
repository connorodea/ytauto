"""Application settings loaded from environment variables and .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(Path.home() / ".ytauto" / ".env")),
        env_prefix="YTAUTO_",
        env_file_encoding="utf-8",
    )

    # --- LLM Providers ---
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    # --- TTS ---
    deepgram_api_key: SecretStr = SecretStr("")
    elevenlabs_api_key: SecretStr = SecretStr("")

    # --- Defaults ---
    default_llm_provider: Literal["claude", "openai"] = "claude"
    default_tts_provider: Literal["deepgram", "openai", "elevenlabs"] = "deepgram"
    default_tts_voice: str = "aura-orion-en"
    default_image_provider: Literal["dalle"] = "dalle"

    # --- Video Defaults ---
    default_resolution: str = "1920x1080"
    default_fps: int = 24
    default_image_duration: int = 8
    default_music_volume: float = 0.15

    # --- Paths ---
    data_dir: Path = Path.home() / ".ytauto"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    def ensure_directories(self) -> None:
        """Create all required runtime directories."""
        for d in (self.data_dir, self.jobs_dir, self.workspaces_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)

    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key.get_secret_value())

    def has_openai(self) -> bool:
        return bool(self.openai_api_key.get_secret_value())

    def has_deepgram(self) -> bool:
        return bool(self.deepgram_api_key.get_secret_value())

    def has_elevenlabs(self) -> bool:
        return bool(self.elevenlabs_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
