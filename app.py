import streamlit as st

import config
from scraper import scrape_article, create_article_from_text
from rewriter import rewrite_article
from image_gen import generate_article_images
from wordpress import (
    test_connection,
    upload_image,
    create_post,
    insert_images_into_html,
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
    st.caption("LUNA WORK Salon")

# --- Session State ---
for key in ["scraped", "rewritten", "images", "wp_post"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ========================================
# Step 1: Article Input
# ========================================
st.header("Step 1: 踏襲する記事を入力")

input_tab_url, input_tab_text, input_tab_file = st.tabs(
    ["URLから取得", "テキスト貼り付け", "ファイルアップロード"]
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
    st.write("生成する画像のプロンプト:")
    for i, prompt in enumerate(rewritten.image_prompts):
        st.text(f"{i + 1}. {prompt}")

    if st.button("画像を生成", type="primary"):
        with st.spinner(f"Nano Banana 2で{len(rewritten.image_prompts)}枚の画像を生成中...（数分かかります）"):
            try:
                images = generate_article_images(
                    rewritten.image_prompts,
                    article_title=rewritten.title,
                )
                st.session_state.images = images
                st.session_state.wp_post = None
                st.success(f"{len(images)}枚の画像を生成しました")
            except Exception as e:
                st.error(f"画像生成失敗: {e}")

    # Show generated images
    if st.session_state.images:
        cols = st.columns(len(st.session_state.images))
        for i, (col, img) in enumerate(zip(cols, st.session_state.images)):
            with col:
                st.image(img.pil_image, caption=f"画像 {i + 1}")

# ========================================
# Step 5: Publish to WordPress
# ========================================
if st.session_state.rewritten and st.session_state.images:
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
