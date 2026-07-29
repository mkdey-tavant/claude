"""Application configuration, loaded from environment variables (prefix ``SAM_``)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings. Every field can be overridden via ``SAM_<NAME>`` env vars."""

    model_config = SettingsConfigDict(
        env_prefix="SAM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    cache_ttl_seconds: int = 900
    cache_maxsize: int = 256
    default_market: str = "NSE"
    max_retries: int = 3
    history_days: int = 400
    risk_free_rate: float = 0.07

    # yfinance can be flaky; keep per-call timeouts modest so tools stay responsive.
    request_timeout_seconds: int = 20


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of :class:`Settings`."""
    return Settings()
