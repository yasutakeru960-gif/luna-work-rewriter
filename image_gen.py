from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from openai import OpenAI
from PIL import Image

import config

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=config.OPENAI_API_KEY)
    return _client


# ---------------------------------------------------------------------------
# Character reference — one persistent chibi character for figure consistency
# ---------------------------------------------------------------------------
#
# The first time `generate_article_images` runs, if `assets/character_reference.png`
# doesn't exist we generate it from this prompt and save it. Every subsequent
# in-body figure is generated with `images.edit(image=[character_reference])`
# so the same girl appears in every diagram.
#
# Tweak this prompt and delete the saved PNG if you want a different character.

CHARACTER_REFERENCE_PROMPT = (
    "A cute Japanese young woman character reference sheet, late teens or early twenties. "
    "Shoulder-length dark brown hair with subtle purple/violet highlights, "
    "large expressive purple eyes, friendly warm smile, light skin. "
    "Wearing a soft white hoodie over a teal/sage green inner shirt. "
    "Soft pastel anime/manga illustration style, chibi-friendly proportions, "
    "clean simple plain white background, full upper body shot facing the viewer, "
    "modern flat-shaded illustration, gentle soft purple accent colors, no text, no labels. "
    "Designed as a character reference for a Japanese women's lifestyle blog — "
    "approachable, friendly, easy to recognize, consistent silhouette."
)


# ---------------------------------------------------------------------------
# Style suffixes appended to user-provided prompts
# ---------------------------------------------------------------------------

HERO_STYLE_SUFFIX = (
    "Render this as a flashy, eye-catching Japanese-style article thumbnail / banner. "
    "Bright purple-to-lavender gradient background with sparkle and starburst particle effects. "
    "Bold dramatic Japanese typography with the article title prominently displayed in large "
    "stylized characters, using red/gold/white color accents with subtle outline and shadow. "
    "Include small decorative ribbon-style badges. "
    "Place a small cheerful chibi-style Japanese woman character in the corner as a friendly accent. "
    "Modern catchy YouTube-thumbnail / blog hero banner aesthetic. "
    "High contrast, polished, professional, suitable as the lead image of a women's lifestyle blog post. "
    "16:9 horizontal composition."
)

FIGURE_STYLE_SUFFIX = (
    "Render this as a friendly, easy-to-understand illustrated explainer diagram, "
    "in the style of a Japanese women's lifestyle blog infographic. "
    "Feature the SAME chibi-style young Japanese woman from the reference image — "
    "keep her hair color, hairstyle, outfit (white hoodie + teal/sage inner), and face style identical. "
    "She can appear in multiple poses/expressions within one image to walk through the explanation. "
    "Use rounded speech bubbles, soft purple/lavender accent colors, light pastel background, "
    "simple flat illustration style, clean labels in Japanese where appropriate, "
    "arrows and connectors to show flow, and small UI mockups (laptop screens, file icons, "
    "chat windows, progress bars) where relevant to illustrate the concept. "
    "Composition should be clear, uncluttered, and instantly readable on a phone."
)


# ---------------------------------------------------------------------------
# Output container
# ---------------------------------------------------------------------------

@dataclass
class GeneratedImage:
    image_bytes: bytes
    filename: str
    mime_type: str
    prompt: str
    pil_image: Image.Image


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_article_images(
    image_prompts: list[str],
    article_title: str = "",
) -> list[GeneratedImage]:
    """Generate the hero thumbnail + in-body figures for an article.

    Convention:
      image_prompts[0]  -> hero / thumbnail (rendered with embedded title text)
      image_prompts[1:] -> in-body figures (rendered with character reference)
    """
    if not image_prompts:
        return []

    # 1. Make sure we have a character reference on disk
    reference_path = _ensure_character_reference()

    images: list[GeneratedImage] = []

    # 2. Hero / thumbnail (no reference image — banner-style with title text)
    hero = _generate_hero(image_prompts[0], article_title, index=0)
    if hero:
        images.append(hero)
    # Brief pause to be polite to the API
    if len(image_prompts) > 1:
        time.sleep(1)

    # 3. In-body figures (each uses the character reference)
    for i, prompt in enumerate(image_prompts[1:], start=1):
        figure = _generate_figure(prompt, reference_path, index=i)
        if figure:
            images.append(figure)
        if i < len(image_prompts) - 1:
            time.sleep(1)

    return images


# ---------------------------------------------------------------------------
# Character reference: generate once, persist to assets/
# ---------------------------------------------------------------------------

def _ensure_character_reference() -> Path:
    """Generate `assets/character_reference.png` if it doesn't exist yet."""
    path = config.CHARACTER_REFERENCE_PATH
    if path.exists():
        return path

    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    png_bytes = _call_generate(
        prompt=CHARACTER_REFERENCE_PROMPT,
        size="1024x1024",
        quality=config.OPENAI_IMAGE_QUALITY,
    )
    path.write_bytes(png_bytes)
    return path


# ---------------------------------------------------------------------------
# Hero / thumbnail generation
# ---------------------------------------------------------------------------

def _generate_hero(
    user_prompt: str,
    article_title: str,
    index: int,
) -> GeneratedImage | None:
    title_clause = (
        f'The article title text to render prominently in the banner is: "{article_title}". '
        f"Render this exact Japanese title text crisp and readable inside the image. "
        if article_title
        else ""
    )

    full_prompt = (
        f"{user_prompt}\n\n"
        f"{title_clause}"
        f"{HERO_STYLE_SUFFIX}"
    )

    png_bytes = _call_generate(
        prompt=full_prompt,
        size=config.OPENAI_IMAGE_HERO_SIZE,
        quality=config.OPENAI_IMAGE_QUALITY,
    )
    if not png_bytes:
        return None

    return _wrap_png(png_bytes, filename=f"article_image_{index + 1}.png", prompt=user_prompt)


# ---------------------------------------------------------------------------
# In-body figure generation (with character reference)
# ---------------------------------------------------------------------------

def _generate_figure(
    user_prompt: str,
    reference_path: Path,
    index: int,
) -> GeneratedImage | None:
    full_prompt = f"{user_prompt}\n\n{FIGURE_STYLE_SUFFIX}"

    png_bytes = _call_edit(
        prompt=full_prompt,
        reference_path=reference_path,
        size=config.OPENAI_IMAGE_FIGURE_SIZE,
        quality=config.OPENAI_IMAGE_QUALITY,
    )
    if not png_bytes:
        return None

    return _wrap_png(png_bytes, filename=f"article_image_{index + 1}.png", prompt=user_prompt)


# ---------------------------------------------------------------------------
# OpenAI API wrappers with retry
# ---------------------------------------------------------------------------

def _call_generate(
    prompt: str,
    size: str,
    quality: str,
    max_retries: int = 3,
) -> bytes:
    """images.generate — no reference image. Raises on permanent failure."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            result = _get_client().images.generate(
                model=config.OPENAI_IMAGE_MODEL,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )
            png_bytes = _decode_first(result)
            if png_bytes is None:
                raise RuntimeError("OpenAI returned no image data in response")
            return png_bytes
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(
        f"gpt-image-2 generate failed after {max_retries} attempts. "
        f"Last error: {type(last_error).__name__}: {last_error}"
    )


def _call_edit(
    prompt: str,
    reference_path: Path,
    size: str,
    quality: str,
    max_retries: int = 3,
) -> bytes:
    """images.edit — with reference image. Raises on permanent failure."""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            with open(reference_path, "rb") as fh:
                result = _get_client().images.edit(
                    model=config.OPENAI_IMAGE_MODEL,
                    image=[fh],
                    prompt=prompt,
                    size=size,
                    quality=quality,
                    input_fidelity="high",
                    n=1,
                )
            png_bytes = _decode_first(result)
            if png_bytes is None:
                raise RuntimeError("OpenAI returned no image data in response")
            return png_bytes
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError(
        f"gpt-image-2 edit failed after {max_retries} attempts. "
        f"Last error: {type(last_error).__name__}: {last_error}"
    )


def _decode_first(result) -> bytes | None:
    """gpt-image-2 always returns b64_json."""
    if not result or not getattr(result, "data", None):
        return None
    b64 = getattr(result.data[0], "b64_json", None)
    if not b64:
        return None
    return base64.b64decode(b64)


def _wrap_png(png_bytes: bytes, filename: str, prompt: str) -> GeneratedImage:
    pil = Image.open(BytesIO(png_bytes))
    if pil.mode != "RGBA":
        pil = pil.convert("RGBA")
    return GeneratedImage(
        image_bytes=png_bytes,
        filename=filename,
        mime_type="image/png",
        prompt=prompt,
        pil_image=pil,
    )


# ---------------------------------------------------------------------------
# Utility: regenerate the character reference (call manually if you want
# to refresh the character look without touching the rest of the pipeline).
# ---------------------------------------------------------------------------

def regenerate_character_reference() -> Path:
    """Force-regenerate the character reference image."""
    if config.CHARACTER_REFERENCE_PATH.exists():
        config.CHARACTER_REFERENCE_PATH.unlink()
    return _ensure_character_reference()
