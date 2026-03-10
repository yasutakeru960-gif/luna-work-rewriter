import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, override=True)

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY")

# WordPress
WP_URL = "https://mixpost.net"
WP_REST_BASE = f"{WP_URL}/wp-json/wp/v2"
WP_POSTS_ENDPOINT = f"{WP_REST_BASE}/posts"
WP_MEDIA_ENDPOINT = f"{WP_REST_BASE}/media"
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

# Claude Model
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 32000  # Total budget (thinking + output)
CLAUDE_THINKING_BUDGET = 8000  # Tokens reserved for thinking

# Gemini Image Model (Nano Banana 2 = Gemini 3.1 Flash Image)
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview"

# Image settings
IMAGES_PER_ARTICLE = 3


def validate_config() -> list[str]:
    """Return list of missing config items. Empty list = all good."""
    errors = []
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY が設定されていません")
    if not GOOGLE_AI_API_KEY:
        errors.append("GOOGLE_AI_API_KEY が設定されていません")
    if not WP_USERNAME:
        errors.append("WP_USERNAME が設定されていません")
    if not WP_APP_PASSWORD:
        errors.append("WP_APP_PASSWORD が設定されていません")
    return errors
