"""Crawl a documentation site once and freeze the cleaned pages.

Every chunker in every experiment reads this snapshot, so they all see the same
input and a rerun next month gives the same numbers even if the site changes.
The crawl date and the site's generator (from its <meta name="generator">) are
recorded for the paper.

    python -m research.snapshot --site fastapi
    python -m research.snapshot --site plausible --max-pages 150

Polite by design: honours robots.txt, one request at a time, a delay between
requests, and a page cap.

Idempotent by default: if data/research/<site>/pages.json already exists, the
site is not re-crawled — this file is meant to be portable (copy the whole
data/research/ folder to another machine and it just works), and a silent
re-crawl would both hit the target site again needlessly and overwrite a
snapshot you may have already reviewed questions against. Pass --force to
redo it deliberately.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.ingest.crawler import SKIP_EXTENSIONS, SKIP_HINTS, STRIP_TAGS
from research.common import Page, save_pages, site_config, site_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("snapshot")

USER_AGENT = "KnowledgePulse-Research/0.1 (academic study of documentation chunking)"


def _robots(entry: str, client: httpx.Client) -> RobotFileParser:
    parsed = urlparse(entry)
    rp = RobotFileParser()
    try:
        res = client.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        rp.parse(res.text.splitlines() if res.status_code == 200 else [])
    except httpx.HTTPError:
        rp.parse([])
    return rp


def _follow(url: str, cfg: dict, exclude: re.Pattern | None) -> bool:
    lowered = url.lower()
    if not lowered.startswith(cfg["include_prefix"].lower()):
        return False
    if any(lowered.split("?")[0].endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    if any(hint in lowered for hint in SKIP_HINTS):
        return False
    if exclude and exclude.search(url):
        return False
    return True


def _clean(html: str, cfg: dict) -> tuple[str, str, str | None]:
    """Return (title, cleaned main HTML, generator)."""
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": "generator"})
    generator = meta.get("content") if meta else None

    main = soup.select_one(cfg["content_selector"]) if cfg.get("content_selector") else None
    if main is None:
        main = soup.find("main") or soup.find("article") or soup.body or soup
    for tag in main.find_all(STRIP_TAGS):
        tag.decompose()
    for selector in cfg.get("strip_selectors", []):
        for tag in main.select(selector):
            tag.decompose()
    return title, str(main), generator


def normalise(url: str) -> str:
    url = urldefrag(url)[0]
    # Treat /page and /page/ as the same page.
    return url[:-1] if url.endswith("/") and urlparse(url).path not in ("", "/") else url


def crawl_site(site: str, max_pages: int | None, delay: float, force: bool = False) -> None:
    out_dir = site_dir(site)
    existing_meta = out_dir / "meta.json"
    if existing_meta.exists() and not force:
        prior = json.loads(existing_meta.read_text())
        log.info(
            "Snapshot already exists for %s: %d pages, crawled %s. Skipping — pass --force to redo it.",
            site, prior.get("page_count", "?"), prior.get("crawled_at", "unknown date"),
        )
        return

    cfg = site_config(site)
    limit = max_pages or cfg.get("max_pages", 250)
    exclude = re.compile(cfg["exclude_regex"]) if cfg.get("exclude_regex") else None

    pages: list[Page] = []
    generators: dict[str, int] = {}
    seen: set[str] = set()
    queue = [normalise(cfg["entry"])]
    skipped_robots = 0
    empty = 0

    with httpx.Client(follow_redirects=True, timeout=20, headers={"User-Agent": USER_AGENT}) as client:
        robots = _robots(cfg["entry"], client)
        while queue and len(pages) < limit:
            url = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if not robots.can_fetch(USER_AGENT, url):
                skipped_robots += 1
                continue
            try:
                res = client.get(url)
            except httpx.HTTPError as exc:
                log.warning("Skipped %s: %s", url, exc)
                continue
            if res.status_code != 200 or "text/html" not in res.headers.get("content-type", ""):
                continue

            # Keep the real, un-stripped URL as the base for resolving links on this
            # page. normalise() strips a trailing slash for de-duplication purposes
            # (so /page and /page/ count as one page), but urljoin() treats a base
            # without a trailing slash as a *file*, not a *directory* — resolving a
            # relative link like "tutorial/index.html" against the stripped
            # ".../3" would silently produce ".../tutorial/index.html", dropping the
            # "/3" segment entirely. Only sites whose theme emits relative hrefs
            # (Sphinx, mdBook) are affected; sites with absolute-path hrefs
            # (Docusaurus, VitePress) are not.
            final_raw = str(res.url)
            final = normalise(final_raw)
            if final != url and final in seen:
                continue  # a redirect to a page we already have
            seen.add(final)

            title, main_html, generator = _clean(res.text, cfg)
            if generator:
                generators[generator] = generators.get(generator, 0) + 1
            page = Page(url=final, title=title, html=main_html)
            if sum(len(b.text.split()) for b in page.blocks()) < 30:
                empty += 1  # index pages and redirects stubs; links are still followed
            else:
                pages.append(page)
                if len(pages) % 25 == 0:
                    log.info("%s: %d pages", site, len(pages))

            for anchor in BeautifulSoup(res.text, "lxml").find_all("a", href=True):
                link = normalise(urljoin(final_raw, anchor["href"]))
                if link not in seen and _follow(link, cfg, exclude):
                    queue.append(link)
            time.sleep(delay)

    path = save_pages(site, pages)
    meta = {
        "site": site,
        "name": cfg["name"],
        "entry": cfg["entry"],
        "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_count": len(pages),
        "page_limit": limit,
        "hit_limit": len(pages) >= limit,
        "skipped_by_robots": skipped_robots,
        "near_empty_pages_dropped": empty,
        "generator": max(generators, key=generators.get) if generators else "unknown",
        "total_words": sum(len(b.text.split()) for p in pages for b in p.blocks()),
        "config": cfg,
    }
    existing_meta.write_text(json.dumps(meta, indent=2))
    log.info("Saved %d pages to %s (generator: %s, %d words)", len(pages), path, meta["generator"], meta["total_words"])
    if len(pages) < 20:
        log.warning(
            "Very few pages. Check content_selector and include_prefix for %s in research/sites.json.", site
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", required=True)
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between requests")
    parser.add_argument("--force", action="store_true", help="Re-crawl even if a snapshot already exists")
    args = parser.parse_args()
    crawl_site(args.site, args.max_pages, args.delay, args.force)


if __name__ == "__main__":
    main()