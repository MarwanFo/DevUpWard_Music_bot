from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Strongly-typed application settings loaded from environment variables and .env file.
    Validates presence and format of required API credentials.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Discord Credentials
    DISCORD_BOT_TOKEN: str = Field(
        default="",
        description="Discord Bot Token from Discord Developer Portal"
    )
    DEV_GUILD_ID: Optional[int] = Field(
        default=None,
        description="Optional Guild ID for instant slash command registration during development"
    )

    # Spotify Credentials
    SPOTIPY_CLIENT_ID: str = Field(
        default="",
        description="Spotify App Client ID"
    )
    SPOTIPY_CLIENT_SECRET: str = Field(
        default="",
        description="Spotify App Client Secret"
    )

    # Audio & Voice Settings
    FFMPEG_PATH: str = Field(
        default="ffmpeg",
        description="Path to the ffmpeg executable"
    )
    DEFAULT_VOLUME: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Default playback volume in percent (0 to 100)"
    )
    IDLE_TIMEOUT_SECONDS: int = Field(
        default=300,
        ge=30,
        description="Seconds of inactivity before the bot leaves the voice channel (default 5 min)"
    )

    # Logging
    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )

    @field_validator("DISCORD_BOT_TOKEN", "SPOTIPY_CLIENT_ID", "SPOTIPY_CLIENT_SECRET", mode="before")
    @classmethod
    def clean_tokens(cls, v: Optional[str]) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def validate_production_readiness(self) -> list[str]:
        """
        Returns a list of missing or placeholder configuration warnings/errors.
        """
        errors = []
        placeholders = {
            "your_discord_bot_token_here",
            "your_spotify_client_id_here",
            "your_spotify_client_secret_here",
            ""
        }

        if self.DISCORD_BOT_TOKEN in placeholders:
            errors.append("DISCORD_BOT_TOKEN is missing or contains placeholder.")
        if self.SPOTIPY_CLIENT_ID in placeholders:
            errors.append("SPOTIPY_CLIENT_ID is missing or contains placeholder.")
        if self.SPOTIPY_CLIENT_SECRET in placeholders:
            errors.append("SPOTIPY_CLIENT_SECRET is missing or contains placeholder.")

        return errors


settings = Settings()

