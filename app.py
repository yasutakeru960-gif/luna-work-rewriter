import dataclasses
import json

import streamlit as st

import config
from scraper import scrape_article, create_article_from_text, ScrapedArticle
from rewriter import rewrite_article, RewrittenArticle
from image_gen import (
    generate_article_images_parallel,
    generate_one_image,
    regenerate_character_reference,
    save_uploaded_character_reference,
)
from wordpress import (
    test_connection,
    upload_image,
    create_post,
    insert_images_into_html,
)


def _serialize_draft() -> str:
    """Serialize the scraped + rewritten article to JSON for download."""
    return json.dumps(
        {
            "scraped": dataclasses.asdict(st.session_state.scraped),
            "rewritten": dataclasses.asdict(st.session_state.rewritten),
        },
        ensure_ascii=False,
        indent=2,
    )

st.set_page_config(
    page_title="LUNA WORK Article Rewriter",
    page_icon="moon",
    layout="wide",
)

st.title("LUNA WORK Article Rewriter")
st.caption("記事URLを入力 → リライト → 画像生成 → WordPress投稿")

# --- Sidebar: Configuration ---
with st.sidebar:
    st.header("設定状況")
    errors = config.validate_config()
    if errors:
        for err in errors:
            st.error(err)
        st.info("`.env` ファイルにAPIキーを設定してください")
        st.stop()
    else:
        st.success("APIキー設定済み")

    if st.button("WordPress接続テスト"):
        ok, msg = test_connection()
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.divider()
    st.subheader("画像生成の品質")
    quality_options = {
        "low": "節約 (low) — 1枚 約$0.01",
        "medium": "標準 (medium) — 1枚 約$0.04",
        "high": "高品質 (high) — 1枚 約$0.19",
        "auto": "自動 (auto) — モデル任せ",
    }
    st.selectbox(
        "品質",
        options=list(quality_options.keys()),
        format_func=lambda k: quality_options[k],
        index=1,
        key="image_quality",
        help="テスト中はlow/medium推奨。本番投稿時にhighへ。",
    )

    st.divider()
    st.subheader("キャラクター参照画像")
    if config.CHARACTER_REFERENCE_PATH.exists():
        st.image(
            str(config.CHARACTER_REFERENCE_PATH),
            caption="本文図解で毎回登場するキャラ",
            use_container_width=True,
        )
        st.download_button(
            "このキャラ画像を保存",
            data=config.CHARACTER_REFERENCE_PATH.read_bytes(),
            file_name="character_reference.png",
            mime="image/png",
            help="再デプロイで消える前に手元に保存。次回は下のアップローダーで戻せます。",
        )
        if st.button("キャラを再生成(AI)"):
            with st.spinner("キャラクター参照画像を再生成中..."):
                try:
                    regenerate_character_reference()
                    st.success("再生成しました")
                    st.rerun()
                except Exception as e:
                    st.error(f"再生成失敗: {e}")
    else:
        st.caption("初回の画像生成時に自動で作成されます")

    with st.expander("自分で用意した画像をキャラに使う"):
        st.caption(
            "AIで生成したキャラがイメージと違う場合、好みのイラストをアップロードしてください。"
            "以降の図解は、その画像のキャラ・絵柄に寄せて生成されます。"
        )
        uploaded_char = st.file_uploader(
            "PNG または JPG",
            type=["png", "jpg", "jpeg"],
            key="char_upload",
        )
        if uploaded_char is not None and st.button(
            "この画像をキャラとして使う", key="btn_char_upload"
        ):
            try:
                save_uploaded_character_reference(uploaded_char.read())
                st.success("参照画像を更新しました")
                st.rerun()
            except Exception as e:
                st.error(f"アップロード失敗: {e}")

    st.divider()
    st.caption("LUNA WORK Salon")

# --- Session State ---
for key in ["scraped", "rewritten", "images", "wp_post"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ========================================
# Step 1: Article Input
# ========================================
st.header("Step 1: 踏襲する記事を入力")

input_tab_url, input_tab_text, input_tab_file, input_tab_draft = st.tabs(
    ["URLから取得", "テキスト貼り付け", "ファイルアップロード", "下書きを読み込む"]
)

with input_tab_url:
    url = st.text_input(
        "踏襲する記事のURL",
        placeholder="https://example.com/article",
    )
    if st.button("記事を取得", disabled=not url, type="primary", key="btn_url"):
        with st.spinner("記事を取得中..."):
            try:
                st.session_state.scraped = scrape_article(url)
                st.session_state.rewritten = None
                st.session_state.images = None
                st.session_state.wp_post = None
                st.success("記事を取得しました")
            except Exception as e:
                st.error(f"取得失敗: {e}")

with input_tab_text:
    paste_title = st.text_input("記事タイトル", placeholder="元記事のタイトル", key="paste_title")
    paste_text = st.text_area(
        "記事本文を貼り付け",
        placeholder="有料記事など、URLから取得できない場合はここにテキストを貼り付けてください",
        height=300,
        key="paste_text",
    )
    if st.button("この内容で進む", disabled=not paste_text, type="primary", key="btn_paste"):
        st.session_state.scraped = create_article_from_text(
            text=paste_text, title=paste_title
        )
        st.session_state.rewritten = None
        st.session_state.images = None
        st.session_state.wp_post = None
        st.success("記事を読み込みました")

with input_tab_file:
    uploaded_file = st.file_uploader(
        "テキストファイルをアップロード",
        type=["txt", "md"],
        key="file_upload",
    )
    file_title = st.text_input("記事タイトル", placeholder="元記事のタイトル", key="file_title")
    if st.button(
        "ファイルを読み込む",
        disabled=uploaded_file is None,
        type="primary",
        key="btn_file",
    ):
        file_text = uploaded_file.read().decode("utf-8")
        st.session_state.scraped = create_article_from_text(
            text=file_text, title=file_title
        )
        st.session_state.rewritten = None
        st.session_state.images = None
        st.session_state.wp_post = None
        st.success("ファイルを読み込みました")

with input_tab_draft:
    st.caption(
        "リライト後にダウンロードしたJSONを読み込めば、リライトをやり直さずに画像生成からやり直せます。"
    )
    uploaded_draft = st.file_uploader(
        "下書きJSON",
        type=["json"],
        key="draft_upload",
    )
    if st.button(
        "この下書きから再開",
        disabled=uploaded_draft is None,
        type="primary",
        key="btn_draft",
    ):
        try:
            data = json.loads(uploaded_draft.read().decode("utf-8"))
            st.session_state.scraped = ScrapedArticle(**data["scraped"])
            st.session_state.rewritten = RewrittenArticle(**data["rewritten"])
            st.session_state.images = None
            st.session_state.wp_post = None
            st.success("下書きを復元しました。Step 4以降から再開できます")
            st.rerun()
        except Exception as e:
            st.error(f"下書きの読み込み失敗: {e}")

# ========================================
# Step 2: Show Scraped Content
# ========================================
if st.session_state.scraped:
    article = st.session_state.scraped
    st.header("Step 2: 元記事の確認")
    st.subheader(article.title)

    col1, col2 = st.columns(2)
    with col1:
        st.caption(f"著者: {article.author or '不明'}")
    with col2:
        st.caption(f"日付: {article.date or '不明'}")

    with st.expander("元記事のテキストを表示", expanded=False):
        display_text = article.text
        if len(display_text) > 5000:
            display_text = display_text[:5000] + "\n\n...（以下省略）"
        st.text(display_text)

    if article.headings:
        with st.expander("見出し構造", expanded=False):
            for h in article.headings:
                st.markdown(f"- {h}")

    # ========================================
    # Step 3: Rewrite
    # ========================================
    st.header("Step 3: AIでリライト")
    if st.button("リライト実行", type="primary"):
        with st.spinner("Claude APIでリライト中...（30〜60秒かかります）"):
            try:
                st.session_state.rewritten = rewrite_article(article)
                st.session_state.images = None
                st.session_state.wp_post = None
                st.success("リライト完了")
            except Exception as e:
                st.error(f"リライト失敗: {e}")

# ========================================
# Step 4: Preview & Image Generation
# ========================================
if st.session_state.rewritten:
    rewritten = st.session_state.rewritten

    st.header("Step 4: リライト結果の確認 & 画像生成")

    st.subheader(rewritten.title)
    st.caption(f"Slug: {rewritten.slug}")
    st.caption(f"Meta: {rewritten.meta_description}")

    st.download_button(
        "下書きをダウンロード(JSON)",
        data=_serialize_draft(),
        file_name=f"draft_{rewritten.slug or 'article'}.json",
        mime="application/json",
        help="リロードや再デプロイで作業が消えないよう、リライト結果をJSONで保存できます。Step 1 の「下書きを読み込む」タブから復元できます。",
    )

    tab_preview, tab_edit = st.tabs(["プレビュー", "HTML編集"])

    with tab_preview:
        st.html(rewritten.html_content)

    with tab_edit:
        edited_html = st.text_area(
            "HTMLコンテンツ（編集可能）",
            value=rewritten.html_content,
            height=400,
            key="html_editor",
        )
        if edited_html != rewritten.html_content:
            st.session_state.rewritten.html_content = edited_html
            st.info("HTMLを更新しました")

    # Image generation
    st.subheader("画像生成")

    # Initialize slots whenever the prompt list shape changes
    total_imgs = len(rewritten.image_prompts)
    if (
        not isinstance(st.session_state.images, list)
        or len(st.session_state.images) != total_imgs
    ):
        st.session_state.images = [None] * total_imgs

    done_count = sum(1 for img in st.session_state.images if img is not None)
    remaining_indices = [
        i for i, img in enumerate(st.session_state.images) if img is None
    ]
    quality_choice = st.session_state.get("image_quality", "medium")

    # Normalize image_styles length (e.g. loaded from older JSON drafts)
    styles_list = list(rewritten.image_styles) if rewritten.image_styles else []
    while len(styles_list) < len(rewritten.image_prompts):
        styles_list.append("hero" if len(styles_list) == 0 else "figure")
    rewritten.image_styles = styles_list

    _style_label = {"hero": "サムネ", "figure": "図解", "operation": "操作画面"}

    with st.expander("生成プロンプト一覧", expanded=False):
        for i, prompt in enumerate(rewritten.image_prompts):
            style = styles_list[i] if i < len(styles_list) else "figure"
            label = _style_label.get(style, "図解")
            st.markdown(f"**{i + 1}. [{label}]** {prompt}")

    # Top-level generate / resume button
    if remaining_indices:
        button_label = (
            f"画像を生成 ({total_imgs}枚 / 並列3)"
            if done_count == 0
            else f"残り{len(remaining_indices)}枚を生成 (生成済み {done_count}/{total_imgs})"
        )
        if total_imgs >= 7 and done_count == 0:
            st.caption(
                f"※ {total_imgs}枚 × 約45秒 ÷ 3並列 ≈ "
                f"おおむね {max(total_imgs * 45 // 60 // 3, 1)} 分前後で完了します。"
            )
        if st.button(button_label, type="primary", key="btn_gen_images"):
            progress_bar = st.progress(
                done_count / total_imgs if total_imgs else 0.0,
                text=f"生成中... 完了 {done_count}/{total_imgs}",
            )
            completed = [done_count]
            failures: list[tuple[int, Exception]] = []

            def _on_complete(idx, img):
                st.session_state.images[idx] = img
                completed[0] += 1
                progress_bar.progress(
                    completed[0] / total_imgs,
                    text=f"生成中... 完了 {completed[0]}/{total_imgs}",
                )

            def _on_failure(idx, err):
                failures.append((idx, err))

            try:
                generate_article_images_parallel(
                    image_prompts=rewritten.image_prompts,
                    article_title=rewritten.title,
                    indices=remaining_indices,
                    quality=quality_choice,
                    max_workers=3,
                    on_complete=_on_complete,
                    on_failure=_on_failure,
                    image_styles=styles_list,
                )
            except Exception as e:
                progress_bar.empty()
                st.error(f"画像生成中に予期せぬエラー: {e}")
            else:
                progress_bar.progress(
                    completed[0] / total_imgs if total_imgs else 1.0,
                    text=f"完了 {completed[0]}/{total_imgs}",
                )
                if failures:
                    for idx, err in failures:
                        label = "サムネ" if idx == 0 else f"図解 {idx}"
                        st.error(
                            f"{label} (画像 {idx + 1}) 失敗: {err}。"
                            f"画像カード下の「再生成」ボタンで個別にリトライできます。"
                        )
                else:
                    st.success(f"{completed[0]}枚の画像を生成しました")
                st.session_state.wp_post = None
                st.rerun()
    else:
        st.success(f"全{total_imgs}枚生成済み — 各カード下の「再生成」で差し替えできます")

    # Per-image grid with regen buttons
    if total_imgs > 0:
        per_row = 3
        for row_start in range(0, total_imgs, per_row):
            row = st.columns(per_row)
            for col_offset in range(per_row):
                i = row_start + col_offset
                if i >= total_imgs:
                    break
                with row[col_offset]:
                    style_i = styles_list[i] if i < len(styles_list) else "figure"
                    style_label = _style_label.get(style_i, "図解")
                    label = f"{style_label} {i}" if i > 0 else "サムネイル"
                    img = st.session_state.images[i]
                    if img is not None:
                        st.image(img.pil_image, caption=f"{i + 1}. {label}")
                    else:
                        st.warning(f"{i + 1}. {label} — 未生成")
                    if st.button(
                        "再生成",
                        key=f"regen_img_{i}",
                        help="この1枚だけを生成し直します",
                    ):
                        with st.spinner(f"{label} を再生成中..."):
                            try:
                                new_img = generate_one_image(
                                    image_prompts=rewritten.image_prompts,
                                    index=i,
                                    article_title=rewritten.title,
                                    quality=quality_choice,
                                    image_styles=styles_list,
                                )
                                if new_img is not None:
                                    st.session_state.images[i] = new_img
                                    st.session_state.wp_post = None
                                    st.rerun()
                                else:
                                    st.error("画像が返ってきませんでした")
                            except Exception as e:
                                st.error(f"再生成失敗: {e}")

# ========================================
# Step 5: Publish to WordPress
# ========================================
_ready_to_publish = (
    st.session_state.rewritten
    and isinstance(st.session_state.images, list)
    and len(st.session_state.images) > 0
    and all(img is not None for img in st.session_state.images)
)

if _ready_to_publish:
    st.header("Step 5: WordPressに投稿")

    publish_status = st.radio(
        "投稿ステータス",
        ["draft", "publish"],
        format_func=lambda x: "下書き" if x == "draft" else "公開",
        index=0,
        horizontal=True,
    )

    if st.button("WordPressにアップロード & 投稿", type="primary"):
        progress = st.progress(0, text="準備中...")
        try:
            # 1. Upload images
            media_items = []
            total_steps = len(st.session_state.images) + 2
            for i, img in enumerate(st.session_state.images):
                progress.progress(
                    (i + 1) / total_steps,
                    text=f"画像 {i + 1}/{len(st.session_state.images)} をアップロード中...",
                )
                media = upload_image(
                    image_bytes=img.image_bytes,
                    filename=img.filename,
                    mime_type=img.mime_type,
                    alt_text=img.prompt,
                )
                media_items.append(media)

            # 2. Insert images into HTML
            progress.progress(
                (len(st.session_state.images) + 1) / total_steps,
                text="HTMLに画像を挿入中...",
            )
            final_html = insert_images_into_html(
                st.session_state.rewritten.html_content,
                media_items,
            )

            # 3. Create post
            progress.progress(
                (total_steps - 1) / total_steps,
                text="記事を投稿中...",
            )
            rewritten = st.session_state.rewritten
            wp_post = create_post(
                title=rewritten.title,
                html_content=final_html,
                slug=rewritten.slug,
                meta_description=rewritten.meta_description,
                featured_image_id=media_items[0].media_id if media_items else None,
                status=publish_status,
            )

            progress.progress(1.0, text="完了!")
            st.session_state.wp_post = wp_post

            st.success("投稿が完了しました!")
            st.markdown(f"**記事を見る**: [{wp_post.post_url}]({wp_post.post_url})")
            st.markdown(
                f"**管理画面で編集**: [{wp_post.edit_url}]({wp_post.edit_url})"
            )

        except Exception as e:
            progress.empty()
            st.error(f"投稿失敗: {e}")

# Show result if already posted
elif st.session_state.wp_post:
    st.header("投稿完了")
    wp_post = st.session_state.wp_post
    st.success("記事は既に投稿されています")
    st.markdown(f"**記事を見る**: [{wp_post.post_url}]({wp_post.post_url})")
    st.markdown(f"**管理画面で編集**: [{wp_post.edit_url}]({wp_post.edit_url})")
