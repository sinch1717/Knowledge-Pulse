"""Every tunable value in the system, read from the environment once.

Nothing else in the codebase reads os.environ. If you want to change how the
crawler behaves or how insights are weighted, this is the only file to open.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Storage ---------------------------------------------------------
    # SQLite by default so the project runs with nothing installed. Point this
    # at Postgres for deployment: postgresql+psycopg://user:pass@host/db
    database_url: str = "sqlite:///./data/knowledgepulse.db"
    chroma_path: str = "./data/chroma"
    upload_path: str = "./data/uploads"

    # --- Language model --------------------------------------------------
    # "groq" for development, "gemini" for the demo. One interface, two adapters.
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    llm_timeout_seconds: int = 60

    # --- Embeddings ------------------------------------------------------
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Crawling and chunking -------------------------------------------
    crawl_max_pages: int = 120
    crawl_max_depth: int = 3
    crawl_delay_seconds: float = 0.4
    crawl_timeout_seconds: int = 20
    chunk_target_words: int = 220
    chunk_overlap_words: int = 40

    # --- Retrieval -------------------------------------------------------
    retrieval_top_k: int = 5
    # Confidence blends the single best match with the spread of the rest, so a
    # lucky one-off hit surrounded by noise does not read as high confidence.
    confidence_top_weight: float = 0.6
    low_confidence_threshold: float = 0.40

    # --- Analytics -------------------------------------------------------
    umap_neighbours: int = 12
    umap_components: int = 5
    hdbscan_min_cluster_size: int = 6
    # Two clusters in consecutive periods are the same topic above this centroid
    # cosine similarity. Tuned by hand; see docs/ARCHITECTURE.md.
    topic_match_threshold: float = 0.72
    emerging_growth_threshold: float = 0.60
    emerging_max_previous: int = 25

    # Priority weights: volume, growth, confidence deficit, severity.
    w_volume: float = 0.30
    w_growth: float = 0.30
    w_confidence: float = 0.25
    w_severity: float = 0.15

    # --- API -------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
