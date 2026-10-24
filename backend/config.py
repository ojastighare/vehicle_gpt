"""Application configuration module for VehicleGPT."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DATABASE_PATH: str = "data/vehiclegpt.db"

    # Local AI / SLM (Ollama or llama.cpp compatible)
    USE_LOCAL_LLM: bool = False
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5:1.5b"
    LLM_TIMEOUT_SECONDS: float = 6.0

    # Analytics & Anomaly Thresholds
    BATTERY_TEMP_ALERT_THRESHOLD: float = 45.0  # °C
    ENERGY_CONSUMPTION_HIGH_THRESHOLD: float = 25.0  # kWh/100 km
    RANDOM_SEED: int = 42

    # Safety & Security
    ALLOW_RESET: bool = True
    CORS_ORIGINS: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

# Ensure base directory and data directories exist
BASE_DIR = Path(__file__).resolve().parent.parent
DB_ABSOLUTE_PATH = BASE_DIR / settings.DATABASE_PATH
DB_ABSOLUTE_PATH.parent.mkdir(parents=True, exist_ok=True)
