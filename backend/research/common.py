"""Paths, site config and the page model shared by every research step."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from bs4 import BeautifulSoup

from app.ingest.chunker import Block, iter_blocks

ROOT = Path("data/research")
SITES_FILE = Path(__file__).with_name("sites.json")


def load_sites() -> dict[str, dict]:
    return json.loads(SITES_FILE.read_text())


def site_config(site: str) -> dict:
    sites = load_sites()
    if site not in sites:
        raise SystemExit(f"Unknown site '{site}'. Known: {', '.join(sites)}. Add it to research/sites.json.")
    return sites[site]


def site_dir(site: str) -> Path:
    path = ROOT / site
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Page:
    url: str
    title: str
    html: str  # the cleaned main-content HTML, frozen at snapshot time

    def blocks(self) -> list[Block]:
        return iter_blocks(BeautifulSoup(self.html, "lxml"))


def load_pages(site: str) -> list[Page]:
    path = site_dir(site) / "pages.json"
    if not path.exists():
        raise SystemExit(f"No snapshot for {site}. Run: python -m research.snapshot --site {site}")
    return [Page(**p) for p in json.loads(path.read_text())]


def save_pages(site: str, pages: list[Page]) -> Path:
    path = site_dir(site) / "pages.json"
    path.write_text(json.dumps([asdict(p) for p in pages], indent=1))
    return path


def words(text: str) -> list[str]:
    return text.split()
