"""
GasFlare model — maps to VIIRS Nightfire gas flaring records.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class GasFlare(Base):
    __tablename__ = "gas_flares"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    year: Mapped[int | None] = mapped_column(Integer)
    month: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    flare_count: Mapped[int | None] = mapped_column(Integer)
    avg_temperature_k: Mapped[float | None] = mapped_column(Float)
    estimated_volume_m3: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(50))  # VIIRS-Nightfire, etc.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(True), default=datetime.utcnow
    )

    def __repr__(self):
        return f"<GasFlare {self.lat:.2f},{self.lon:.2f} ({self.year})>"

    def to_geojson(self) -> dict:
        """Serialize to GeoJSON Feature."""
        feature = {
            "type": "Feature",
            "geometry": (
                {
                    "type": "Point",
                    "coordinates": [self.longitude, self.latitude],
                }
                if self.latitude is not None and self.longitude is not None
                else None
            ),
            "properties": {
                "id": self.id,
                "year": self.year,
                "month": self.month,
                "flare_count": self.flare_count,
                "avg_temperature_k": self.avg_temperature_k,
                "estimated_volume_m3": self.estimated_volume_m3,
                "confidence": self.confidence,
                "source": self.source,
            },
        }
        return feature
