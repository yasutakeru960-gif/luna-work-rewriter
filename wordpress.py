from __future__ import annotations

import base64
import xmlrpc.client
from dataclasses import dataclass

import config


@dataclass
class WPMediaItem:
    media_id: int
    source_url: str


@dataclass
class WPPost:
    post_id: int
    post_url: str
    edit_url: str


def _get_xmlrpc_client() -> xmlrpc.client.ServerProxy:
    """Get XML-RPC client for WordPress."""
    return xmlrpc.client.ServerProxy(f"{config.WP_URL}/xmlrpc.php")


def test_connection() -> tuple[bool, str]:
    """Test WordPress XML-RPC connectivity and authentication."""
    try:
        client = _get_xmlrpc_client()
        blogs = client.wp.getUsersBlogs(
            config.WP_USERNAME,
            config.WP_APP_PASSWORD,
        )
        if blogs:
            blog_name = blogs[0].get("blogName", "unknown")
            return True, f"接続成功 (サイト: {blog_name})"
        return False, "ブログ情報を取得できませんでした"
    except xmlrpc.client.Fault as e:
        return False, f"認証エラー: {e.faultString}"
    except Exception as e:
        return False, f"接続エラー: {e}"


def upload_image(
    image_bytes: bytes,
    filename: str,
    mime_type: str = "image/png",
    alt_text: str = "",
) -> WPMediaItem:
    """Upload an image to WordPress media library via XML-RPC."""
    client = _get_xmlrpc_client()

    media_data = {
        "name": filename,
        "type": mime_type,
        "bits": xmlrpc.client.Binary(image_bytes),
        "overwrite": False,
    }

    result = client.wp.uploadFile(
        1,  # blog_id
        config.WP_USERNAME,
        config.WP_APP_PASSWORD,
        media_data,
    )

    return WPMediaItem(
        media_id=int(result["id"]),
        source_url=result["url"],
    )


def create_post(
    title: str,
    html_content: str,
    slug: str = "",
    meta_description: str = "",
    featured_image_id: int | None = None,
    status: str = "draft",
) -> WPPost:
    """Create a WordPress post via XML-RPC."""
    client = _get_xmlrpc_client()

    post_data: dict = {
        "post_type": "post",
        "post_title": title,
        "post_content": html_content,
        "post_status": status,
    }
    if slug:
        post_data["post_name"] = slug
    if meta_description:
        post_data["post_excerpt"] = meta_description
    if featured_image_id:
        post_data["post_thumbnail"] = featured_image_id

    post_id = client.wp.newPost(
        1,  # blog_id
        config.WP_USERNAME,
        config.WP_APP_PASSWORD,
        post_data,
    )

    post_id = int(post_id)

    # Get the post URL
    post_info = client.wp.getPost(
        1,
        config.WP_USERNAME,
        config.WP_APP_PASSWORD,
        post_id,
        ["link"],
    )
    post_url = post_info.get("link", f"{config.WP_URL}/?p={post_id}")

    return WPPost(
        post_id=post_id,
        post_url=post_url,
        edit_url=f"{config.WP_URL}/wp-admin/post.php?post={post_id}&action=edit",
    )


def insert_images_into_html(
    html_content: str,
    media_items: list[WPMediaItem],
) -> str:
    """Replace IMAGE_PLACEHOLDER comments with actual WordPress image tags."""
    for i, media in enumerate(media_items):
        placeholder = f"<!-- IMAGE_PLACEHOLDER_{i + 1} -->"
        img_tag = (
            f'<figure class="wp-block-image size-large" '
            f'style="text-align:center; margin: 2em auto;">'
            f'<img src="{media.source_url}" alt="" '
            f'class="wp-image-{media.media_id}" '
            f'style="max-width:100%; height:auto; border-radius:8px;"/>'
            f"</figure>"
        )
        html_content = html_content.replace(placeholder, img_tag)
    return html_content
