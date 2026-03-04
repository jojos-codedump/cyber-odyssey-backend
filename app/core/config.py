import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Dict, Any


class Settings(BaseSettings):
    """
    Centralized configuration for the FastAPI backend.
    Reads from .env locally and from Render's Environment Variables in production.
    """
    PROJECT_NAME: str = "Cyber Odyssey 2.0 API"
    VERSION: str = "1.0.0"

    # ──────────────────────────────────────────────────────
    # FIREBASE
    # ──────────────────────────────────────────────────────
    FIREBASE_SERVICE_ACCOUNT_KEY: str

    # ──────────────────────────────────────────────────────
    # EMAIL — Resend HTTP API (replaces blocked SMTP)
    #
    # RESEND_API_KEY   : from resend.com → API Keys
    # RESEND_FROM_EMAIL: must be a verified sender in Resend.
    #                    Use "onboarding@resend.dev" for testing,
    #                    then swap to your verified domain address
    #                    before the live event.
    # ──────────────────────────────────────────────────────
    RESEND_API_KEY: str
    RESEND_FROM_EMAIL: str = "Cyber Odyssey 2.0 <onboarding@resend.dev>"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_firebase_credentials_dict(self) -> Dict[str, Any]:
        """
        Parses the raw JSON string from the environment variable back into
        a Python dictionary for the Firebase Admin SDK.
        """
        try:
            return json.loads(self.FIREBASE_SERVICE_ACCOUNT_KEY)
        except json.JSONDecodeError as e:
            raise ValueError(
                "CRITICAL: FIREBASE_SERVICE_ACCOUNT_KEY is not valid JSON. "
                "Ensure you copied the entire contents of serviceAccountKey.json."
            ) from e


@lru_cache()
def get_settings() -> Settings:
    """Returns the singleton Settings instance."""
    return Settings()