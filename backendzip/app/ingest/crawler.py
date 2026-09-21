"""Breadth-first crawler, bounded by domain, depth and page count.

Deliberately not a general-purpose spider. It follows links inside the domain you
gave it, ignores anything that looks like a file download or a login page, and
stops at the configured limits. If a site renders its content with JavaScript this
crawler will find an empty page and say so rather than silently indexing nothing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup

from app.config import settings

log = logging.getLogger(__name__)

SKIP_EXTENSIONS = (
    ".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".mp4",
    ".css", ".js", ".ico", ".woff", ".woff2", ".xml", ".json",
)
SKIP_HINTS = ("/login", "/signin", "/signup", "/cart", "/checkout", "/account")
STRIP_TAGS = ("nav", "header", "footer", "aside", "script", "style", "noscript", "form", "iframe")


@dataclass
class Page:
    url: str
    title: str
    html: str


def _same_site(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower().removeprefix("www.") == urlparse(b).netloc.lower().removeprefix("www.")


def _worth_following(url: str) -> bool:
    lowered = url.lower()
    if any(lowered.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if any(hint in lowered for hint in SKIP_HINTS):
        return False
    return lowered.startswith("http")


def crawl(entry_url: str) -> list[Page]:
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(urldefrag(entry_url)[0], 0)]
    pages: list[Page] = []

    headers = {"User-Agent": "KnowledgePulse/0.1 (academic project crawler)"}
    with httpx.Client(
        follow_redirects=True, timeout=settings.crawl_timeout_seconds, headers=headers
    ) as client:
        while queue and len(pages) < settings.crawl_max_pages:
            url, depth = queue.pop(0)
            if url in seen or depth > settings.crawl_max_depth:
                continue
            seen.add(url)

            try:
                response = client.get(url)
            except httpx.HTTPError as exc:
                log.warning("Skipped %s: %s", url, exc)
                continue

            if response.status_code != 200:
                continue
            if "text/html" not in response.headers.get("content-type", ""):
                continue

            soup = BeautifulSoup(response.text, "lxml")
            title = soup.title.get_text(strip=True) if soup.title else url
            pages.append(Page(url=url, title=title, html=response.text))

            if depth < settings.crawl_max_depth:
                for anchor in soup.find_all("a", href=True):
                    link = urldefrag(urljoin(url, anchor["href"]))[0]
                    if link not in seen and _same_site(entry_url, link) and _worth_following(link):
                        queue.append((link, depth + 1))

            time.sleep(settings.crawl_delay_seconds)

    log.info("Crawled %d pages from %s", len(pages), entry_url)
    return pages


def extract_main_text(html: str) -> BeautifulSoup:
    """Strip navigation and boilerplate, return the soup of what is left."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(STRIP_TAGS):
        tag.decompose()
    # Prefer a semantic main region when the page offers one.
    main = soup.find("main") or soup.find("article") or soup.find(attrs={"role": "main"})
    return main if main else (soup.body or soup)
