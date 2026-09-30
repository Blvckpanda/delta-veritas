"""
Pydantic schemas for flare-related API requests and responses.
"""


from pydantic import BaseModel, Field


class FlareFilters(BaseModel):
    """Query parameters for filtering gas flare records."""
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    min_temp: float | None = Field(None, alias="min_temp_k")
    bbox: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class FlareResponse(BaseModel):
    """A single gas flare record response."""
    id: str
    year: int | None = None
    month: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    flare_count: int | None = None
    avg_temperature_k: float | None = None
    estimated_volume_m3: float | None = None
    confidence: str | None = None
    source: str | None = None
