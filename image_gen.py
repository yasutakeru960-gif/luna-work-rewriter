from __future__ import annotations

import base64
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from openai import OpenAI
from PIL import Image

import config

_client: OpenAI | None = None

# Per-request hard timeout. gpt-image-2 high quality usually finishes in
# 20-60s; 180s gives margin for slow runs without letting a stuck request
# hang the whole UI for hours.
OPENAI_REQUEST_TIMEOUT = 180.0


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            timeout=OPENAI_REQUEST_TIMEOUT,
        )
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

OPERATION_STYLE_SUFFIX = (
    "Render this as a clear UI walkthrough image — the kind of image you'd see in a "
    "Japanese how-to blog post explaining step by step how to use an app or website. "
    "\n\n"
    "==== CRITICAL — what this is NOT: ==== "
    "NOT a character illustration. NOT chibi. NOT anime. NOT an editorial cartoon. "
    "The recurring chibi character must NOT appear in this image. "
    "This is purely a UI demonstration, not a story scene. "
    "\n\n"
    "==== CRITICAL — what this IS: ==== "
    "A realistic-looking but stylized mockup of the actual app screen or web page "
    "being explained. "
    "Show the interface elements relevant to the action — buttons, menus, forms, "
    "input fields, modals, lists, navigation bars. "
    "Modern UI with realistic colors, subtle drop shadows, rounded corners. "
    "Smartphone screen frame OR desktop browser window frame, whichever fits the context. "
    "Light gray or white surrounding background. "
    "\n\n"
    "==== Annotation overlay (the hand-holding part): ==== "
    "Add red or orange annotation overlays on top of the UI to guide the reader: "
    "Red or orange circles / rounded rectangles highlighting the exact button or "
    "field to tap or fill in. "
    "Arrows pointing from explanation labels to the relevant UI element. "
    "Numbered step markers ①②③ for sequential steps. "
    "Hand-lettered Japanese callout text (e.g. ここをタップ / メールアドレスを入力 / "
    "「登録する」を押す / 次へ進む / これを選択 / ① 商品名を入力) integrated as "
    "floating labels with simple background. "
    "\n\n"
    "==== Composition: ==== "
    "If showing a single screen with one main action: one phone or desktop mockup, "
    "centered, with annotations. "
    "If showing a sequence of 2-3 steps: arrange screens horizontally or in a small "
    "grid, each labeled STEP 1 / STEP 2 / STEP 3. "
    "Plenty of white space, easy to read on a phone, focus on the action being taught. "
    "\n\n"
    "Overall feel: a helpful, instantly understandable Japanese app/web how-to image."
)


ACCENT_STYLE_SUFFIX = (
    "Render this as a SIMPLE, calm accent illustration — a magazine-column "
    "spot illustration whose only job is to give the reader's eye a rest "
    "between paragraphs of text. NOT an explainer diagram. "
    "\n\n"
    "==== CRITICAL — what this is NOT: ==== "
    "NOT a multi-panel explainer. NOT a diagram. NOT a chart. "
    "NO speech bubbles. NO Japanese onomatopoeia (no プルプル / ガーン / etc). "
    "NO labels, NO arrows, NO step markers, NO UI mockups (no laptops, no "
    "file icons, no chat windows). NO captions inside the image. "
    "Minimize text — ideally zero text. If text is unavoidable, at most one "
    "short hand-lettered word as a soft accent. "
    "\n\n"
    "==== CRITICAL — what this IS: ==== "
    "The SAME woman from the reference image, drawn as a single character "
    "or a single small scene with her in one natural pose that fits the "
    "section's mood (relaxed, thinking, smiling, sipping coffee, sitting at "
    "a window, stretching, holding a notebook, looking up at a sky, etc.). "
    "Hand-drawn cartoon-manga style consistent with the rest of the article: "
    "bold thick black ink outlines, simple flat color fills, no gradients, "
    "small blush dots on cheeks, expressive but subtle face. "
    "Plain white or very light single-tone pastel background. "
    "\n\n"
    "==== Character continuity: ==== "
    "Keep her hair (shoulder-length wavy brown with soft bangs), her outfit "
    "(bright mustard-yellow t-shirt + blue denim shorts), face, and body "
    "proportions IDENTICAL to the reference. "
    "\n\n"
    "==== Composition: ==== "
    "Centered or slightly off-center single subject. Lots of negative space. "
    "Phone-friendly, easy on the eyes. "
    "Overall feel: a quiet, friendly spot illustration in a Japanese "
    "lifestyle column — adds visual rhythm without adding information."
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

def _resolve_style(
    image_styles: list[str] | None, index: int, default: str
) -> str:
    if image_styles and 0 <= index < len(image_styles):
        s = (image_styles[index] or "").lower().strip()
        if s in ("hero", "figure", "accent", "operation"):
            return s
    return default


def generate_one_image(
    image_prompts: list[str],
    index: int,
    article_title: str = "",
    quality: str | None = None,
    image_styles: list[str] | None = None,
) -> GeneratedImage | None:
    """Generate a single image at the given index in the prompts list.

    Routing based on image_styles[index]:
      "hero"      (default for index 0) -> _generate_hero, no reference image
      "figure"    (default for index>=1) -> _generate_figure, character ref
      "operation"                        -> _generate_operation, no ref, UI mockup

    Returns None only if the index is out of range; permanent API failures raise.
    """
    if index < 0 or index >= len(image_prompts):
        return None
    prompt = image_prompts[index]
    effective_quality = quality or config.OPENAI_IMAGE_QUALITY
    style = _resolve_style(
        image_styles, index, default="hero" if index == 0 else "figure"
    )

    if style == "hero" or index == 0:
        return _generate_hero(prompt, article_title, index=index, quality=effective_quality)
    if style == "operation":
        return _generate_operation(prompt, index=index, quality=effective_quality)
    reference_path = _ensure_character_reference()
    if style == "accent":
        return _generate_accent(
            prompt, reference_path, index=index, quality=effective_quality
        )
    return _generate_figure(
        prompt, reference_path, index=index, quality=effective_quality
    )


def generate_article_images_parallel(
    image_prompts: list[str],
    article_title: str,
    indices: list[int],
    quality: str | None = None,
    max_workers: int = 3,
    on_complete=None,
    on_failure=None,
    image_styles: list[str] | None = None,
) -> dict[int, GeneratedImage]:
    """Generate images at the given indices in parallel using a thread pool.

    Callbacks fire from the main thread as each future completes:
      on_complete(index, GeneratedImage)
      on_failure(index, Exception)

    Returns a dict of index -> GeneratedImage for all successful generations.
    """
    if not indices:
        return {}

    # Only materialize the character reference when at least one figure-style
    # image will need it; doing it up-front avoids a thread race.
    needs_char_ref = any(
        _resolve_style(image_styles, i, default="figure") == "figure" and i >= 1
        for i in indices
    )
    if needs_char_ref:
        _ensure_character_reference()

    results: dict[int, GeneratedImage] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                generate_one_image,
                image_prompts,
                idx,
                article_title,
                quality,
                image_styles,
            ): idx
            for idx in indices
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                img = fut.result()
                if img is None:
                    if on_failure:
                        on_failure(idx, RuntimeError("No image returned"))
                else:
                    results[idx] = img
                    if on_complete:
                        on_complete(idx, img)
            except Exception as e:
                if on_failure:
                    on_failure(idx, e)

    return results


def generate_article_images(
    image_prompts: list[str],
    article_title: str = "",
    progress_callback=None,
    quality: str | None = None,
) -> list[GeneratedImage]:
    """Generate the hero thumbnail + in-body figures for an article.

    Convention:
      image_prompts[0]  -> hero / thumbnail (rendered with embedded title text)
      image_prompts[1:] -> in-body figures (rendered with character reference)

    progress_callback(stage_index, total_stages, description) is invoked
    before each generation step so the caller can update a progress bar.
    """
    if not image_prompts:
        return []

    effective_quality = quality or config.OPENAI_IMAGE_QUALITY
    total_stages = 1 + len(image_prompts)  # 1 char-ref check + N prompts
    stage = 0

    def _report(desc: str):
        nonlocal stage
        stage += 1
        if progress_callback:
            try:
                progress_callback(stage, total_stages, desc)
            except Exception:
                pass

    _report("キャラクター参照画像を準備中...")
    reference_path = _ensure_character_reference()

    images: list[GeneratedImage] = []
    figure_count = max(len(image_prompts) - 1, 0)

    _report("サムネを生成中...")
    hero = _generate_hero(image_prompts[0], article_title, index=0, quality=effective_quality)
    if hero:
        images.append(hero)
    if len(image_prompts) > 1:
        time.sleep(1)

    for i, prompt in enumerate(image_prompts[1:], start=1):
        _report(f"図解 {i}/{figure_count} を生成中...")
        figure = _generate_figure(
            prompt, reference_path, index=i, quality=effective_quality
        )
        if figure:
            images.append(figure)
        if i < figure_count:
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
    quality: str | None = None,
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
        quality=quality or config.OPENAI_IMAGE_QUALITY,
    )
    if not png_bytes:
        return None

    return _wrap_png(png_bytes, filename=f"article_image_{index + 1}.png", prompt=user_prompt)


# ---------------------------------------------------------------------------
# In-body figure generation (with character reference)
# ---------------------------------------------------------------------------

def _generate_operation(
    user_prompt: str,
    index: int,
    quality: str | None = None,
) -> GeneratedImage | None:
    """Operation/UI walkthrough image — no character reference, realistic UI mockup."""
    full_prompt = f"{user_prompt}\n\n{OPERATION_STYLE_SUFFIX}"

    png_bytes = _call_generate(
        prompt=full_prompt,
        size=config.OPENAI_IMAGE_FIGURE_SIZE,
        quality=quality or config.OPENAI_IMAGE_QUALITY,
    )
    if not png_bytes:
        return None

    return _wrap_png(
        png_bytes, filename=f"article_image_{index + 1}.png", prompt=user_prompt
    )


def _generate_accent(
    user_prompt: str,
    reference_path: Path,
    index: int,
    quality: str | None = None,
) -> GeneratedImage | None:
    """Accent/spot illustration — minimal text, calm single-figure scene."""
    full_prompt = f"{user_prompt}\n\n{ACCENT_STYLE_SUFFIX}"

    png_bytes = _call_edit(
        prompt=full_prompt,
        reference_path=reference_path,
        size=config.OPENAI_IMAGE_FIGURE_SIZE,
        quality=quality or config.OPENAI_IMAGE_QUALITY,
    )
    if not png_bytes:
        return None

    return _wrap_png(
        png_bytes, filename=f"article_image_{index + 1}.png", prompt=user_prompt
    )


def _generate_figure(
    user_prompt: str,
    reference_path: Path,
    index: int,
    quality: str | None = None,
) -> GeneratedImage | None:
    full_prompt = f"{user_prompt}\n\n{FIGURE_STYLE_SUFFIX}"

    png_bytes = _call_edit(
        prompt=full_prompt,
        reference_path=reference_path,
        size=config.OPENAI_IMAGE_FIGURE_SIZE,
        quality=quality or config.OPENAI_IMAGE_QUALITY,
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
