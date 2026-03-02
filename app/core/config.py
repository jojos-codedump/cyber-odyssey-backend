import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Dict, Any

class Settings(BaseSettings):
    """
    Centralized configuration management for the FastAPI backend.
    Reads securely from the .env file locally, and from Render's Environment Variables in production.
    """
    PROJECT_NAME: str = "Cyber Odyssey 2.0 API"
    VERSION: str = "1.0.0"
    
    # ---------------------------------------------------------
    # FIREBASE CONFIGURATION
    # ---------------------------------------------------------
    FIREBASE_SERVICE_ACCOUNT_KEY: str

    # ---------------------------------------------------------
    # EMAIL SERVICE CONFIGURATION
    # ---------------------------------------------------------
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SENDER_EMAIL: str
    SENDER_PASSWORD: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" 
    )

    def get_firebase_credentials_dict(self) -> Dict[str, Any]:
        """
        Parses the raw JSON string from the environment variable back into a Python dictionary.
        This dictionary is then passed directly to the Firebase Admin SDK for initialization.
        """
        try:
            return json.loads(self.FIREBASE_SERVICE_ACCOUNT_KEY)
        except json.JSONDecodeError as e:
            raise ValueError(
                "CRITICAL: FIREBASE_SERVICE_ACCOUNT_KEY is not a valid JSON string. "
                "Ensure you have copied the exact contents of your serviceAccountKey.json file."
            ) from e

@lru_cache()
def get_settings() -> Settings:
    """Returns the singleton instance of the application settings."""
    return Settings()