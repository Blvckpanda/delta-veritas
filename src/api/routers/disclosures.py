"""
Disclosure API routes — GeoJSON for NEITI/NDDC investment data.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.disclosure import Disclosure
from ..schemas.common import GeoJSONFeatureCollection

router = APIRouter(prefix="/disclosures", tags=["disclosures"])


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
async def get_disclosures_geojson(
    source: str | None = Query(None),
    year: int | None = Query(None),
    state: str | None = Query(None),
    disclosure_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Get disclosure records as GeoJSON FeatureCollection."""
    clauses = []
    if source:
        clauses.append(Disclosure.source == source)
    if year:
        clauses.append(Disclosure.year == year)
    if state:
        clauses.append(Disclosure.state == state)
    if disclosure_type:
        clauses.append(Disclosure.disclosure_type == disclosure_type)

    q = (
        select(Disclosure)
        .where(*clauses)
        .offset(offset)
        .limit(limit)
        .order_by(Disclosure.year.desc().nullslast())
    )
    result = await session.execute(q)
    records = result.scalars().all()

    return GeoJSONFeatureCollection(
        features=[r.to_geojson() for r in records],
        metadata={"count": len(records), "offset": offset, "limit": limit},
    )


@router.get("/sources")
async def get_disclosure_sources(session: AsyncSession = Depends(get_session)):
    """Get list of disclosure sources with record counts."""
    q = (
        select(
            Disclosure.source,
            func.count(Disclosure.id).label("count"),
            func.min(Disclosure.year).label("year_min"),
            func.max(Disclosure.year).label("year_max"),
        )
        .where(Disclosure.source.isnot(None))
        .group_by(Disclosure.source)
        .order_by(func.count(Disclosure.id).desc())
    )
    result = await session.execute(q)
    return [
        {
            "source": row.source,
            "record_count": row.count,
            "year_range": f"{row.year_min}–{row.year_max}" if row.year_min else None,
        }
        for row in result
    ]
