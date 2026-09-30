"""
Pydantic schemas for spill-related API requests and responses.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class SpillFilters(BaseModel):
    """Query parameters for filtering spill incidents."""
    year: int | None = None
    state: str | None = None
    company: str | None = None
    cause: str | None = None
    date_from: date | None = Field(None, alias="date_from")
    date_to: date | None = Field(None, alias="date_to")
    min_quantity: float | None = None
    bbox: str | None = None  # "min_lon,min_lat,max_lon,max_lat"
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SpillResponse(BaseModel):
    """A single spill incident response."""
    id: str
    incident_id: str
    date: str | None = None
    year: int | None = None
    month: int | None = None
    state: str | None = None
    lga: str | None = None
    community: str | None = None
    company: str | None = None
    cause: str | None = None
    spill_type: str | None = None
    quantity_spilled: float | None = None
    quantity_recovered: float | None = None
    recovery_pct: float | None = None
    impact_area: str | None = None
    contaminant: str | None = None
    status: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class SpillStats(BaseModel):
    """Aggregated spill statistics."""
    total_incidents: int
    total_spilled_bbl: float
    total_recovered_bbl: float
    overall_recovery_pct: float
    by_state: list[dict[str, Any]]
    by_year: list[dict[str, Any]]
    top_causes: list[dict[str, Any]]
    top_companies: list[dict[str, Any]]
