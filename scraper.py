from __future__ import annotations

import requests
import trafilatura
from bs4 import BeautifulSoup
from dataclasses import dataclass


@dataclass
class ScrapedArticle:
    url: str
    title: str
    text: str
    headings: list[str]
    author: str | None = None
    date: str | None = None


def scrape_article(url: str) -> ScrapedArticle:
    """Scrape article from URL. Uses trafilatura with BS4 fallback."""
    article = _scrape_with_trafilatura(url)
    if article and article.text:
        return article

    article = _scrape_with_beautifulsoup(url)
    if article and article.text:
        return article

    raise ValueError(f"記事の取得に失敗しました: {url}")


def _scrape_with_trafilatura(url: str) -> ScrapedArticle | None:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not text:
        return None

    metadata = trafilatura.extract_metadata(downloaded)
    headings = _extract_headings(downloaded)

    title = ""
    author = None
    date = None
    if metadata:
        title = metadata.title or ""
        author = metadata.author
        date = metadata.date

    return ScrapedArticle(
        url=url,
        title=title,
        text=text,
        headings=headings,
        author=author,
        date=date,
    )


def _scrape_with_beautifulsoup(url: str) -> ScrapedArticle | None:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; LunaWorkBot/1.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException:
        return None

    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    # Remove non-content elements
    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "aside", "header", "iframe"]
    ):
        tag.decompose()

    # Extract title
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Try to find main content: <article> > <main> > <body>
    content_el = soup.find("article") or soup.find("main") or soup.find("body")
    if not content_el:
        return None

    text = content_el.get_text(separator="\n", strip=True)
    headings = _extract_headings(str(soup))

    return ScrapedArticle(
        url=url,
        title=title,
        text=text,
        headings=headings,
    )


def create_article_from_text(
    text: str,
    title: str = "",
    url: str = "",
) -> ScrapedArticle:
    """Create a ScrapedArticle from raw text (for paid articles etc.)."""
    import re

    # Extract headings from text (lines starting with 【 or STEP or common heading patterns)
    headings = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Match patterns like 【STEP1：...】, 【...編】, numbered steps
        if re.match(r"^【.+】", line):
            headings.append(line)
        elif re.match(r"^(STEP|ステップ)\s*\d", line, re.IGNORECASE):
            headings.append(line)
        elif re.match(r"^\d+-\d+\.", line):
            headings.append(line)

    return ScrapedArticle(
        url=url,
        title=title,
        text=text,
        headings=headings,
    )


def _extract_headings(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
