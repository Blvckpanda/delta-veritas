"""
API configuration — loaded from environment with sensible defaults.
"""
from pathlib import Path

# Database
# For local dev: SQLite (aiosqlite). For production: set DATABASE_URL to PostGIS.
# Examples:
#   SQLite:  sqlite+aiosqlite:///./data/observatory.db
#   PostGIS: postgresql+asyncpg://user:pass@host:5432/observatory
DATABASE_URL = (
    "sqlite+aiosqlite:///"
    f"{Path(__file__).resolve().parent.parent.parent / 'data' / 'observatory.db'}"
)

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
