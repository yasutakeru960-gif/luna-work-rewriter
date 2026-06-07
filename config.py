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


# === Anthropic / OpenAI API keys ===
ANTHROPIC_API_KEY = _get_secret("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")

# === Claude model ===
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MAX_TOKENS = 64000  # Total budget (thinking + output)
CLAUDE_THINKING_BUDGET = 8000  # Tokens reserved for thinking

# === OpenAI image model (gpt-image-2, released 2026-04-21) ===
OPENAI_IMAGE_MODEL = "gpt-image-2"
OPENAI_IMAGE_QUALITY = "high"
OPENAI_IMAGE_HERO_SIZE = "1536x1024"
OPENAI_IMAGE_FIGURE_SIZE = "1536x1024"

# === Character reference asset ===
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
CHARACTER_REFERENCE_PATH = ASSETS_DIR / "character_reference.png"


# === Multi-site WordPress configuration ===
# Each entry defines a publishing destination. The primary site keeps the
# original WP_URL / WP_USERNAME / WP_APP_PASSWORD secret names for backward
# compatibility; the additional sites use suffixed secret names so a single
# Streamlit Cloud Secrets file can hold credentials for every site.
WP_SITES = [
    {
        "id": "reviwviw",
        "label": "reviwviw.jp (本番)",
        "default_url": "https://reviwviw.jp",
        "url_secret": "WP_URL",
        "username_secret": "WP_USERNAME",
        "password_secret": "WP_APP_PASSWORD",
    },
    {
        "id": "mixpost",
        "label": "mixpost.net (旧サイト)",
        "default_url": "https://mixpost.net",
        "url_secret": "WP_URL_MIXPOST",
        "username_secret": "WP_USERNAME_MIXPOST",
        "password_secret": "WP_APP_PASSWORD_MIXPOST",
    },
]


def _get_current_site_id() -> str:
    """Look up the active site id from Streamlit session_state, else default."""
    try:
        import streamlit as st
        sid = st.session_state.get("wp_site_id")
        if sid and any(s["id"] == sid for s in WP_SITES):
            return sid
    except Exception:
        pass
    return WP_SITES[0]["id"]


def _resolve_site(site_id: str) -> dict:
    for s in WP_SITES:
        if s["id"] == site_id:
            return {
                "id": s["id"],
                "label": s["label"],
                "url": _get_secret(s["url_secret"]) or s["default_url"],
                "username": _get_secret(s["username_secret"]),
                "password": _get_secret(s["password_secret"]),
            }
    return _resolve_site(WP_SITES[0]["id"])


def _get_current_site() -> dict:
    return _resolve_site(_get_current_site_id())


def list_wp_sites() -> list[dict]:
    """List configured sites with the URL each one would currently use.

    Used by the sidebar selector. Returns:
        [{"id", "label", "url"}, ...]
    """
    return [
        {
            "id": s["id"],
            "label": s["label"],
            "url": _get_secret(s["url_secret"]) or s["default_url"],
        }
        for s in WP_SITES
    ]


# Module-level __getattr__ — every access to e.g. config.WP_URL is routed
# through _get_current_site() so wordpress.py keeps using config.WP_URL etc.
# unchanged while transparently respecting the active selection.
def __getattr__(name):
    if name == "WP_URL":
        return _get_current_site()["url"]
    if name == "WP_USERNAME":
        return _get_current_site()["username"]
    if name == "WP_APP_PASSWORD":
        return _get_current_site()["password"]
    if name == "WP_REST_BASE":
        return f"{_get_current_site()['url']}/wp-json/wp/v2"
    if name == "WP_POSTS_ENDPOINT":
        return f"{_get_current_site()['url']}/wp-json/wp/v2/posts"
    if name == "WP_MEDIA_ENDPOINT":
        return f"{_get_current_site()['url']}/wp-json/wp/v2/media"
    raise AttributeError(name)


def validate_config() -> list[str]:
    """Return list of missing config items. Empty list = all good."""
    errors = []
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY が設定されていません")
    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY が設定されていません")
    current = _get_current_site()
    if not current["username"]:
        errors.append(
            f"{current['label']} の WP_USERNAME が設定されていません"
            " (Secrets を確認してください)"
        )
    if not current["password"]:
        errors.append(
            f"{current['label']} の WP_APP_PASSWORD が設定されていません"
            " (Secrets を確認してください)"
        )
    return errors
