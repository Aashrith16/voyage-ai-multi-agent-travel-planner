"""Shared Gemini model configuration for VoyageAI agents."""

import os

from dotenv import load_dotenv


load_dotenv()

DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


def get_gemini_model() -> str:
    """Return the configured Gemini model, falling back to the verified default."""

    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
