# Architecture

## System Boundaries

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────┐
│  NOSDRA     │    │  EOG/NOAA    │    │  Copernicus      │
│  Spill API  │    │  VIIRS VNF   │    │  STAC API        │
└──────┬──────┘    └──────┬───────┘    └───────┬──────────┘
       │                  │                    │
       ▼                  ▼                    ▼
┌──────────────────────────────────────────────────────┐
│  src/etl/  Python data pipeline                        │
│  ingest.py → clean.py → analyse.py → export.py        │
│  Entry point: pipeline.py                              │
└────────────────────┬─────────────────────────────────┘
                     │ cleaned GeoJSON / CSV
                     ▼
┌──────────────────────────────────────────────────────┐
│  data/processed/  Cleaned output files                │
│  spills_20260730.geojson                              │
│  flares_20260730.geojson                              │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  Data serving layer                                   │
│  Option A: PostGIS on Supabase (for interactive)      │
│  Option B: Static GeoJSON served via Next.js API      │
│  Decision: Start with B, graduate to A if needed      │
└────────────────────┬─────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────┐
│  frontend/  Next.js 16 + MapLibre GL                  │
│  - Map page with layer controls                       │
│  - Timeline slider                                    │
│  - Popups and filters                                 │
│  - PDF report export                                  │
└──────────────────────────────────────────────────────┘
```

## Storage Model

### NOSDRA Spills — GeoJSON Feature Schema (as actually emitted by `nosdra_pipeline.py`)
```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": { "type": "Point", "coordinates": [lng, lat] },
    "properties": {
      "incident_id": "string",
      "date": "ISO8601 or null (unparseable dates are logged, not dropped)",
      "year": "integer or null",
      "month": "integer or null",
      "state": "string",
      "lga": "string",
      "community": "string",
      "company": "string (operator)",
      "cause": "string (raw free text — normalisation is a future stage)",
      "spill_type": "string",
      "quantity_spilled": "float or null (validated against thresholds)",
      "quantity_recovered": "float or null",
      "recovery_pct": "float or null (derived)",
      "impact_area": "string",
      "jiv_date": "ISO8601 or null",
      "latitude": "float or null (null ⇒ geometry is null too)",
      "longitude": "float or null",
      "status": "string",
      "contaminant": "string",
      "data_source": "string (always 'NOSDRA')"
    }
  }]
}
```
Note: `data_source` was added so every record independently satisfies invariant #5
(every data point traces to a public source). The planned cause normalisation stage
will reduce the free-text `cause` field to a controlled vocabulary.

### VIIRS Flaring — GeoJSON Feature Schema
```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": { "type": "Point", "coordinates": [lng, lat] },
    "properties": {
      "site_id": "string",
      "year": "integer",
      "month": "integer",
      "temperature_k": "float",
      "source_area_m2": "float",
      "radiative_heat_mw": "float",
      "estimated_volume_mscf": "float",
      "company": "string or null",
      "state": "string",
      "lga": "string or null",
      "data_source": "string (always 'VIIRS_VNF')"
    }
  }]
}
```

## Invariants

1. `data/raw/` is never modified. Raw data is read-only.
2. `logs/data_quality.log` is append-only. Every cleaning decision is logged.
3. All output filenames include ISO date timestamp.
4. No infrastructure coordinates (pipeline routes, wellheads, flow stations) are stored.
5. Every data point in processed output traces to a public source.
6. No lateral imports between pipeline modules. Only `pipeline.py` coordinates stages.
