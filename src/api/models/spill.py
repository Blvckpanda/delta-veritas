"""
SpillIncident model — maps to NOSDRA oil spill records.
"""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class SpillIncident(Base):
    __tablename__ = "spill_incidents"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: str(uuid4()))
    incident_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    date: Mapped[date | None] = mapped_column(DateTime(True), nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lga: Mapped[str | None] = mapped_column(String(100), nullable=True)
    community: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cause: Mapped[str | None] = mapped_column(String(300), nullable=True)
    spill_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity_spilled: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_recovered: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jiv_date: Mapped[date | None] = mapped_column(DateTime(True), nullable=True)
    contaminant: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self):
        return f"<SpillIncident {self.incident_id}>"

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
                "incident_id": self.incident_id,
                "date": str(self.date.date()) if self.date else None,
                "year": self.year,
                "month": self.month,
                "state": self.state,
                "lga": self.lga,
                "community": self.community,
                "company": self.company,
                "cause": self.cause,
                "spill_type": self.spill_type,
                "quantity_spilled": self.quantity_spilled,
                "quantity_recovered": self.quantity_recovered,
                "recovery_pct": self.recovery_pct,
                "impact_area": self.impact_area,
                "jiv_date": str(self.jiv_date.date()) if self.jiv_date else None,
                "contaminant": self.contaminant,
                "status": self.status,
                "data_source": self.data_source,
            },
        }
        return feature
