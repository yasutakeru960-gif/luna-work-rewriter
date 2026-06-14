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


# Browser-like User-Agent. Many Japanese rental hosts (XServer, Lolipop,
# SAKURA) block the default "python-requests/2.x" UA at the WAF layer.
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36 LunaWorkRewriter/1.0"
    ),
    "Accept": "application/json",
}


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

    Runs three probes in order so failure messages point at the real cause:
      1. anonymous GET /wp-json/ — proves the REST API itself is reachable
         (catches host-level WAF / .htaccess blocks before we even try auth)
      2. authenticated GET /wp-json/wp/v2/posts?per_page=1 — verifies the
         Application Password works. /posts is rarely blocked, whereas
         /users/me is commonly blocked at the host firewall on Japanese
         shared hosts to prevent username enumeration
      3. authenticated GET /wp-json/wp/v2/users/me — best-effort fetch of
         the friendly display name; failure here is non-fatal
    """
    try:
        # 1) Is REST API reachable at all?
        r1 = requests.get(
            f"{config.WP_URL}/wp-json/",
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        if r1.status_code == 403:
            return False, (
                "REST API がサーバーレベルでブロックされています (403)。"
                "レンタルサーバーのWAF設定、または .htaccess で /wp-json/ "
                "がブロックされていないか確認してください。"
                f" サーバー応答先頭: {_short_error(r1)}"
            )
        if r1.status_code == 404:
            return False, (
                "REST API が見つかりません (404)。WordPress 管理画面の "
                "「設定 → パーマリンク」で「投稿名」などを選択して保存し、"
                "REST APIを無効化するプラグインが入っていないか確認してください。"
            )
        if r1.status_code != 200:
            return False, f"REST 探索失敗 ({r1.status_code}): {_short_error(r1)}"

        # 2) Authenticated GET /users/me?context=edit — this strictly requires
        #    a valid WP_USERNAME + WP_APP_PASSWORD pair AND returns the user's
        #    role + capabilities so we can verify they can actually publish.
        r2 = requests.get(
            f"{config.WP_REST_BASE}/users/me?context=edit",
            headers=DEFAULT_HEADERS,
            auth=_auth(),
            timeout=15,
        )
        if r2.status_code == 401:
            return False, (
                "認証エラー (401): WP_USERNAME / WP_APP_PASSWORD のどちらかが間違っています。"
                " 確認ポイント: (1) Application Passwordを発行した本人のログインID(表示名/メアドではなく)を WP_USERNAME に入れる。"
                " (2) アプリケーションパスワードはスペース込み24文字を改行なしでそのままコピー。"
                " (3) Secretsを保存してアプリを再起動済みか。"
            )
        if r2.status_code == 403:
            return False, (
                f"権限エラー (403): {_short_error(r2)} "
                "認証は通ったが /users/me が拒否されました。ConoHa等のサーバー側設定で "
                "/wp-json/wp/v2/users/* が遮断されている可能性。"
            )
        if r2.status_code != 200:
            return False, f"users/me 失敗 ({r2.status_code}): {_short_error(r2)}"

        data = r2.json()
        display_name = data.get("name") or data.get("slug") or "?"
        username = data.get("username") or data.get("slug") or "?"
        roles = data.get("roles", [])
        caps = data.get("capabilities", {}) or {}
        can_upload = bool(caps.get("upload_files"))
        can_publish = bool(caps.get("publish_posts"))
        can_edit = bool(caps.get("edit_posts"))

        # If the user authenticates but lacks the WP capabilities we need,
        # warn loudly — the publish step will otherwise fail with the same
        # opaque "このユーザーとして投稿を編集する権限がありません" 401.
        if not (can_upload and can_publish and can_edit):
            missing = []
            if not can_edit:
                missing.append("edit_posts")
            if not can_publish:
                missing.append("publish_posts")
            if not can_upload:
                missing.append("upload_files")
            return False, (
                f"認証はOK(ユーザー: {display_name} / login: {username} / 権限グループ: {roles})ですが、"
                f"必要な能力が不足しています: {', '.join(missing)}。"
                f" wp-admin → ユーザー → 当該ユーザー → 権限グループを「編集者」または「管理者」に変更してください。"
            )

        return True, (
            f"接続成功 (ユーザー: {display_name} / login: {username} / "
            f"権限グループ: {roles[0] if roles else '?'} @ {config.WP_URL})"
        )
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
        **DEFAULT_HEADERS,
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
                headers=DEFAULT_HEADERS,
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
    rest_base: str = "posts",
    taxonomy_terms: dict[str, list[int]] | None = None,
) -> WPPost:
    """Create a post of the given post type via the REST API.

    rest_base: REST API base of the target post type (e.g. "posts" for the
        built-in post, or "video-articles" / a CPT slug for a custom type).
    taxonomy_terms: {taxonomy_rest_base: [term_id, ...]} mapping to set
        custom taxonomy terms (e.g. {"video_category": [42]}).
    """
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
    if taxonomy_terms:
        for tax_rest_base, term_ids in taxonomy_terms.items():
            if term_ids:
                payload[tax_rest_base] = term_ids

    endpoint = f"{config.WP_REST_BASE}/{rest_base}"
    resp = requests.post(
        endpoint,
        headers=DEFAULT_HEADERS,
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


def list_post_types() -> list[dict]:
    """List public post types registered on the site, including CPTs.

    Returns each as {"slug", "name", "rest_base", "taxonomies": [slug,...]}.
    """
    resp = requests.get(
        f"{config.WP_REST_BASE}/types?context=edit",
        headers=DEFAULT_HEADERS,
        auth=_auth(),
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"投稿タイプ取得失敗 ({resp.status_code}): {_short_error(resp)}"
        )
    types = resp.json() or {}
    result = []
    for slug, info in types.items():
        if not isinstance(info, dict):
            continue
        rest_base = info.get("rest_base")
        if not rest_base:
            continue
        # Skip internal types like attachment / nav-menu-item / wp_block
        if slug in ("attachment", "nav_menu_item", "wp_block",
                    "wp_template", "wp_template_part", "wp_navigation"):
            continue
        result.append({
            "slug": slug,
            "name": info.get("name") or slug,
            "rest_base": rest_base,
            "taxonomies": info.get("taxonomies") or [],
        })
    return result


def list_taxonomies(post_type_slug: str | None = None) -> list[dict]:
    """List taxonomies, optionally filtered by post type slug.

    Returns each as {"slug", "name", "rest_base", "types": [slug,...]}.
    """
    params = {"context": "edit"}
    if post_type_slug:
        params["type"] = post_type_slug
    resp = requests.get(
        f"{config.WP_REST_BASE}/taxonomies",
        headers=DEFAULT_HEADERS,
        auth=_auth(),
        params=params,
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"タクソノミー取得失敗 ({resp.status_code}): {_short_error(resp)}"
        )
    taxes = resp.json() or {}
    result = []
    for slug, info in taxes.items():
        if not isinstance(info, dict):
            continue
        rest_base = info.get("rest_base")
        if not rest_base:
            continue
        result.append({
            "slug": slug,
            "name": info.get("name") or slug,
            "rest_base": rest_base,
            "types": info.get("types") or [],
        })
    return result


def list_terms(taxonomy_rest_base: str, per_page: int = 100) -> list[dict]:
    """List all terms of a taxonomy. Paginates through every page.

    Returns each as {"id", "name", "slug", "parent"}.
    """
    all_terms: list[dict] = []
    page = 1
    while True:
        resp = requests.get(
            f"{config.WP_REST_BASE}/{taxonomy_rest_base}",
            headers=DEFAULT_HEADERS,
            auth=_auth(),
            params={"per_page": per_page, "page": page, "context": "edit"},
            timeout=15,
        )
        if resp.status_code == 400:
            # past the last page
            break
        if resp.status_code != 200:
            raise RuntimeError(
                f"ターム取得失敗 ({resp.status_code}): {_short_error(resp)}"
            )
        terms = resp.json() or []
        if not terms:
            break
        for t in terms:
            all_terms.append({
                "id": int(t["id"]),
                "name": t.get("name") or "",
                "slug": t.get("slug") or "",
                "parent": int(t.get("parent") or 0),
            })
        if len(terms) < per_page:
            break
        page += 1
    return all_terms


def insert_images_into_html(
    html_content: str,
    media_items: list[WPMediaItem],
) -> str:
    """Replace IMAGE_PLACEHOLDER_N comments with actual WordPress image tags.

    Each placeholder number maps to media_items[N-1] and is replaced only
    ONCE (the first occurrence), so a duplicate placeholder number in the
    HTML can never reuse the same image in two spots. Any placeholder left
    unreplaced (no matching media, or a duplicate second occurrence) is
    stripped so no raw HTML comment ships to the published article.
    """
    import re as _re

    def _img_tag(media: WPMediaItem) -> str:
        return (
            f'<figure class="wp-block-image size-large" '
            f'style="text-align:center; margin: 2em auto;">'
            f'<img src="{media.source_url}" alt="" '
            f'class="wp-image-{media.media_id}" '
            f'style="max-width:100%; height:auto; border-radius:8px;"/>'
            f"</figure>"
        )

    for i, media in enumerate(media_items):
        placeholder = f"<!-- IMAGE_PLACEHOLDER_{i + 1} -->"
        # count=1 → replace only the first occurrence
        html_content = html_content.replace(placeholder, _img_tag(media), 1)

    # Strip any placeholders that were never replaced (missing media or
    # duplicate numbers) so the published HTML has no leftover comments.
    html_content = _re.sub(
        r"<!--\s*IMAGE_PLACEHOLDER_\d+\s*-->", "", html_content
    )
    return html_content
