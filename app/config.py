"""
Weather-Advisory Support Bot configuration.

Loads settings from .env file. All external URLs and credentials
are configured here so tests can override them.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (one level above app/)
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


# --- LLM Provider ---
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# --- Open-Meteo API ---
GEOCODING_BASE_URL: str = os.getenv(
    "GEOCODING_BASE_URL", "https://geocoding-api.open-meteo.com/v1/search"
)
FORECAST_BASE_URL: str = os.getenv(
    "FORECAST_BASE_URL", "https://api.open-meteo.com/v1/forecast"
)

# --- Timeouts ---
HTTP_TIMEOUT: int = int(os.getenv("HTTP_TIMEOUT", "30"))

# --- Server ---
HOST: str = os.getenv("HOST", "127.0.0.1")
PORT: int = int(os.getenv("PORT", "8000"))

# --- Paths ---
PROJECT_ROOT: Path = _project_root
SOPS_DIR: Path = _project_root / "sops"
CONFIG_DIR: Path = _project_root / "config"
