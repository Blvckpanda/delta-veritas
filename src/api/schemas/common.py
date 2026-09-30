"""
Common Pydantic schemas — GeoJSON response wrappers, pagination, health.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


# ── GeoJSON response ──────────────────────────────────────────────────────
class GeoJSONFeature(BaseModel):
    """A single GeoJSON Feature."""
    type: str = "Feature"
    geometry: dict | None = None
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection response."""
    type: str = "FeatureCollection"
    features: list[GeoJSONFeature]
    metadata: dict[str, Any] | None = None


# ── Pagination ────────────────────────────────────────────────────────────
class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Health ────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    timestamp: datetime
    db_connected: bool
