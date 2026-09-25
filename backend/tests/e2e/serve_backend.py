"""The API with the test fakes and throwaway storage, for the browser test.

    python tests/e2e/serve_backend.py <port> <frontend origin>
"""

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "tests" / "suites"))
os.chdir(BACKEND)
os.environ["ANONYMIZED_TELEMETRY"] = "False"

port, origin = int(sys.argv[1]), sys.argv[2]
tmp = tempfile.mkdtemp(prefix="kp_e2e_")

import app.config as config  # noqa: E402

config.settings = config.Settings(
    _env_file=None,
    database_url=f"sqlite:///{tmp}/e2e.db",
    chroma_path=f"{tmp}/chroma",
    upload_path=f"{tmp}/uploads",
    crawl_delay_seconds=0,
    llm_provider="groq",
    groq_api_key="not-used",
    demo_user_email="demo@e2e.test",
    demo_user_password="demo-password",
    demo_user_name="Sinchana",
    cors_origins=origin,
)

from support import FakeEmbeddingModel, FakeLLM  # noqa: E402

from app import embeddings, llm  # noqa: E402

embeddings._model = FakeEmbeddingModel()
llm._groq = FakeLLM()

import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
