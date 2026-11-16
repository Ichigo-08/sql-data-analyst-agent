
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


# Load environment variables from the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


def get_gemini_client():
    """Create and return a Gemini API client."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "Gemini API key not found. Check your project .env file."
        )

    return genai.Client(api_key=api_key)


def get_gemini_model():
    """Return the configured Gemini model name."""

    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
