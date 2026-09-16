import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["CBI_DB_PATH"] = str(Path(_tmp) / "test.db")
os.environ["LLM_MODE"] = "offline"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.ingest import pipeline  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def store():
    pipeline.run(regenerate=True, verbose=False)
    yield
