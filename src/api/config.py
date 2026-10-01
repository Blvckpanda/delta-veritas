"""
API configuration — loaded from environment with sensible defaults.
"""
import os
from pathlib import Path

# Database
# For local dev: SQLite (aiosqlite). For production: set DATABASE_URL to PostGIS.
# Override for tests or alternate environments with the OBSERVATORY_DATABASE_URL
# environment variable (e.g. a per-test-run temp SQLite file).
# Examples:
#   SQLite:  sqlite+aiosqlite:///./data/observatory.db
#   PostGIS: postgresql+asyncpg://user:pass@host:5432/observatory
#
# NOTE (async SQLite tests): aiosqlite connections bind to the event loop that
# created them. FastAPI's TestClient runs the app in a different loop than the
# test that seeds the database, so pooled connections raised across loops fail
# with "attached to a different loop". Tests must create the engine with
# poolclass=NullPool (no pooled connections) and point OBSERVATORY_DATABASE_URL
# at a dedicated temp file — never the shared data/observatory.db.
DATABASE_URL = os.environ.get("OBSERVATORY_DATABASE_URL") or (
    "sqlite+aiosqlite:///"
    f"{Path(__file__).resolve().parent.parent.parent / 'data' / 'observatory.db'}"
)

# Static site (MapLibre prototype lives in docs/)
DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "docs"

# API
API_HOST = "0.0.0.0"
API_PORT = 8766
API_PREFIX = "/api/v1"
DEBUG = True

# CORS — allow the frontend dev server
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8765",
    "https://niger-delta-observatory.vercel.app",
]

# Pagination
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500

# Data versioning
CURRENT_DATA_VERSION = "0.1.0"
