from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file (local development)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path, override=True)


def _get_secret(key: str) -> str | None:
    """Get secret from Streamlit Cloud secrets or environment variable."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key)


# API Keys
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")

# WordPress
WP_URL = "https://mixpost.net"
WP_REST_BASE = f"{WP_URL}/wp-json/wp/v2"
WP_POSTS_ENDPOINT = f"{WP_REST_BASE}/posts"
WP_MEDIA_ENDPOINT = f"{WP_REST_BASE}/media"
WP_USERNAME = _get_secret("WP_USERNAME")
WP_APP_PASSWORD = _get_secret("WP_APP_PASSWORD")

# Claude Model
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 64000  # Total budget (thinking + output)
CLAUDE_THINKING_BUDGET = 8000  # Tokens reserved for thinking

# OpenAI Image Model (gpt-image-2, released 2026-04-21)
OPENAI_IMAGE_MODEL = "gpt-image-2"
OPENAI_IMAGE_QUALITY = "high"  # low / medium / high / auto
OPENAI_IMAGE_HERO_SIZE = "1536x1024"    # Thumbnail / featured image
OPENAI_IMAGE_FIGURE_SIZE = "1536x1024"  # In-body figures / diagrams

# Character reference (used to keep the chibi character consistent across figures)
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
CHARACTER_REFERENCE_PATH = ASSETS_DIR / "character_reference.png"


def validate_config() -> list[str]:
    """Return list of missing config items. Empty list = all good."""
    errors = []
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY が設定されていません")
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY が設定されていません")
    if not WP_USERNAME:
        errors.append("WP_USERNAME が設定されていません")
    if not WP_APP_PASSWORD:
        errors.append("WP_APP_PASSWORD が設定されていません")
    return errors
