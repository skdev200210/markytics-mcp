"""Application settings, loaded from the environment (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field #type: ignore
from pydantic_settings import BaseSettings, SettingsConfigDict #type: ignore


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    product_v3_workflow_base_url: str = Field(description="Base URL for the product V3 workflow.")
    
    logs_dir: str = Field(default="logs", description="Directory to write log files to.")
    log_level: str = Field(
        default="INFO", description="Root log level: DEBUG, INFO, WARNING, ERROR, CRITICAL."
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment


settings = get_settings()