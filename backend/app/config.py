"""Application settings loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    blizzard_client_id: str = ""
    blizzard_client_secret: str = ""
    default_region: str = "eu"


settings = Settings()
