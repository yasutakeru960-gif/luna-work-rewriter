from __future__ import annotations

from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth

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


def _auth() -> HTTPBasicAuth:
    """Application Password = HTTP Basic Auth on the WP REST API."""
    return HTTPBasicAuth(config.WP_USERNAME or "", config.WP_APP_PASSWORD or "")


def _short_error(resp: requests.Response) -> str:
    """Best-effort extraction of a human-friendly WP REST error message."""
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data.get("message") or str(data)[:300]
    except Exception:
        pass
    return (resp.text or "")[:300]


def test_connection() -> tuple[bool, str]:
    """Test REST API connectivity + Application Password auth.

    Hits /wp-json/wp/v2/users/me which requires authentication, so a 200
    confirms both that the REST API is reachable and that the credentials
    are valid.
    """
    try:
        resp = requests.get(
            f"{config.WP_REST_BASE}/users/me",
            auth=_auth(),
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("name") or data.get("slug") or "unknown"
            return True, f"接続成功 (ユーザー: {name} @ {config.WP_URL})"
        if resp.status_code == 401:
            return (
                False,
                "認証エラー (401): WP_USERNAME / WP_APP_PASSWORD を確認してください。"
                " アプリケーションパスワードはスペース込み24文字でコピーします。",
            )
        if resp.status_code == 403:
            return False, f"権限エラー (403): {_short_error(resp)}"
        if resp.status_code == 404:
            return (
                False,
                f"REST API が見つかりません (404): {config.WP_URL}/wp-json/ "
                "は有効ですか？ パーマリンク設定や REST 無効化プラグインを確認してください。",
            )
        return False, f"接続エラー ({resp.status_code}): {_short_error(resp)}"
    except requests.exceptions.RequestException as e:
        return False, f"接続エラー: {e}"


def upload_image(
    image_bytes: bytes,
    filename: str,
    mime_type: str = "image/png",
    alt_text: str = "",
) -> WPMediaItem:
    """Upload an image to the WordPress media library via the REST API."""
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime_type,
    }
    resp = requests.post(
        config.WP_MEDIA_ENDPOINT,
        headers=headers,
        data=image_bytes,
        auth=_auth(),
        timeout=120,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"画像アップロード失敗 ({resp.status_code}): {_short_error(resp)}"
        )

    data = resp.json()
    media_id = int(data["id"])
    source_url = data.get("source_url") or data.get("guid", {}).get("rendered", "")

    # Best-effort alt text (separate PATCH so a failure here doesn't kill upload)
    if alt_text:
        try:
            requests.post(
                f"{config.WP_MEDIA_ENDPOINT}/{media_id}",
                json={"alt_text": alt_text},
                auth=_auth(),
                timeout=15,
            )
        except requests.exceptions.RequestException:
            pass

    return WPMediaItem(media_id=media_id, source_url=source_url)


def create_post(
    title: str,
    html_content: str,
    slug: str = "",
    meta_description: str = "",
    featured_image_id: int | None = None,
    status: str = "draft",
) -> WPPost:
    """Create a post via the REST API."""
    payload: dict = {
        "title": title,
        "content": html_content,
        "status": status,
    }
    if slug:
        payload["slug"] = slug
    if meta_description:
        payload["excerpt"] = meta_description
    if featured_image_id:
        payload["featured_media"] = featured_image_id

    resp = requests.post(
        config.WP_POSTS_ENDPOINT,
        json=payload,
        auth=_auth(),
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"投稿作成失敗 ({resp.status_code}): {_short_error(resp)}"
        )

    data = resp.json()
    post_id = int(data["id"])
    post_url = data.get("link") or f"{config.WP_URL}/?p={post_id}"
    edit_url = f"{config.WP_URL}/wp-admin/post.php?post={post_id}&action=edit"

    return WPPost(post_id=post_id, post_url=post_url, edit_url=edit_url)


def insert_images_into_html(
    html_content: str,
    media_items: list[WPMediaItem],
) -> str:
    """Replace IMAGE_PLACEHOLDER_N comments with actual WordPress image tags."""
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
