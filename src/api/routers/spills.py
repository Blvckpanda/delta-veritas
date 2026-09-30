"""
Spill incidents API routes — GeoJSON, filtering, and aggregation.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models.spill import SpillIncident
from ..schemas.common import GeoJSONFeatureCollection
from ..schemas.spill import SpillFilters, SpillStats

router = APIRouter(prefix="/spills", tags=["spills"])


def _build_filter_clauses(filters: SpillFilters):
    """Build WHERE clauses from filter parameters."""
    clauses = []
    if filters.year:
        clauses.append(SpillIncident.year == filters.year)
    if filters.state:
        clauses.append(SpillIncident.state == filters.state)
    if filters.company:
        clauses.append(SpillIncident.company.ilike(f"%{filters.company}%"))
    if filters.cause:
        clauses.append(SpillIncident.cause.ilike(f"%{filters.cause}%"))
    if filters.date_from:
        clauses.append(SpillIncident.date >= filters.date_from)
    if filters.date_to:
        clauses.append(SpillIncident.date <= filters.date_to)
    if filters.min_quantity:
        clauses.append(SpillIncident.quantity_spilled >= filters.min_quantity)
    if filters.bbox:
        try:
            parts = [float(x) for x in filters.bbox.split(",")]
            if len(parts) == 4:
                min_lon, min_lat, max_lon, max_lat = parts
                clauses.append(SpillIncident.longitude >= min_lon)
                clauses.append(SpillIncident.longitude <= max_lon)
                clauses.append(SpillIncident.latitude >= min_lat)
                clauses.append(SpillIncident.latitude <= max_lat)
        except (ValueError, TypeError):
            pass
    return clauses


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
async def get_spills_geojson(
    year: int | None = Query(None),
    state: str | None = Query(None),
    company: str | None = Query(None),
    cause: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    bbox: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """Get spill incidents as GeoJSON FeatureCollection."""
    filters = SpillFilters(
        year=year, state=state, company=company, cause=cause,
        date_from=date_from, date_to=date_to, bbox=bbox,
        limit=limit, offset=offset,
    )

    clauses = _build_filter_clauses(filters)
    query = (
        select(SpillIncident)
        .where(*clauses)
        .offset(filters.offset)
        .limit(filters.limit)
        .order_by(SpillIncident.date.desc().nullslast())
    )

    result = await session.execute(query)
    records = result.scalars().all()

    features = [r.to_geojson() for r in records]

    return GeoJSONFeatureCollection(
        features=features,
        metadata={"count": len(features), "offset": offset, "limit": limit},
    )


@router.get("/stats", response_model=SpillStats)
async def get_spill_stats(session: AsyncSession = Depends(get_session)):
    """Get aggregated spill statistics."""
    # Total counts
    count_q = select(func.count(SpillIncident.id))
    total = (await session.execute(count_q)).scalar() or 0

    # Totals
    sum_q = select(
        func.coalesce(func.sum(SpillIncident.quantity_spilled), 0),
        func.coalesce(func.sum(SpillIncident.quantity_recovered), 0),
    )
    sum_result = await session.execute(sum_q)
    total_spilled, total_recovered = sum_result.one()
    total_spilled = float(total_spilled)
    total_recovered = float(total_recovered)

    # By state
    state_q = (
        select(
            SpillIncident.state,
            func.count(SpillIncident.id).label("count"),
            func.coalesce(func.sum(SpillIncident.quantity_spilled), 0).label("spilled"),
        )
        .where(SpillIncident.state.isnot(None))
        .group_by(SpillIncident.state)
        .order_by(func.count(SpillIncident.id).desc())
        .limit(15)
    )
    state_result = await session.execute(state_q)
    by_state = [
        {"state": row.state, "count": row.count, "spilled_bbl": float(row.spilled)}
        for row in state_result
    ]

    # By year
    year_q = (
        select(
            SpillIncident.year,
            func.count(SpillIncident.id).label("count"),
            func.coalesce(func.sum(SpillIncident.quantity_spilled), 0).label("spilled"),
        )
        .where(SpillIncident.year.isnot(None))
        .group_by(SpillIncident.year)
        .order_by(SpillIncident.year.desc())
        .limit(15)
    )
    year_result = await session.execute(year_q)
    by_year = [
        {"year": row.year, "count": row.count, "spilled_bbl": float(row.spilled)}
        for row in year_result
    ]

    # Top causes
    cause_q = (
        select(
            SpillIncident.cause,
            func.count(SpillIncident.id).label("count"),
        )
        .where(SpillIncident.cause.isnot(None))
        .group_by(SpillIncident.cause)
        .order_by(func.count(SpillIncident.id).desc())
        .limit(10)
    )
    cause_result = await session.execute(cause_q)
    top_causes = [
        {"cause": row.cause, "count": row.count}
        for row in cause_result
    ]

    # Top companies
    company_q = (
        select(
            SpillIncident.company,
            func.count(SpillIncident.id).label("count"),
        )
        .where(SpillIncident.company.isnot(None))
        .group_by(SpillIncident.company)
        .order_by(func.count(SpillIncident.id).desc())
        .limit(10)
    )
    company_result = await session.execute(company_q)
    top_companies = [
        {"company": row.company, "count": row.count}
        for row in company_result
    ]

    return SpillStats(
        total_incidents=total,
        total_spilled_bbl=total_spilled,
        total_recovered_bbl=total_recovered,
        overall_recovery_pct=round((total_recovered / total_spilled * 100), 1)
        if total_spilled > 0 else 0.0,
        by_state=by_state,
        by_year=by_year,
        top_causes=top_causes,
        top_companies=top_companies,
    )


@router.get("/distinct/{field}", response_model=list[str])
async def get_distinct_values(
    field: str,
    session: AsyncSession = Depends(get_session),
):
    """Get distinct values for a given field (state, company, cause, etc.)."""
    allowed = {"state", "company", "cause", "spill_type", "contaminant", "impact_area", "lga"}
    if field not in allowed:
        return []

    column = getattr(SpillIncident, field, None)
    if column is None:
        return []

    q = select(column).distinct().where(column.isnot(None)).order_by(column)
    result = await session.execute(q)
    return [row[0] for row in result if row[0]]
