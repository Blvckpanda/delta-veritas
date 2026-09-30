"""
Disclosure model — maps to NEITI, NDDC, and other public disclosure records.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Disclosure(Base):
    __tablename__ = "disclosures"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str | None] = mapped_column(String(50), index=True)  # NEITI, NDDC
    year: Mapped[int | None] = mapped_column(index=True)
    facility_name: Mapped[str | None] = mapped_column(String(300))
    operator: Mapped[str | None] = mapped_column(String(200))
    disclosure_type: Mapped[str | None] = mapped_column(
        String(100)
    )  # production, revenue, project
    value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(String(100))
    lga: Mapped[str | None] = mapped_column(String(100))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(True), default=datetime.utcnow
    )

    def __repr__(self):
        return f"<Disclosure {self.source} {self.year} {self.facility_name}>"

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
                "source": self.source,
                "year": self.year,
                "facility_name": self.facility_name,
                "operator": self.operator,
                "disclosure_type": self.disclosure_type,
                "value": self.value,
                "currency": self.currency,
                "description": self.description,
                "state": self.state,
                "lga": self.lga,
                "url": self.url,
            },
        }
        return feature
