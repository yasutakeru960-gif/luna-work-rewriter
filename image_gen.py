from __future__ import annotations

import textwrap
import time
from dataclasses import dataclass
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config

_client = None

# Japanese fonts (macOS)
_FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"
_FONT_MEDIUM = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
_FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GOOGLE_AI_API_KEY)
    return _client


@dataclass
class GeneratedImage:
    image_bytes: bytes
    filename: str
    mime_type: str
    prompt: str
    pil_image: Image.Image


def generate_article_images(
    image_prompts: list[str],
    article_title: str = "",
) -> list[GeneratedImage]:
    """Generate images for each prompt using Nano Banana 2."""
    images = []
    for i, prompt in enumerate(image_prompts):
        image = _generate_single_image(prompt, index=i)
        if image:
            # For the first image (hero), overlay the article title
            if i == 0 and article_title:
                image = _create_title_card(image, article_title)
            images.append(image)
        # Brief pause between requests to avoid rate limiting
        if i < len(image_prompts) - 1:
            time.sleep(2)
    return images


def _create_title_card(
    base_image: GeneratedImage,
    title: str,
) -> GeneratedImage:
    """Create a professional title card with gradient background and illustration."""
    target_w, target_h = 1200, 630

    # Create gradient background
    img = Image.new("RGBA", (target_w, target_h))
    draw = ImageDraw.Draw(img, "RGBA")

    # Draw warm gradient background (coral pink -> soft lavender)
    for y in range(target_h):
        ratio = y / target_h
        r = int(245 - 30 * ratio)  # 245 -> 215
        g = int(180 - 40 * ratio)  # 180 -> 140
        b = int(200 + 30 * ratio)  # 200 -> 230
        draw.rectangle([(0, y), (target_w, y + 1)], fill=(r, g, b, 255))

    # Place the AI illustration on the right side (semi-transparent)
    illustration = base_image.pil_image.copy()
    ill_h = target_h
    ill_w = int(illustration.width * (ill_h / illustration.height))
    illustration = illustration.resize((ill_w, ill_h), Image.LANCZOS)
    if illustration.mode != "RGBA":
        illustration = illustration.convert("RGBA")

    # Make illustration semi-transparent
    alpha = illustration.split()[3]
    alpha = alpha.point(lambda p: int(p * 0.35))  # 35% opacity
    illustration.putalpha(alpha)

    # Position illustration on the right
    x_offset = target_w - ill_w + int(ill_w * 0.15)
    img.paste(illustration, (x_offset, 0), illustration)

    # Re-create draw after paste
    draw = ImageDraw.Draw(img, "RGBA")

    # Draw title text (dark text on light background)
    _draw_title_text_styled(draw, title, target_w, target_h)

    # Convert to bytes
    buf = BytesIO()
    final_img = img.convert("RGB")  # Remove alpha for final PNG
    final_img.save(buf, format="PNG", optimize=True)
    png_bytes = buf.getvalue()

    return GeneratedImage(
        image_bytes=png_bytes,
        filename=base_image.filename,
        mime_type="image/png",
        prompt=base_image.prompt,
        pil_image=final_img,
    )


def _resize_and_crop(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize and center-crop image to target dimensions."""
    # Calculate scale to cover target area
    scale = max(target_w / img.width, target_h / img.height)
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    return img



def _draw_title_text_styled(draw: ImageDraw.Draw, title: str, w: int, h: int):
    """Draw styled article title on a gradient background."""
    clean_title = title.strip()

    # Split title into lines
    lines = _split_title_lines(clean_title, max_chars=14)

    # Font size based on line count
    if len(lines) <= 2:
        font_size = 52
    elif len(lines) <= 3:
        font_size = 44
    else:
        font_size = 38

    try:
        font = ImageFont.truetype(_FONT_BOLD, font_size)
    except Exception:
        try:
            font = ImageFont.truetype(_FONT_MEDIUM, font_size)
        except Exception:
            font = ImageFont.load_default()

    # Calculate text block dimensions
    line_spacing = int(font_size * 0.6)
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
        line_widths.append(bbox[2] - bbox[0])

    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)

    # Position text on the left side (leaving room for illustration on right)
    text_area_w = int(w * 0.65)
    y_start = (h - total_height) // 2 - 20

    # Draw a subtle frosted panel behind the text
    panel_padding = 30
    max_line_w = max(line_widths) if line_widths else 200
    panel_x1 = (text_area_w - max_line_w) // 2 - panel_padding
    panel_y1 = y_start - panel_padding
    panel_x2 = (text_area_w + max_line_w) // 2 + panel_padding
    panel_y2 = y_start + total_height + panel_padding
    draw.rounded_rectangle(
        [(panel_x1, panel_y1), (panel_x2, panel_y2)],
        radius=16,
        fill=(255, 255, 255, 100),
    )

    # Draw each line
    for i, line in enumerate(lines):
        text_w = line_widths[i]
        x = (text_area_w - text_w) // 2
        y = y_start + i * (line_heights[0] + line_spacing)

        # Soft shadow
        draw.text(
            (x + 1, y + 2),
            line,
            fill=(80, 40, 60, 80),
            font=font,
        )

        # Main text in dark color
        draw.text((x, y), line, fill=(60, 30, 50, 255), font=font)

    # Draw "LUNA WORK" branding at bottom center
    try:
        brand_font = ImageFont.truetype(_FONT_MEDIUM, 18)
    except Exception:
        brand_font = ImageFont.load_default()

    brand_text = "LUNA WORK"
    brand_bbox = draw.textbbox((0, 0), brand_text, font=brand_font)
    brand_w = brand_bbox[2] - brand_bbox[0]

    # Brand with decorative line
    brand_x = (text_area_w - brand_w) // 2
    brand_y = h - 55
    line_w = 60
    draw.line(
        [(brand_x - line_w - 10, brand_y + 10), (brand_x - 10, brand_y + 10)],
        fill=(140, 90, 120, 150),
        width=1,
    )
    draw.text((brand_x, brand_y), brand_text, fill=(100, 60, 80, 200), font=brand_font)
    draw.line(
        [(brand_x + brand_w + 10, brand_y + 10), (brand_x + brand_w + line_w + 10, brand_y + 10)],
        fill=(140, 90, 120, 150),
        width=1,
    )


def _split_title_lines(title: str, max_chars: int = 14) -> list[str]:
    """Split Japanese title into balanced lines."""
    if len(title) <= max_chars:
        return [title]

    lines = []
    remaining = title

    while remaining:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break

        # Try to find a natural break point
        # Look for punctuation or particles near max_chars
        break_chars = "。、！？」）】のにはをがでと"
        best_break = max_chars

        # Search around the max_chars position for a good break
        for offset in range(3):
            pos = max_chars - offset
            if pos > 0 and pos < len(remaining):
                if remaining[pos - 1] in break_chars:
                    best_break = pos
                    break

        lines.append(remaining[:best_break])
        remaining = remaining[best_break:]

    return lines


def _generate_single_image(
    prompt: str, index: int, max_retries: int = 3
) -> GeneratedImage | None:
    """Generate a single image with retry logic."""
    # First image (index 0) is the hero/thumbnail background
    if index == 0:
        style_suffix = (
            "Style: beautiful, dreamy background illustration, "
            "warm and inviting, soft pastel gradient colors, "
            "modern flat illustration style, high quality, detailed, "
            "clean composition, no text overlays, no words, "
            "slightly blurred/soft focus suitable as a background. "
            "Japanese style, featuring Japanese woman or Japanese cultural elements."
        )
    else:
        style_suffix = (
            "Style: soft pastel colors, modern flat illustration, "
            "minimal clean design, warm and friendly, "
            "suitable for a Japanese women's lifestyle blog, "
            "no text overlays, high quality. "
            "Japanese style, featuring Japanese people or Japanese cultural context."
        )

    full_prompt = f"{prompt} {style_suffix}"

    for attempt in range(max_retries):
        try:
            response = _get_client().models.generate_content(
                model=config.GEMINI_IMAGE_MODEL,
                contents=[full_prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            if not response.candidates:
                continue

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    image_data = part.inline_data.data
                    pil_image = Image.open(BytesIO(image_data))

                    # Ensure good resolution - resize up if too small
                    min_width = 1200
                    if pil_image.width < min_width:
                        ratio = min_width / pil_image.width
                        new_size = (min_width, int(pil_image.height * ratio))
                        pil_image = pil_image.resize(new_size, Image.LANCZOS)

                    # Convert to RGBA for potential overlay processing
                    if pil_image.mode != "RGBA":
                        pil_image = pil_image.convert("RGBA")

                    # Convert to high-quality PNG bytes
                    buf = BytesIO()
                    pil_image.save(buf, format="PNG", optimize=True)
                    png_bytes = buf.getvalue()

                    return GeneratedImage(
                        image_bytes=png_bytes,
                        filename=f"article_image_{index + 1}.png",
                        mime_type="image/png",
                        prompt=prompt,
                        pil_image=pil_image,
                    )

        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(3)

    return None
