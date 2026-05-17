"""Application configuration — the SOLE consumer of ``os.environ``.

Every other module in the project reads configuration via::

    from app.config import settings
    settings.DATABASE_URL  # etc.

This invariant is enforced at CI time by ``tests/test_no_direct_env.py``
(FOUND-10 in REQUIREMENTS.md). If you find yourself reaching for ``os.environ``
elsewhere, add a typed field here instead — that's the 4-step procedure
documented in CLAUDE.md §"Adding a new env var".

The ``.env.example`` file in the repo root documents every field below with a
one-liner generation hint; ``tests/test_env_example.py`` enforces parity
between this class and that file (FOUND-09).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables / ``.env``.

    All fields are read from process environment with optional ``.env`` file
    overlay (development convenience; production sets real env vars via
    ``docker-compose.yml``). ``extra="forbid"`` rejects unknown env keys at
    startup — a tampering defense (threat T-00-01-04) and a typo guard.
    """

    # --- Postgres connection (required; no defaults) ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    DATABASE_URL: str  # expected shape: postgresql+psycopg://USER:PASS@coffee-snobbery-db:5432/DB

    # --- App secrets (required; no defaults — Phase 0 will not start without them) ---
    # 64-byte token_urlsafe encoded → 86 base64-url chars; we accept >=32 to keep
    # the boundary loose for test fixtures while still rejecting empty / weak values.
    APP_SECRET_KEY: str = Field(..., min_length=32)
    # Comma-separated list of Fernet keys. First = primary for encryption;
    # all attempted for decryption. Phase 0 stores raw string; Phase 3
    # parses + builds the MultiFernet (CONTEXT.md <specifics>, decision D-18).
    APP_ENCRYPTION_KEY: str

    # --- Proxy / runtime defaults ---
    TRUSTED_PROXY_IPS: str = "127.0.0.1"  # comma-separated; consumed by uvicorn --forwarded-allow-ips
    APP_TIMEZONE: str = "America/Chicago"  # IANA; consumed by APScheduler (Phase 8)
    BACKUP_RETENTION_DAYS: int = 14  # consumed by Phase 8 backup job

    # --- Logging (CONTEXT D-16) ---
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


settings = Settings()  # type: ignore[call-arg]
# ``settings`` is the canonical singleton. Importers do
# ``from app.config import settings`` — never instantiate Settings() elsewhere.
