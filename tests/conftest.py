"""Pytest configuration — import paths + isolated API test database."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Make both import styles available:
#   `import config` / `from nosdra_pipeline import ...`  (src/etl modules)
#   `from quality_scorecard import ...`                  (src/analysis modules)
#   `from src.api.main import app`                       (project-root packages)
for _p in (ROOT / "src" / "etl", ROOT / "src" / "analysis", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# The API test module imports src.api, whose config reads this env var at
# import time. Point it at a throwaway DB so tests never touch
# data/observatory.db. database.py uses NullPool for sqlite URLs, which makes
# connections safe across the separate event loops of asyncio.run() seeding
# and the TestClient portal.
_API_TEST_DB = Path(tempfile.gettempdir()) / f"observatory_api_test_{os.getpid()}.db"
_API_TEST_DB.unlink(missing_ok=True)
os.environ["OBSERVATORY_DATABASE_URL"] = f"sqlite+aiosqlite:///{_API_TEST_DB}"
