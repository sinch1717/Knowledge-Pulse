"""Stop requests for sources that are being crawled or indexed.

Ingestion runs in a background thread inside the API process, so a plain
thread-safe set is enough: the stop endpoint adds an id, and the pipeline checks
for it between pages and between embedding batches.
"""

from __future__ import annotations

import threading

_requested: set[str] = set()
_lock = threading.Lock()


class Stopped(Exception):
    """Raised inside the pipeline when a stop was requested."""


def request_stop(source_id: str) -> None:
    with _lock:
        _requested.add(source_id)


def is_requested(source_id: str) -> bool:
    with _lock:
        return source_id in _requested


def clear(source_id: str) -> None:
    with _lock:
        _requested.discard(source_id)


def check(source_id: str) -> None:
    if is_requested(source_id):
        raise Stopped()
