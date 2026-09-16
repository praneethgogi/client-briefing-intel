"""Central settings. Everything is overridable via environment variables or a local .env file."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

DATA_DIR = Path(os.getenv("CBI_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DOCS_DIR = RAW_DIR / "docs"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = Path(os.getenv("CBI_DB_PATH", DATA_DIR / "briefing.db"))
EVALS_DIR = ROOT / "evals"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

# LLM_MODE: "openai" | "offline" | "auto" (openai when a key is present)
_mode = os.getenv("LLM_MODE", "auto").lower()
LLM_MODE = ("openai" if OPENAI_API_KEY else "offline") if _mode == "auto" else _mode

# The demo world is frozen at a fixed "today" so results are reproducible.
AS_OF_DATE = date.fromisoformat(os.getenv("AS_OF_DATE", "2026-09-17"))

# Policy knobs (deterministic rules, not LLM judgement)
STALE_DAYS = int(os.getenv("STALE_DAYS", "120"))
AUM_CONFLICT_TOLERANCE = float(os.getenv("AUM_CONFLICT_TOLERANCE", "0.05"))
ER_AUTO_MATCH = int(os.getenv("ER_AUTO_MATCH", "90"))
ER_REVIEW_MATCH = int(os.getenv("ER_REVIEW_MATCH", "75"))
MAX_DRAFT_ATTEMPTS = int(os.getenv("MAX_DRAFT_ATTEMPTS", "2"))
