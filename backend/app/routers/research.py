"""Serves the latest chunking experiment to the website's Research page.

Read-only, and not workspace-scoped: the experiment compares sites side by side.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/research", tags=["research"])

LATEST = Path("data/research/results/latest.json")


@router.get("/latest")
def latest():
    if not LATEST.exists():
        raise HTTPException(404, "No experiment has been run yet. Run: python -m research.run --sites plausible,fastapi")
    return json.loads(LATEST.read_text())
