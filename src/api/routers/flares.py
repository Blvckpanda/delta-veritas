"""
Gas flare API routes — GeoJSON, filtering, and aggregation.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.flare import GasFlare
from ..schemas.common import GeoJSONFeatureCollection
from ..schemas.flare import FlareFilters

router = APIRouter(prefix="/flares", tags=["flares"])


def _build_filter_clauses(filters: FlareFilters):
    clauses = []
    if filters.year:
        clauses.append(GasFlare.year == filters.year)
    if filters.year_from:
        clauses.append(GasFlare.year >= filters.year_from)
    if filters.year_to:
        clauses.append(GasFlare.year <= filters.year_to)
    if filters.min_temp:
        clauses.append(GasFlare.avg_temperature_k >= filters.min_temp)
    if filters.bbox:
        try:
            parts = [float(x) for x in filters.bbox.split(",")]
            if len(parts) == 4:
                min_lon, min_lat, max_lon, max_lat = parts
                clauses.append(GasFlare.longitude >= min_lon)
                clauses.append(GasFlare.longitude <= max_lon)
                clauses.append(GasFlare.latitude >= min_lat)
                clauses.append(GasFlare.latitude <= max_lat)
        except (ValueError, TypeError):
            pass
    return clauses


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
async def get_flares_geojson(
    year: int | None = Query(None),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
    min_temp_k: float | None = Query(None),
    bbox: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Get gas flare records as GeoJSON FeatureCollection."""
    filters = FlareFilters(
        year=year, year_from=year_from, year_to=year_to,
        min_temp=min_temp_k, bbox=bbox, limit=limit, offset=offset,
    )

    count_q = select(func.count(GasFlare.id)).where(*_build_filter_clauses(filters))
    total = (await session.execute(count_q)).scalar() or 0

    q = (
        select(GasFlare)
        .where(*_build_filter_clauses(filters))
        .offset(offset)
        .limit(limit)
        .order_by(GasFlare.year.desc().nullslast(), GasFlare.month.desc().nullslast())
    )
    result = await session.execute(q)
    records = result.scalars().all()

    return GeoJSONFeatureCollection(
        features=[r.to_geojson() for r in records],
        metadata={"count": len(records), "total": total, "offset": offset, "limit": limit},
    )


@router.get("/summary")
async def get_flare_summary(session: AsyncSession = Depends(get_session)):
    """Get yearly summary of flare activity."""
    q = (
        select(
            GasFlare.year,
            func.count(GasFlare.id).label("detections"),
            func.coalesce(func.avg(GasFlare.avg_temperature_k), 0).label("avg_temp_k"),
            func.coalesce(func.avg(GasFlare.estimated_volume_m3), 0).label("avg_volume_m3"),
        )
        .where(GasFlare.year.isnot(None))
        .group_by(GasFlare.year)
        .order_by(GasFlare.year.desc())
        .limit(20)
    )
    result = await session.execute(q)
    rows = [
        {
            "year": row.year,
            "detections": row.detections,
            "avg_temperature_k": round(float(row.avg_temp_k), 1),
            "avg_volume_m3": round(float(row.avg_volume_m3), 2),
        }
        for row in result
    ]
    return {"by_year": rows}
