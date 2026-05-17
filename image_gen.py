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
    "A single-character reference sheet of a Japanese adult woman in her late 20s, "
    "drawn in the bold cartoon-manga style of a Japanese 'comic essay' / lifestyle "
    "manga column / weekly ladies' magazine cut illustration "
    "(コミックエッセイ / 育児マンガ / 週刊女性誌の挿絵 / ライフスタイル雑誌のコラムカット). "
    "\n\n"
    "==== CRITICAL — this is NOT: ==== "
    "NOT realistic. NOT a polished Western digital illustration. "
    "NOT an Instagram illustrator aesthetic. NOT watercolor / wash style. "
    "NOT a detailed anime portrait. NOT a serene refined drawing. "
    "NOT 7-head realistic body proportions. NOT photorealism. "
    "NOT a Korean drama girl portrait. NOT soft pastel illustrator style. "
    "\n\n"
    "==== CRITICAL — this IS: ==== "
    "Cartoon manga proportions — head appears slightly oversized relative to body "
    "(about 1:4 to 1:5 head-to-body ratio, like an essay comic character). "
    "Bold thick black ink outlines, hand-drawn with visible brush/marker imperfection. "
    "Simple flat color fills, bright cheerful palette, NO gradients, NO soft airbrush shading. "
    "Cartoon face with simple lively features — eyes can be small expressive dots or curves, "
    "eyebrows clearly expressive, mouth often open mid-quip showing teeth or rounded tongue, "
    "small pink blush dots on the cheeks, comical energy. "
    "Loose, gestural, hand-drawn quickly with a brush pen — like an essay manga panel. "
    "\n\n"
    "==== Character features (must stay identical in every later figure): ==== "
    "Shoulder-length brown hair with a slight wave and soft bangs. "
    "Wearing a bright mustard-yellow short-sleeve t-shirt and blue denim shorts. "
    "Casual approachable everyday look, slim cartoon build, light skin. "
    "\n\n"
    "==== Composition: ==== "
    "Single character, standing in a slightly dynamic friendly pose, facing the viewer. "
    "Pure plain white background — no decoration, no props, no text, no labels, no other characters. "
    "\n\n"
    "==== Style summary: ==== "
    "This is a model sheet drawn in the comical, hand-drawn cartoon-manga style of a "
    "Japanese essay comic or weekly ladies' magazine column cut illustration. "
    "Expressive, lively, distinctly Japanese, NOT polished Western illustration."
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
    "Place a small Japanese woman character in the corner as a friendly accent — drawn in the "
    "comical, hand-drawn editorial style of a Japanese women's magazine column "
    "(bold organic black ink outlines, flat bright colors, expressive comical face, "
    "shoulder-length wavy brown hair with bangs, mustard-yellow tee + denim shorts). "
    "Modern catchy YouTube-thumbnail / blog hero banner aesthetic. "
    "High contrast, polished, professional, suitable as the lead image of a women's lifestyle blog post. "
    "16:9 horizontal composition."
)

FIGURE_STYLE_SUFFIX = (
    "Render this as a hand-drawn cartoon-manga illustration in the style of a Japanese "
    "essay comic / weekly ladies' magazine column cut illustration "
    "(コミックエッセイ / 育児マンガ / 週刊女性誌の挿絵). "
    "\n\n"
    "==== CRITICAL style requirements — NOT realistic, NOT Western polished, NOT Instagram aesthetic. ==== "
    "It MUST look like a Japanese essay manga panel: cartoon-manga proportions with slightly "
    "oversized heads, bold thick brush-pen black outlines (slightly imperfect), simple flat "
    "color fills with NO gradients, comical exaggerated expressions, and hand-lettered Japanese text. "
    "\n\n"
    "==== Character continuity: ==== "
    "Feature the SAME woman from the reference image. Keep her hair (shoulder-length wavy brown "
    "with soft bangs), her outfit (bright mustard-yellow t-shirt + blue denim shorts), her face, "
    "and her cartoon body proportions IDENTICAL. "
    "She can appear in multiple comical poses with exaggerated expressions within one image to "
    "walk through the explanation — confused face, eureka face with sparkly eyes, tired face with "
    "big sweat drop, victorious fist-pump face, surprised mouth-wide-open face, etc. "
    "\n\n"
    "==== Drawing style: ==== "
    "Cartoon-manga proportions (slightly oversized heads, simple cartoon bodies). "
    "Bold thick hand-drawn brush-pen black outlines with deliberate imperfection. "
    "Simple flat color fills only — NO gradients, NO soft shading, NO airbrush, NO watercolor. "
    "Bright cheerful palette with soft feminine accents (mustard yellow, coral pink, lavender, sky blue). "
    "Comical exaggerated faces with simple eyes (dots, lines, or expressive curves), "
    "expressive eyebrows, mouths often open showing teeth, blush dots on cheeks. "
    "Hand-drawn rounded speech bubbles, motion lines, sweat drops, sparkle marks, comic emphasis lines. "
    "Hand-lettered Japanese comic onomatopoeia integrated into the scene "
    "(e.g. プルプル / ガーン / ピコーン / なるほど! / やったー! / えっ? / シーン...). "
    "Where UI elements are needed (laptops, file icons, chat windows, progress bars), draw them "
    "in the same loose hand-drawn cartoon style — NOT realistic screenshots, NOT digital mockups. "
    "\n\n"
    "==== Composition: ==== "
    "Plain white or very light pastel background, no heavy decoration. "
    "Lively, gestural, with strong comical exaggeration. "
    "Hand-lettered Japanese labels in a casual, lively style. "
    "Clear, uncluttered, instantly readable on a phone. "
    "Overall feel: a fun, comical, hand-drawn cartoon diagram you'd see in a Japanese essay "
    "comic / women's lifestyle magazine column — relatable, warm, with personality."
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


def save_uploaded_character_reference(image_bytes: bytes) -> Path:
    """Save a user-uploaded image as the character reference (converted to PNG)."""
    config.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(BytesIO(image_bytes))
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.save(config.CHARACTER_REFERENCE_PATH, format="PNG")
    return config.CHARACTER_REFERENCE_PATH
