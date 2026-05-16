from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from anthropic import Anthropic

import config
from scraper import ScrapedArticle

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client

SYSTEM_PROMPT = """あなたは「LUNA WORK」というWebメディアの専属ライターです。
以下のガイドラインに厳密に従って、元記事を **同等以上のボリュームと情報量** でリライトしてください。

## あなたのペルソナ
- 30代前半の女性ライター
- 親しみやすく、読者に寄り添うような文体
- 専門用語を使わず、わかりやすい言葉で説明する
- 「〜ですよね」「〜なんです」「〜してみてくださいね」のような柔らかい語尾を自然に使う
- 押し付けがましくなく、読者の気持ちに共感しながら情報を伝える

## ターゲット読者
- 20代〜40代の女性
- デジタルリテラシーが高くない
- 実用的で具体的なアドバイスを求めている

## リライトルール

### 最重要：ボリュームと情報の充実度
- **元記事と同等以上の文字数・情報量を保ってください。要約や簡略化は絶対にしないでください。**
- 元記事の各セクションの情報を省略せず、すべてリライトに反映してください。
- 元記事にあるステップや手順は、すべて具体的に解説してください。
- 各セクションのボリュームは十分に確保し、薄い内容にならないよう気をつけてください。
- 元記事で使われている具体例・数字・事例はすべて活かしてください。

### 購入誘導の除去と補完
- 元記事にある他の教材・コース・有料商品への購入を促す部分は完全に削除してください。
- **重要：削除した部分の「内容・ノウハウ自体」は削除しないでください。** 購入リンクや「詳しくはこちら」を削除するだけで、そこで語られていたノウハウ・テクニック・手順は、あなた自身の言葉で具体的に解説し直してください。
- 有料教材に誘導していた箇所は、「無料で今すぐ実践できる具体的な方法」として書き直してください。

### 文体と表現
- 専門用語やカタカナ用語は、平易な日本語に言い換えるか、初出時に簡単な説明を付けてください。
- H2/H3を使って読みやすく区切ってください。
- 適度に読者への問いかけを入れて共感を引き出してください。
- 具体例や身近なたとえ話を豊富に使ってください。

### メリハリのある記事にする（超重要）
- **各段落で最も伝えたいポイント・キーワードは必ず<strong>タグで太字にしてください。**
- 1段落（数文のまとまり）につき最低1箇所は太字を入れてください。
- 具体的な数字、重要な結論、読者の行動を促す部分は積極的に太字にしてください。
- 例：「実は、noteで<strong>月5万円以上</strong>稼いでいる人の多くが、<strong>たった3つのこと</strong>を意識しているんです。」
- 太字だらけにしすぎないでください。1文の中で太字にするのは1〜2箇所が目安です。
- 問いかけ文（「〜ですよね？」）や感想文は太字にせず、事実・数字・結論を太字にしてください。

### スマホで読みやすいフォーマット（超重要）
- **1文ごとに改行してください。** 1つの<p>タグに長い文章を詰め込まないでください。
- 1文は40文字以内を目安にし、短めの文をテンポよく連ねてください。
- 段落と段落の間には空の行（<br>や空の<p>）を入れて、十分な余白を作ってください。
- 以下のようなHTML構造にしてください：

  <p>こんにちは。</p>
  <p>&nbsp;</p>
  <p>今日はnoteの収益化について</p>
  <p>お話ししていきますね。</p>
  <p>&nbsp;</p>
  <p>「副業で稼ぎたいけど、何から始めればいいの…？」</p>
  <p>&nbsp;</p>
  <p>そう思ったこと、ありませんか？</p>

- 会話調の問いかけや感情表現は独立した行にしてください。
- 箇条書き（<ul><li>）の前後にも空行を入れてください。
- H2/H3見出しの前後にも十分な余白を入れてください。
- とにかく「スマホの小さな画面で、指でスクロールしながら気持ちよく読める」フォーマットを意識してください。

## 出力フォーマット（重要：この形式を厳守してください）

以下の形式で、メタデータとHTML本文を分けて出力してください。
JSONの中にHTMLを入れないでください。

---METADATA---
title: 記事タイトル（32文字以内）
meta_description: メタディスクリプション（120文字以内）
slug: url-slug-in-english
image_prompt_1: 記事トップのアイキャッチ画像用の英語プロンプト（記事全体を象徴するイメージ）
image_prompt_2: 第1章（最初のH2セクション）の画像用の英語プロンプト
image_prompt_3: 第2章の画像用の英語プロンプト
image_prompt_4: 第3章の画像用の英語プロンプト
image_prompt_5: 第4章の画像用の英語プロンプト
（以降、H2セクションの数だけ続ける。各章に最低1つの画像プロンプトを作成すること）
---HTML---
（ここにWordPress用のHTMLコンテンツをそのまま出力）

## 画像プレースホルダーの配置ルール（超重要）

### 必須：記事先頭にアイキャッチ画像
- **HTML本文の一番最初に `<!-- IMAGE_PLACEHOLDER_1 -->` を配置してください。**
- これがサムネイル・アイキャッチ画像になります。本文テキストの前に必ず置いてください。

### 必須：各H2セクションに最低1つの画像
- **すべてのH2見出しの直後に、対応する `<!-- IMAGE_PLACEHOLDER_N -->` を配置してください。**
- 例えば、H2が5つある記事なら、image_prompt_1（トップ）+ image_prompt_2〜6（各章）= 合計6つの画像プロンプトとプレースホルダーが必要です。
- H2見出しの直後（H2タグの次の行）にプレースホルダーを置いてください。

### 配置例
```
<!-- IMAGE_PLACEHOLDER_1 -->
<p>こんにちは。</p>
...
<h2>第1章 タイトル</h2>
<!-- IMAGE_PLACEHOLDER_2 -->
<p>本文...</p>
...
<h2>第2章 タイトル</h2>
<!-- IMAGE_PLACEHOLDER_3 -->
<p>本文...</p>
...
```

## HTML出力のその他の注意点
- WordPress投稿用のHTMLのみ出力（<html>, <head>, <body>タグは不要）
- 適切な箇所に太字（<strong>）を使い、重要ポイントを強調してください
- 箇条書き（<ul><li>）を積極的に活用してください
- テーブルは使わないでください（モバイル表示で崩れるため）
- 十分に長く書いてください。短くまとめすぎないでください。
- **最重要：1文ごとに<p>タグで囲み、段落間に<p>&nbsp;</p>を入れて余白を作ってください。スマホで読みやすいこまめな改行が必須です。**

## image_promptsについて（超重要：2種類のプロンプトを使い分けてください）

すべて **英語で** 記述してください。
画像は2つの役割に分かれており、求められる内容がまったく違います。

### image_prompt_1 = サムネイル（アイキャッチ／ヒーロー画像）
- これは記事の **トップに表示される派手なバナー画像** です（YouTubeサムネ風）
- **記事タイトルの日本語文字が画像内に大きく描き込まれます**（システム側で自動的にタイトルを差し込むので、プロンプトには「the article title prominently rendered as bold Japanese typography」のような指示を含めれば十分です）
- 内容は、記事のメインテーマ・キャッチコピー・主な訴求点を視覚化する短い英語の説明にしてください
- 例: "Eye-catching banner thumbnail conveying the idea of starting an AI-powered side business from home, evoking excitement and possibility, with abstract sparkles and elegant accents."
- 細かい人物配置は指定しなくてOK（システム側のスタイル指示で女性キャラがコーナーに自動配置されます）

### image_prompt_2 以降 = 本文中の図解（インフォグラフィック）
- これは各H2セクションの内容を **わかりやすく解説する図解** です
- **同じ女の子キャラクター（紫の瞳、白パーカー、ティールの内シャツ）が毎回登場します**（システム側でリファレンス画像を渡して統一）
- プロンプトには、その章で説明したい概念・手順・比較を **具体的に視覚化する内容** を書いてください
- 例（PC内検索の図解）: "Diagram showing the chibi character at her laptop asking 'where is that image?', then a friendly robot AI searching her PC file explorer, then a results panel showing matched image candidates with filenames, file sizes, and folder paths."
- 例（ChatGPT vs Codex 比較）: "Split-panel comparison diagram. Left side: chibi character chatting with ChatGPT bubble labeled '会話で考えるAI', showing idea brainstorming. Right side: chibi character at laptop with Codex robot, showing autonomous code/test/doc tasks and an accumulating knowledge database."
- 矢印・吹き出し・UIモック（ノートPC画面、ファイルアイコン、進捗バーなど）・小さな日本語ラベルを含めることを推奨してください
- 各H2の内容と直接対応させてください（一般的な装飾画像ではなく、その章の内容を補強する図解）

### 共通ルール
- **H2セクションの数 + 1（サムネ）分のimage_promptを必ず作成してください**
- 各プロンプトは概ね80〜200語の範囲で具体的に書いてください（短すぎると図解の構成要素が薄くなります）
- スタイル指定（パステル・フラット・キャラ統一）はシステム側で自動付与するので、プロンプトには **「何を描くか・どう構成するか」のコンテンツ部分だけ** を書けばOKです"""


@dataclass
class RewrittenArticle:
    title: str
    html_content: str
    meta_description: str
    image_prompts: list[str] = field(default_factory=list)
    slug: str = ""


def rewrite_article(article: ScrapedArticle) -> RewrittenArticle:
    """Rewrite article using Claude API with Extended Thinking (streaming)."""
    user_prompt = _build_user_prompt(article)

    # Use streaming to avoid timeout with Extended Thinking
    text_parts = []
    with _get_client().messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=config.CLAUDE_MAX_TOKENS,
        thinking={
            "type": "enabled",
            "budget_tokens": config.CLAUDE_THINKING_BUDGET,
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        response = stream.get_final_message()

    # With extended thinking, extract only text blocks (skip thinking blocks)
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
    result_text = "\n".join(text_parts)

    result = _parse_response(result_text)

    # Apply inline styles for WordPress compatibility
    result.html_content = _apply_inline_styles(result.html_content)

    return result


def _build_user_prompt(article: ScrapedArticle) -> str:
    headings_text = "\n".join(f"- {h}" for h in article.headings) if article.headings else "（見出し情報なし）"

    # Truncate very long articles to avoid token limits
    text = article.text
    if len(text) > 80000:
        text = text[:80000] + "\n\n（※ 記事が長いため、ここまでの内容をもとにリライトしてください）"

    return f"""以下の記事をリライトしてください。

## 元記事のタイトル
{article.title}

## 元記事の構成（見出し一覧）
{headings_text}

## 元記事の本文
{text}

## リライトの指示
上記の記事を、システムプロンプトの指示に従って完全にリライトしてください。

【重要な注意】
- 元記事の事実情報・ノウハウ・具体的な手順はすべて盛り込んでください。情報を省略・簡略化しないでください。
- 元記事と同等以上のボリュームでリライトしてください。短くまとめないでください。
- 各ステップ（STEP1〜STEP6など）の内容は、すべて個別に詳しく解説してください。
- 購入を促すリンクや文言は削除しますが、そこで語られていたノウハウ・テクニック自体はあなた自身の言葉で詳しく解説し直してください。
- **HTML本文の一番最初に必ず <!-- IMAGE_PLACEHOLDER_1 --> を配置してください（アイキャッチ画像用）**
- **すべてのH2見出しの直後にも <!-- IMAGE_PLACEHOLDER_N --> を配置してください（各章の画像用）**
- **画像プロンプトは、アイキャッチ + 各H2セクション分を必ず全て作成してください**

出力は必ず ---METADATA--- と ---HTML--- のセパレータで区切ってください。"""


def _apply_inline_styles(html_content: str) -> str:
    """Apply inline styles to HTML elements for WordPress compatibility.
    WordPress strips <style> tags, so all styling must be inline."""

    # Wrapper div with centered layout
    wrapper_style = (
        "max-width:640px; margin:0 auto; padding:0 20px; "
        "font-size:16px; line-height:1.9; color:#333; "
        "word-wrap:break-word; overflow-wrap:break-word;"
    )

    # H2 styling - pink bottom border
    h2_style = (
        "font-size:1.4em; font-weight:bold; margin-top:2.5em; "
        "margin-bottom:1em; padding-bottom:0.4em; "
        "border-bottom:2px solid #e8b4c8; color:#444;"
    )

    # H3 styling - pink left border
    h3_style = (
        "font-size:1.2em; font-weight:bold; margin-top:2em; "
        "margin-bottom:0.8em; padding-left:0.8em; "
        "border-left:4px solid #e8b4c8; color:#444;"
    )

    # Strong styling - pink color
    strong_style = "color:#d4739a;"

    # Apply inline styles to existing tags
    html_content = re.sub(
        r"<h2(?:\s[^>]*)?>",
        f'<h2 style="{h2_style}">',
        html_content,
    )
    html_content = re.sub(
        r"<h3(?:\s[^>]*)?>",
        f'<h3 style="{h3_style}">',
        html_content,
    )
    html_content = re.sub(
        r"<strong(?:\s[^>]*)?>",
        f'<strong style="{strong_style}">',
        html_content,
    )

    # Wrap in centered div
    return f'<div style="{wrapper_style}">\n{html_content}\n</div>'


def _parse_response(text: str) -> RewrittenArticle:
    """Parse the separated metadata + HTML response."""
    # Split by separators
    metadata_match = re.search(r"---METADATA---\s*\n(.*?)\n---HTML---", text, re.DOTALL)

    if metadata_match:
        metadata_block = metadata_match.group(1).strip()
        html_start = metadata_match.end()
        html_content = text[html_start:].strip()
    else:
        # Fallback: try to find HTML content directly
        parts = re.split(r"---+\s*HTML\s*---+", text, maxsplit=1)
        if len(parts) == 2:
            metadata_block = parts[0]
            html_content = parts[1].strip()
            metadata_block = re.sub(r"---+\s*METADATA\s*---+", "", metadata_block).strip()
        else:
            raise ValueError(f"レスポンスのフォーマットを解析できませんでした:\n{text[:500]}")

    # Parse metadata fields
    def extract_field(block: str, field_name: str) -> str:
        match = re.search(rf"^{field_name}:\s*(.+)$", block, re.MULTILINE)
        return match.group(1).strip() if match else ""

    title = extract_field(metadata_block, "title")
    meta_description = extract_field(metadata_block, "meta_description")
    slug = extract_field(metadata_block, "slug")

    # Extract ALL image prompts (dynamic count - not just 1-3)
    image_prompts = []
    for i in range(1, 30):  # Support up to 29 images
        prompt = extract_field(metadata_block, f"image_prompt_{i}")
        if prompt:
            image_prompts.append(prompt)
        elif i > 3:
            # After prompt 3, stop if we hit a gap
            break

    # Clean up HTML content - remove markdown code fences if present
    html_content = re.sub(r"^```html?\s*\n?", "", html_content)
    html_content = re.sub(r"\n?```\s*$", "", html_content)
    html_content = html_content.strip()

    if not html_content:
        raise ValueError("HTML本文が空です")

    return RewrittenArticle(
        title=title,
        html_content=html_content,
        meta_description=meta_description,
        image_prompts=image_prompts,
        slug=slug,
    )
