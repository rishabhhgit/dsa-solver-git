"""
Central application configuration.

All values are loaded from environment variables (see .env.example).
Nothing here should be hardcoded to a specific deployment domain.
"""
import os
from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _strip_whitespace(cls, data):
        """
        Defensively strip leading/trailing whitespace from every string
        env var before it's assigned to a field.

        This runs regardless of source (real environment variable, .env
        file, or Docker/Render secret) so a stray pasted space in e.g.
        GEMINI_API_KEY or PUBLIC_BASE_URL can't silently turn into an
        invalid key or a malformed URL like "onrender.com /v1/...".
        Only strips values that are actually strings — non-string values
        (if any ever appear) pass through untouched.
        """
        if isinstance(data, dict):
            return {
                key: (value.strip() if isinstance(value, str) else value)
                for key, value in data.items()
            }
        return data

    # --- Admin ---
    APP_ADMIN_PASSWORD: str = "change-this"
    ADMIN_SESSION_SECRET: str = "dev-session-secret-change-this"
    ADMIN_SESSION_TTL_SECONDS: int = 3600

    # --- Public provider identity ---
    PUBLIC_BASE_URL: str = ""
    PUBLIC_MODEL_NAME: str = "dsa-solver"
    PUBLIC_PROVIDER_NAME: str = "DSA Practice Solver"

    # --- Mistral OCR (server-side only, never exposed to clients) ---
    MISTRAL_API_KEY: str = ""
    MISTRAL_OCR_MODEL: str = "mistral-ocr-latest"

    # --- Gemini solver (server-side only, never exposed to clients) ---
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = ""

    # --- Image handling ---
    MAX_IMAGES: int = 10
    MAX_IMAGE_SIZE_MB: int = 10

    # --- Timeouts ---
    REQUEST_TIMEOUT_SECONDS: int = 180

    # --- Misc ---
    ENABLE_VERIFICATION: bool = False
    ALLOWED_ORIGINS: str = ""  # comma-separated list

    # --- Storage ---
    DATA_DIR: str = "data"  # where the generated API key is persisted

    # --- Provider API key override ---
    # Optional. If set, THIS becomes the client-facing API key instead of
    # one generated on first boot and written to DATA_DIR. Use this on
    # hosts with no persistent disk (e.g. Render's free tier): the
    # filesystem is wiped on every deploy/restart there, so a
    # disk-persisted key would otherwise regenerate each time. Set this
    # once as a Render env var (e.g. to the output of
    # `python3 -c "import secrets; print('dsa_sk_' + secrets.token_urlsafe(32))"`)
    # and it will survive every redeploy since env vars aren't wiped.
    PROVIDER_API_KEY: str = ""

    @model_validator(mode="after")
    def _default_data_dir_for_vercel(self):
        """
        On Vercel, the deployed project directory is read-only at
        request time -- only `/tmp` is writable, and it's wiped between
        cold starts / separate function instances anyway. If DATA_DIR
        is still at its default ("data", meant for Docker/local use)
        and we detect we're running on Vercel (it sets VERCEL=1
        automatically, no manual config needed), redirect it to /tmp so
        the app doesn't crash trying to create a directory it can't
        write to. This doesn't change the key-stability guarantee:
        the derived-from-ADMIN_SESSION_SECRET key (see
        app/security/api_keys.py) is what actually keeps the API key
        constant across invocations, not this file cache.
        """
        if os.environ.get("VERCEL") and self.DATA_DIR == "data":
            self.DATA_DIR = "/tmp/dsa-practice-solver-data"
        return self

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
