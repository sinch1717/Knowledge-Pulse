"""Local sentence embeddings.

Lazily loaded, because importing sentence-transformers pulls in torch and takes
several seconds. The API should start instantly; the model can load on the first
request that actually needs it.

Running this locally rather than through an API is what keeps the cost of the
analytics batch at zero regardless of how many conversations accumulate (NFR10).
"""

from __future__ import annotations

import logging
import threading

import numpy as np

from app.config import settings

log = logging.getLogger(__name__)

_model = None
_lock = threading.Lock()


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                log.info("Loading embedding model %s", settings.embedding_model)
                _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Return L2-normalised embeddings, so a dot product is a cosine similarity."""
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    vectors = get_model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 200,
        convert_to_numpy=True,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_one(text: str) -> np.ndarray:
    return embed([text])[0]
