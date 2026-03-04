import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Dict, Any


class Settings(BaseSettings):
    PROJECT_NAME: str = "Cyber Odyssey 2.0 API"
    VERSION: str = "1.0.0"

    # Firebase
    FIREBASE_SERVICE_ACCOUNT_KEY: str

    # Email — SendGrid HTTP API (replaces blocked SMTP)
    SENDGRID_API_KEY: str
    SENDGRID_FROM_EMAIL: str   # must match your Single Sender Verified address

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_firebase_credentials_dict(self) -> Dict[str, Any]:
        try:
            return json.loads(self.FIREBASE_SERVICE_ACCOUNT_KEY)
        except json.JSONDecodeError as e:
            raise ValueError("CRITICAL: FIREBASE_SERVICE_ACCOUNT_KEY is not valid JSON.") from e


@lru_cache()
def get_settings() -> Settings:
    return Settings()