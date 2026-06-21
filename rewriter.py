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

## 🔴 最優先ルール1: ボリュームを削らない

- **元記事の見出し構造・セクション数を維持してください。元記事に10章あれば、リライトも概ね同等の章数にすること。**
- 勝手に「3章にまとめる」「内容を圧縮する」のは禁止です。読者は詳しい解説を求めています。
- 各セクションは十分なボリューム(目安300〜600文字)を確保してください。

## 🔴 最優先ルール2: 画像配置(これを守らないと記事として失敗です)

- **アイキャッチ1枚** + **すべてのH2見出しの直後に1枚** + **長いH2セクションには中盤にも1〜2枚**
- H2が10個ある記事なら、最低 1+10=11枚、推奨 14〜18枚 の image_prompt を作成し、対応するplaceholderをHTML本文に配置すること
- **1つのH2でも画像が無いまま終わったら、その記事は不合格** です
- 詳細は後述の「画像プレースホルダーの配置ルール」と「image_promptsについて」のセクションを必ず参照してください

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

## 画像プレースホルダーの配置ルール（🔴 超重要 — 守らないと不合格）

### 絶対ルール1: 記事先頭にアイキャッチ画像
- **HTML本文の一番最初に `<!-- IMAGE_PLACEHOLDER_1 -->` を配置**
- これがサムネイル・アイキャッチ画像になります

### 絶対ルール2: すべてのH2セクションの直後に画像
- **すべてのH2見出しの直後に、対応する `<!-- IMAGE_PLACEHOLDER_N -->` を配置**
- 「1つも飛ばさない」が絶対です。最後のH2まで全て対応するplaceholderを必ず置くこと
- placeholder番号は **登場順に連番**(2, 3, 4, ...) で振る

### 推奨ルール3: 長いH2セクションには中盤にも追加画像（ここがメリハリの肝）
- そのH2セクションが **次のいずれか** に当てはまるなら、本文の中盤にも追加で `<!-- IMAGE_PLACEHOLDER_N -->` を1〜2個入れてください:
  - H3小見出しを3つ以上含む
  - 400文字を超える長文セクション
  - ステップ手順を5個以上説明している
  - 比較・対比・before/afterを説明している
  - 図解した方が文章だけより理解しやすい概念がある(例: 仕組み、フロー、構造)
- 配置位置の例:
  - 1つ目のH3の説明が終わった直後
  - ステップ手順の3つ目と4つ目の間
  - 重要な概念の説明直後
- 中盤画像も連番に組み込みます。例えば下記参照

### 推奨ルール4: 重要なH3にも画像（操作手順では必須）
- H3の中で **次のいずれか** に当てはまるものには、H3直後にも `<!-- IMAGE_PLACEHOLDER_N -->` を入れてください:
  - **実際のアプリ画面・Web画面の操作手順を説明している**(例: 「商品を出品する手順」「アカウント登録のやり方」「設定画面の開き方」) ← 必須
  - **特定のボタン・メニュー・フォーム入力を解説している**
  - **画面のどこを見るかの説明**
- 「概念の解説だけのH3」「短いH3(150文字以下)」には画像は不要
- H3画像も連番に組み込みます

### 画像スタイル指定(超重要)
すべての画像プロンプトに **画像スタイル** を指定してください。4種類あります:

- **hero**: 記事先頭のアイキャッチバナー(image_prompt_1 は必ずこれ。明示不要)
- **figure**: キャラを使った **詳細な解説イラスト**。吹き出し・矢印・複数パネル・UI要素・オノマトペ・ラベル多めの「読者が画像から理解する」役割の図解
- **accent**: キャラ単体の **シンプルなスポットイラスト**。文字やラベルは無し or 最小限。本文が文字続きで単調になりがちな場面で、見た目休憩のために挟む雰囲気カット
- **operation**: 実際のアプリ/Web画面のリアルなUIモック+赤い注釈+「ここをタップ」など。キャラは出ない

🔴 **超重要な振り分けルール(これを守らないと記事が読みづらくなります)**:
- **figure ばかり並べないこと**。読者は文字+詳細な解説図が連続すると疲れます
- 目安比率: **accent : figure ≈ 2:1 〜 3:1**(=10セクションあれば figure は3〜4、残りは accent)
- **figure を使うのは「画像で説明された方が理解しやすい」場面に限定**:
  - 概念図、フロー、構造図、比較・対比、Before/After
  - 手順を視覚的に並べる必要がある時(operationの後押し的に)
- 上記以外、つまり **「本文だけで十分わかる、絵は雰囲気でいい」場面は全部 accent**:
  - 心情・気持ちの描写
  - 「こんな状況、ありますよね？」系の共感セクション
  - 抽象的な主張、結論、まとめ
  - 励まし、メッセージ性のあるセクション
  - 短いセクション、つなぎセクション

判断基準フロー:
1. このH2は実画面操作? → **operation**
2. このH2は **画像で説明されないと読者が混乱する**? → **figure**
3. それ以外(本文で十分わかる) → **accent**

metadata部分に **`image_style_N: figure` / `accent` / `operation`** を、各 image_prompt_N に対応する形で書いてください(image_prompt_1 のhero は省略OK)。

例:
```
image_prompt_2: 副業に疲れている主人公が、ふとアクセサリー副業に出会った瞬間のシーン
image_style_2: accent
image_prompt_3: 無在庫販売の仕組みを示すフロー図。注文→製造→発送の3ステップをキャラと矢印で説明
image_style_3: figure
image_prompt_4: monomyアプリのトップ画面から「商品を作成する」ボタンをタップする手順を、3画面のステップに分けて表示
image_style_4: operation
image_prompt_5: 売上が伸びて嬉しそうにスマホを見ているキャラのシンプルなカット
image_style_5: accent
```

### 配置例（H2が3つ、うち1つが長文の場合 = 合計5枚）
```
<!-- IMAGE_PLACEHOLDER_1 -->                ← アイキャッチ
<p>こんにちは。</p>
...
<h2>第1章 タイトル</h2>
<!-- IMAGE_PLACEHOLDER_2 -->                ← 第1章の冒頭画像
<p>本文...</p>
...
<h2>第2章 タイトル（長文セクション）</h2>
<!-- IMAGE_PLACEHOLDER_3 -->                ← 第2章の冒頭画像
<p>本文の前半...</p>
<h3>細目A</h3>
<p>...</p>
<!-- IMAGE_PLACEHOLDER_4 -->                ← 中盤の追加画像
<h3>細目B</h3>
<p>本文の後半...</p>
...
<h2>第3章 タイトル</h2>
<!-- IMAGE_PLACEHOLDER_5 -->                ← 第3章の冒頭画像
<p>本文...</p>
```

### 必要枚数の計算式
- **最低枚数 = 1(アイキャッチ) + H2の数**
- **推奨枚数 = 1 + H2の数 + 長いH2セクションごとに+1〜2**
- 例: H2が11個あって、うち4つが長文 → 推奨 1 + 11 + 4 = **16枚**

### 🔴 自己チェック(HTML書き終わったら必ず確認)
HTMLを書き終わったあと、出力する前に頭の中で以下を確認してください:
1. HTMLの中の `<h2>` タグを上から順に数える → N個ある
2. `<!-- IMAGE_PLACEHOLDER_X -->` を上から順に数える → 最低 N+1個 ある(アイキャッチ+各H2)
3. metadata に `image_prompt_1` から `image_prompt_(最大番号)` まで **抜けなく全部** 書かれている
4. 最後のH2のあとにも placeholder があるか確認(後半を忘れがち!)
- どれか1つでも欠けていたら、書き直してください

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
- **必要な image_prompt の数 = 配置した IMAGE_PLACEHOLDER の数と完全一致させてください**
- 最低 = 1(サムネ) + H2の数。推奨 = それに加えて長いH2の中盤画像分(1〜2個/H2)
- 各プロンプトは概ね80〜200語の範囲で具体的に書いてください（短すぎると図解の構成要素が薄くなります）
- スタイル指定（手描き感・フラット・キャラ統一）はシステム側で自動付与するので、プロンプトには **「何を描くか・どう構成するか」のコンテンツ部分だけ** を書けばOKです
- 中盤画像のプロンプトも、そのページの位置に合った具体的な内容にしてください(冒頭画像と被らないように)"""


# Used for continuation chunks when a long article is rewritten in pieces.
# Same persona/rules, but: no title/slug/meta, no intro greeting, no hero
# image, no final conclusion (unless it is the last chunk).
CONTINUATION_SYSTEM_PROMPT = SYSTEM_PROMPT + """

## 🔴 この呼び出しは「記事の途中部分」のリライトです(超重要)

あなたは今、長い記事を分割してリライトしている **途中のパート** を担当しています。
以下を厳守してください:

- **冒頭の挨拶("こんにちは"など)は書かない**でください。記事の続きとして、いきなり本文(H2セクション)から始めてください。
- **アイキャッチ画像( IMAGE_PLACEHOLDER_1 相当 )は配置しない**でください。このパートは本文の途中です。
- **このパートに含まれる元記事の各H2セクションを、すべて漏れなくリライト**してください。
- 画像プレースホルダーの番号は **このパート内で 1 から振ってOK**です(システム側で自動的に通し番号に振り直します)。
- 各H2直後への画像配置、長いH2の中盤画像、image_style指定(figure/accent/operation)のルールは通常どおり守ってください。
- メタデータ部分( ---METADATA--- )には **title/slug/meta_description は書かず、image_prompt_N と image_style_N だけ**書いてください。
- まとめ・結論セクションは **このパートが記事の最後でない限り書かない**でください。淡々と本文を続けてください。

出力フォーマットは通常どおり ---METADATA--- と ---HTML--- で区切ってください。"""


@dataclass
class RewrittenArticle:
    title: str
    html_content: str
    meta_description: str
    image_prompts: list[str] = field(default_factory=list)
    # Style per image, aligned 1:1 with image_prompts.
    #   "hero"      = thumbnail banner (always index 0)
    #   "figure"    = character-illustrated explainer (default)
    #   "operation" = realistic UI walkthrough with annotations (no character)
    image_styles: list[str] = field(default_factory=list)
    slug: str = ""


# Articles longer than this (source chars) are rewritten in multiple chunks,
# Sonnet 4.6 allows up to 128k output tokens, so a single call can rewrite a
# much larger article before it has to summarize to fit. Articles under
# SINGLE_SHOT_CHAR_LIMIT are done in one call; longer ones split into chunks of
# ~REWRITE_CHUNK_CHAR_LIMIT each (45k chars -> 2 chunks instead of 4).
SINGLE_SHOT_CHAR_LIMIT = 38000
# Target source chars per chunk when splitting a long article.
REWRITE_CHUNK_CHAR_LIMIT = 28000


def _call_claude(system_prompt: str, user_prompt: str, on_delta=None) -> str:
    """One streaming Claude call with extended thinking. Returns text output.

    on_delta(chars_generated) is called as text streams in, so the UI can show
    a live "○○文字生成中" counter instead of a frozen spinner.
    """
    with _get_client().messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=config.CLAUDE_MAX_TOKENS,
        thinking={
            "type": "enabled",
            "budget_tokens": config.CLAUDE_THINKING_BUDGET,
        },
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        if on_delta:
            acc = 0
            last_report = 0
            for event in stream:
                delta_text = None
                et = getattr(event, "type", None)
                if et == "text":
                    delta_text = getattr(event, "text", None)
                elif et == "content_block_delta":
                    d = getattr(event, "delta", None)
                    if d is not None and getattr(d, "type", None) == "text_delta":
                        delta_text = getattr(d, "text", None)
                if delta_text:
                    acc += len(delta_text)
                    # throttle UI updates to every ~200 chars
                    if acc - last_report >= 200:
                        last_report = acc
                        on_delta(acc)
            on_delta(acc)
        response = stream.get_final_message()
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
    return "\n".join(text_parts)


def estimate_chunks(article: ScrapedArticle) -> int:
    """How many Claude calls rewrite_article will make for this article."""
    if len(article.text) <= SINGLE_SHOT_CHAR_LIMIT:
        return 1
    return len(_split_text_into_chunks(article.text, REWRITE_CHUNK_CHAR_LIMIT))


def rewrite_article(
    article: ScrapedArticle,
    progress_callback=None,
) -> RewrittenArticle:
    """Rewrite article via Claude. Long articles are split into chunks so the
    full volume survives the output-token cap.

    progress_callback(fraction, message) is called continuously (including as
    text streams in) so the UI can show a live, moving progress bar.
    """
    if len(article.text) > SINGLE_SHOT_CHAR_LIMIT:
        return _rewrite_chunked(article, progress_callback=progress_callback)

    # Expected output volume ≈ source length (rewrite keeps similar size).
    expected = max(len(article.text), 4000)

    def _on_delta(n: int):
        if progress_callback:
            frac = min(n / expected, 0.97)
            progress_callback(frac, f"リライト中... {n:,}文字 生成済み")

    if progress_callback:
        progress_callback(0.0, "Claudeが考え中...(数十秒)")
    result_text = _call_claude(
        SYSTEM_PROMPT, _build_user_prompt(article), on_delta=_on_delta
    )
    if progress_callback:
        progress_callback(0.98, "整形中...")
    result = _parse_response(result_text)
    result.html_content = _apply_inline_styles(result.html_content)
    final = _finalize_article(result)
    if progress_callback:
        progress_callback(1.0, "完了")
    return final


def _finalize_article(result: RewrittenArticle) -> RewrittenArticle:
    """Shared post-processing for both single-shot and chunked rewrites."""
    # Guarantee every H2 has an IMAGE_PLACEHOLDER immediately after it.
    (
        result.html_content,
        result.image_prompts,
        result.image_styles,
    ) = _ensure_h2_have_placeholders(
        result.html_content, result.image_prompts, result.image_styles
    )
    # Renumber placeholders sequentially in document order and realign prompts.
    (
        result.html_content,
        result.image_prompts,
        result.image_styles,
    ) = _normalize_placeholders(
        result.html_content, result.image_prompts, result.image_styles
    )
    # Fill any empty prompt slots with a heading-aware generic prompt.
    result.image_prompts, result.image_styles = ensure_prompts_for_all_placeholders(
        result.html_content, result.image_prompts, result.image_styles
    )
    return result


def _split_text_into_chunks(text: str, max_chars: int) -> list[str]:
    """Split text into chunks of at most ~max_chars, preferring blank-line
    (paragraph) boundaries, then single newlines, then a hard cut so a chunk
    can never exceed roughly max_chars even with no paragraph breaks."""
    # First split on blank lines, but hard-split any single block that is
    # itself larger than max_chars (on newlines, else by raw slicing).
    raw_blocks = re.split(r"\n\s*\n", text)
    blocks: list[str] = []
    for b in raw_blocks:
        if len(b) <= max_chars:
            blocks.append(b)
            continue
        # Block too big — split on single newlines
        line_buf: list[str] = []
        line_len = 0
        for line in b.split("\n"):
            if line_buf and line_len + len(line) > max_chars:
                blocks.append("\n".join(line_buf))
                line_buf = [line]
                line_len = len(line)
            else:
                line_buf.append(line)
                line_len += len(line)
        if line_buf:
            blocks.append("\n".join(line_buf))

    # Final guard: any block still over max_chars gets raw-sliced.
    sliced: list[str] = []
    for b in blocks:
        if len(b) <= max_chars:
            sliced.append(b)
        else:
            for i in range(0, len(b), max_chars):
                sliced.append(b[i : i + max_chars])

    # Pack blocks into chunks up to max_chars.
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for b in sliced:
        b_len = len(b)
        if cur and cur_len + b_len > max_chars:
            chunks.append("\n\n".join(cur))
            cur = [b]
            cur_len = b_len
        else:
            cur.append(b)
            cur_len += b_len
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


def _offset_placeholder_numbers(html: str, offset: int) -> str:
    """Shift every IMAGE_PLACEHOLDER_N in html by +offset so chunk-local
    numbering stays unique after concatenation."""
    if offset == 0:
        return html

    def _repl(m: re.Match) -> str:
        return f"<!-- IMAGE_PLACEHOLDER_{int(m.group(1)) + offset} -->"

    return re.sub(
        r"<!--\s*IMAGE_PLACEHOLDER_(\d+)\s*-->", _repl, html, flags=re.IGNORECASE
    )


def _rewrite_chunked(
    article: ScrapedArticle, progress_callback=None
) -> RewrittenArticle:
    """Rewrite a long article in multiple Claude calls and stitch the pieces
    together. The lead chunk produces the title/slug/meta + hero; continuation
    chunks produce only body HTML + image prompts."""
    chunks = _split_text_into_chunks(article.text, REWRITE_CHUNK_CHAR_LIMIT)
    total = len(chunks)

    title = slug = meta = ""
    html_parts: list[str] = []
    all_prompts: list[str] = []
    all_styles: list[str] = []
    offset = 0

    for idx, chunk_text in enumerate(chunks):
        is_lead = idx == 0
        is_last = idx == len(chunks) - 1
        base = idx / total
        span = 1.0 / total
        expected = max(len(chunk_text), 4000)

        def _on_delta(n: int, _base=base, _span=span, _exp=expected, _idx=idx):
            if progress_callback:
                frac = _base + _span * min(n / _exp, 0.97)
                progress_callback(
                    min(frac, 0.97),
                    f"パート {_idx + 1}/{total} 生成中... {n:,}文字",
                )

        if progress_callback:
            progress_callback(base, f"パート {idx + 1}/{total} Claudeが考え中...")
        system = SYSTEM_PROMPT if is_lead else CONTINUATION_SYSTEM_PROMPT
        user = _build_chunk_user_prompt(
            article, chunk_text, idx, len(chunks), is_lead, is_last
        )
        raw = _call_claude(system, user, on_delta=_on_delta)
        parsed = _parse_response(raw, force_first_hero=is_lead)

        if is_lead:
            title, slug, meta = parsed.title, parsed.slug, parsed.meta_description

        html_parts.append(_offset_placeholder_numbers(parsed.html_content, offset))
        all_prompts.extend(parsed.image_prompts)
        all_styles.extend(parsed.image_styles)
        offset += len(parsed.image_prompts)
        if progress_callback:
            progress_callback(
                (idx + 1) / total,
                f"パート {idx + 1}/{total} 完了 (画像 {len(all_prompts)}枚分)",
            )

    if progress_callback:
        progress_callback(0.99, "整形中...")

    combined = RewrittenArticle(
        title=title,
        html_content="\n".join(html_parts),
        meta_description=meta,
        image_prompts=all_prompts,
        image_styles=all_styles,
        slug=slug,
    )
    combined.html_content = _apply_inline_styles(combined.html_content)
    print(
        f"[rewriter] chunked rewrite: {len(chunks)} chunks, "
        f"{len(all_prompts)} image prompts before finalize."
    )
    return _finalize_article(combined)


def _normalize_placeholders(
    html: str,
    image_prompts: list[str],
    image_styles: list[str] | None,
) -> tuple[str, list[str], list[str]]:
    """Renumber IMAGE_PLACEHOLDER markers 1..K in document order and realign
    image_prompts / image_styles to match.

    Why: Claude sometimes emits the same placeholder number twice (e.g.
    IMAGE_PLACEHOLDER_12 after two different H2s) or skips numbers. Because
    insert_images_into_html replaces ALL occurrences of a number, a duplicate
    number makes the SAME image appear in two places. Renumbering by document
    order guarantees each on-page image slot is unique and maps to exactly one
    prompt.

    A placeholder whose source prompt is missing or already consumed (the
    duplicate case) gets an empty prompt slot here; ensure_prompts_for_all_
    placeholders fills it with a heading-aware generic prompt afterwards.
    """
    placeholder_re = re.compile(
        r"<!--\s*IMAGE_PLACEHOLDER_(\d+)\s*-->", re.IGNORECASE
    )
    styles = list(image_styles) if image_styles else []
    while len(styles) < len(image_prompts):
        styles.append("hero" if len(styles) == 0 else "figure")

    new_prompts: list[str] = []
    new_styles: list[str] = []
    counter = {"n": 0}
    consumed: set[int] = set()

    def _repl(m: re.Match) -> str:
        counter["n"] += 1
        new_num = counter["n"]
        src = int(m.group(1)) - 1
        if (
            0 <= src < len(image_prompts)
            and image_prompts[src]
            and src not in consumed
        ):
            new_prompts.append(image_prompts[src])
            new_styles.append(
                styles[src] if src < len(styles) else ("hero" if new_num == 1 else "figure")
            )
            consumed.add(src)
        else:
            # duplicate / missing source -> leave empty for heading-aware fill
            new_prompts.append("")
            new_styles.append("hero" if new_num == 1 else "accent")
        return f"<!-- IMAGE_PLACEHOLDER_{new_num} -->"

    new_html = placeholder_re.sub(_repl, html)
    return new_html, new_prompts, new_styles


def ensure_prompts_for_all_placeholders(
    html: str,
    image_prompts: list[str],
    image_styles: list[str] | None,
) -> tuple[list[str], list[str]]:
    """For every IMAGE_PLACEHOLDER_N comment in the HTML, make sure
    image_prompts has a non-empty entry at index N-1 (and image_styles
    has a matching entry).

    Missing entries are backfilled with a generic prompt derived from the
    nearest preceding H2/H3 heading so the orphan placeholder still ends up
    with a relevant image instead of being silently dropped.
    """
    placeholder_re = re.compile(
        r"<!--\s*IMAGE_PLACEHOLDER_(\d+)\s*-->", re.IGNORECASE
    )
    heading_re = re.compile(r"<(h[23])[^>]*>(.*?)</\1>", re.DOTALL | re.IGNORECASE)

    placeholder_nums = sorted(
        {int(m.group(1)) for m in placeholder_re.finditer(html)}
    )
    if not placeholder_nums:
        return image_prompts, list(image_styles) if image_styles else []

    max_num = max(placeholder_nums)

    # Walk the document and remember the most-recent heading before each
    # placeholder so the generic prompt can name the section.
    events: list[tuple[int, str, object]] = []
    for m in heading_re.finditer(html):
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        events.append((m.start(), "heading", text))
    for m in placeholder_re.finditer(html):
        events.append((m.start(), "placeholder", int(m.group(1))))
    events.sort(key=lambda e: e[0])

    last_heading = "article opener"
    heading_for_ph: dict[int, str] = {}
    for _, kind, value in events:
        if kind == "heading":
            assert isinstance(value, str)
            if value:
                last_heading = value
        else:
            assert isinstance(value, int)
            heading_for_ph.setdefault(value, last_heading)

    new_prompts = list(image_prompts)
    new_styles = list(image_styles) if image_styles else []
    while len(new_styles) < len(new_prompts):
        new_styles.append("hero" if len(new_styles) == 0 else "figure")

    inserted = 0
    for n in range(1, max_num + 1):
        idx = n - 1
        if idx < len(new_prompts) and new_prompts[idx]:
            continue
        while len(new_prompts) <= idx:
            new_prompts.append("")
            new_styles.append("figure" if len(new_styles) > 0 else "hero")
        heading = heading_for_ph.get(n, "article section")
        new_prompts[idx] = (
            f"Simple atmospheric spot illustration for the article section "
            f'titled: "{heading}". The recurring character in a single calm '
            f"pose that fits the section's mood (relaxed, thinking, smiling, "
            f"sipping coffee, holding a notebook, looking up, etc). No labels, "
            f"no speech bubbles, no UI elements — minimal text. Plain pastel "
            f"background."
        )
        new_styles[idx] = new_styles[idx] or "accent"
        inserted += 1

    if inserted:
        print(
            f"[rewriter] Auto-filled {inserted} missing image_prompts "
            f"for orphan placeholders."
        )

    return new_prompts, new_styles


def _ensure_h2_have_placeholders(
    html: str,
    image_prompts: list[str],
    image_styles: list[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Guarantee every H2 in the HTML is immediately followed by an
    IMAGE_PLACEHOLDER comment.

    For each H2 that doesn't already have one, inserts a placeholder with the
    next available sequential number and appends a generic image prompt derived
    from the H2 title text.
    """
    h2_pattern = re.compile(r"(<h2[^>]*>)(.*?)(</h2>)", re.DOTALL | re.IGNORECASE)
    after_h2_placeholder = re.compile(
        r"^\s*<!--\s*IMAGE_PLACEHOLDER_\d+\s*-->", re.IGNORECASE
    )
    existing_num = re.compile(
        r"<!--\s*IMAGE_PLACEHOLDER_(\d+)\s*-->", re.IGNORECASE
    )

    existing_numbers = [int(m.group(1)) for m in existing_num.finditer(html)]
    next_num = (max(existing_numbers) + 1) if existing_numbers else 1

    parts: list[str] = []
    cursor = 0
    new_prompts = list(image_prompts)
    new_styles = list(image_styles) if image_styles else []
    # Make sure styles array is at least as long as prompts before we start
    # appending; backfill any missing slots with the default "figure".
    while len(new_styles) < len(new_prompts):
        new_styles.append("figure" if len(new_styles) > 0 else "hero")
    inserted = 0

    for m in h2_pattern.finditer(html):
        h2_end = m.end()
        h2_inner = m.group(2)
        h2_text = re.sub(r"<[^>]+>", "", h2_inner).strip()

        parts.append(html[cursor:h2_end])
        cursor = h2_end

        rest_after_h2 = html[h2_end:]
        if after_h2_placeholder.match(rest_after_h2):
            continue

        parts.append(f"\n<!-- IMAGE_PLACEHOLDER_{next_num} -->\n")
        new_prompts.append(
            f"Simple atmospheric spot illustration for the article section "
            f'titled: "{h2_text}". The recurring character in a single calm '
            f"pose that fits the section's mood (relaxed, thinking, smiling). "
            f"No labels, no speech bubbles, no UI elements — minimal text."
        )
        new_styles.append("accent")
        next_num += 1
        inserted += 1

    parts.append(html[cursor:])

    if inserted:
        # Log to stdout so it shows up in Streamlit Cloud logs when debugging.
        print(
            f"[rewriter] Auto-inserted {inserted} IMAGE_PLACEHOLDER(s) for H2s "
            f"that Claude missed."
        )

    return "".join(parts), new_prompts, new_styles


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

【🔴 画像配置 — これを守らないと記事が画像不足で失敗します】
- **HTML本文の一番最初に必ず <!-- IMAGE_PLACEHOLDER_1 --> を配置**（アイキャッチ）
- **すべてのH2見出しの直後にも <!-- IMAGE_PLACEHOLDER_N --> を配置** — 1つも飛ばさない、最後のH2まで全部
- **長いH2セクション(H3が3つ以上、または400文字超、またはステップ5個以上、または図解した方が分かりやすい概念)には、本文中盤にも追加で <!-- IMAGE_PLACEHOLDER_N --> を1〜2個入れる**
- **placeholder番号は登場順に連番**(1, 2, 3, ...)
- **metadataには使ったplaceholder番号全部に対応する image_prompt_N を書く**
- HTMLを書き終わったら、<h2>タグの数を数えて、その数+1以上のplaceholderがあるか必ず確認。後半のH2を忘れがちなので注意。

出力は必ず ---METADATA--- と ---HTML--- のセパレータで区切ってください。"""


def _build_chunk_user_prompt(
    article: ScrapedArticle,
    chunk_text: str,
    idx: int,
    total: int,
    is_lead: bool,
    is_last: bool,
) -> str:
    position = (
        "記事の冒頭パート" if is_lead
        else ("記事の最終パート" if is_last else "記事の中間パート")
    )
    lead_note = (
        "- このパートは記事の冒頭です。導入の挨拶 + アイキャッチ( <!-- IMAGE_PLACEHOLDER_1 --> )"
        "から始めてください。\n"
        "- ---METADATA--- に title / slug / meta_description も書いてください。"
        if is_lead
        else "- このパートは記事の途中です。挨拶やアイキャッチは書かず、本文(H2)から始めてください。\n"
        "- ---METADATA--- には title / slug / meta_description は書かないでください(image_prompt_N と image_style_N のみ)。"
    )
    last_note = (
        "- このパートは記事の最後です。自然なまとめ・結びで締めてください。"
        if is_last
        else "- このパートはまだ記事の途中なので、まとめ・結論は書かず、淡々と本文を続けてください。"
    )

    return f"""以下は長い記事を分割した {total} パート中の {idx + 1} パート目({position})です。
このパートに含まれる元記事の内容を、漏れなく完全にリライトしてください。

## 元記事のタイトル(参考)
{article.title}

## このパートの元記事本文
{chunk_text}

## リライトの指示
- このパートに含まれる元記事の内容を、すべて漏れなくリライトしてください。情報を省略・要約しないでください。
- 元記事と同等以上のボリュームを維持してください。
- 購入誘導リンクは削除しつつ、そこで語られていたノウハウ自体は自分の言葉で詳しく解説し直してください。
{lead_note}
{last_note}

【画像配置】
- すべてのH2見出しの直後に <!-- IMAGE_PLACEHOLDER_N --> を配置(このパート内で N は 1 から振ってOK)
- 長いH2には中盤にも追加画像
- metadata に image_prompt_N と image_style_N(figure/accent/operation)を対応させて書く

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


def _parse_response(text: str, force_first_hero: bool = True) -> RewrittenArticle:
    """Parse the separated metadata + HTML response.

    force_first_hero: when True (lead/single-shot), the first image is forced
    to style "hero". For continuation chunks it is False so the first image
    keeps its declared style instead of becoming a banner mid-article.
    """
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

    # Extract ALL image prompts (dynamic count)
    image_prompts = []
    image_styles = []
    for i in range(1, 80):  # Support up to 79 images per call
        prompt = extract_field(metadata_block, f"image_prompt_{i}")
        if prompt:
            image_prompts.append(prompt)
            raw_style = extract_field(metadata_block, f"image_style_{i}").lower().strip()
            if i == 1 and force_first_hero:
                image_styles.append("hero")
            elif raw_style == "operation":
                image_styles.append("operation")
            elif raw_style == "accent":
                image_styles.append("accent")
            elif raw_style == "figure":
                image_styles.append("figure")
            elif raw_style == "hero":
                image_styles.append("hero")
            else:
                # default: prefer the lighter style — keeps text-only sections
                # from getting overloaded with dense explainer diagrams when
                # Claude forgets to specify
                image_styles.append("accent")
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
        image_styles=image_styles,
        slug=slug,
    )
