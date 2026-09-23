"""The chunking strategies under comparison, behind one interface.

    chunk(page, size, overlap) -> list[ResearchChunk]

All four read the same frozen blocks of the same page, so the only thing that
differs between runs is where the boundaries fall.

  fixed        Word windows of `size` with `overlap`, ignoring structure. The
               baseline most RAG tutorials use.
  recursive    Pack whole paragraphs up to `size`; split an oversized paragraph
               on sentences, and an oversized sentence on words. Respects
               paragraph boundaries but not headings. No overlap, matching the
               usual recursive splitter with overlap disabled.
  heading      The app's own chunker: cut at headings first, window only
               sections longer than `size`. Heading path kept as metadata.
  heading_ctx  Same boundaries as `heading`, but the heading path is prepended
               to the text that gets embedded. Isolates the effect of the
               heading context from the effect of the boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingest import chunker as app_chunker
from research.common import Page

MIN_WORDS = 15  # same floor the app uses; shorter fragments are noise in an index


@dataclass
class ResearchChunk:
    url: str
    heading_path: str
    text: str  # what a reader sees and what relevance is judged on
    embed_text: str  # what gets embedded

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def _mk(page: Page, heading: str, text: str, embed: str | None = None) -> ResearchChunk:
    return ResearchChunk(url=page.url, heading_path=heading, text=text, embed_text=embed or text)


def _content_blocks(page: Page) -> list[str]:
    # Headings are content too for structure-blind chunkers: they appear inline.
    return [b.text for b in page.blocks()]


def fixed(page: Page, size: int, overlap: int) -> list[ResearchChunk]:
    tokens = " ".join(_content_blocks(page)).split()
    step = max(1, size - overlap)
    out = []
    for start in range(0, len(tokens), step):
        window = tokens[start : start + size]
        if len(window) >= MIN_WORDS:
            out.append(_mk(page, page.title, " ".join(window)))
        if start + size >= len(tokens):
            break
    return out


_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`\"'(])")


def _pieces(text: str, size: int) -> list[str]:
    """Break one paragraph into parts no longer than `size` words."""
    if len(text.split()) <= size:
        return [text]
    parts: list[str] = []
    current: list[str] = []
    for sentence in _SENTENCE.split(text):
        sw = sentence.split()
        if len(sw) > size:  # a single enormous sentence, e.g. a code block
            if current:
                parts.append(" ".join(current))
                current = []
            parts.extend(" ".join(sw[i : i + size]) for i in range(0, len(sw), size))
            continue
        if len(current) + len(sw) > size and current:
            parts.append(" ".join(current))
            current = []
        current.extend(sw)
    if current:
        parts.append(" ".join(current))
    return parts


def recursive(page: Page, size: int, overlap: int) -> list[ResearchChunk]:  # noqa: ARG001
    out: list[ResearchChunk] = []
    current: list[str] = []
    for block in _content_blocks(page):
        for piece in _pieces(block, size):
            pw = piece.split()
            if current and len(current) + len(pw) > size:
                if len(current) >= MIN_WORDS:
                    out.append(_mk(page, page.title, " ".join(current)))
                current = []
            current.extend(pw)
    if len(current) >= MIN_WORDS:
        out.append(_mk(page, page.title, " ".join(current)))
    return out


def _heading_chunks(page: Page, size: int, overlap: int) -> list[app_chunker.RawChunk]:
    from bs4 import BeautifulSoup

    sections = app_chunker.sections_from_html(BeautifulSoup(page.html, "lxml"))
    return app_chunker.chunk_sections(sections, url=page.url, target=size, overlap=overlap)


def heading(page: Page, size: int, overlap: int) -> list[ResearchChunk]:
    return [_mk(page, c.heading_path, c.text) for c in _heading_chunks(page, size, overlap)]


def heading_ctx(page: Page, size: int, overlap: int) -> list[ResearchChunk]:
    return [
        _mk(page, c.heading_path, c.text, embed=f"{c.heading_path}\n{c.text}")
        for c in _heading_chunks(page, size, overlap)
    ]


CHUNKERS = {
    "fixed": fixed,
    "recursive": recursive,
    "heading": heading,
    "heading_ctx": heading_ctx,
}


def chunk_site(pages: list[Page], name: str, size: int, overlap: int) -> list[ResearchChunk]:
    fn = CHUNKERS[name]
    out: list[ResearchChunk] = []
    for page in pages:
        out.extend(fn(page, size, overlap))
    return out
