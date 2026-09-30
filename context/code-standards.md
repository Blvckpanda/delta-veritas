# Code Standards

## Python Conventions

- Python 3.11+. Use type hints on all function signatures.
- Every function must have a docstring (Google style).
- Max line length: 100 characters.
- Run `ruff check src/` before committing.

## Configuration Discipline

- `src/etl/config.py` is the single source of truth for:
  - Column names (as constants)
  - File paths (input, output, log)
  - Date formats
  - Thresholds (min volumes, coordinate bounds)
  - Controlled vocabularies (cause categories, contaminant types)
- No hardcoded string values in pipeline modules.
- No hardcoded file paths outside config.py.

## Module Structure (as implemented)

```
src/etl/
├── config.py           # Column names, paths, thresholds (single source of truth)
├── nosdra_pipeline.py  # NOSDRA spill GeoJSON ETL (ingest → clean → export)
├── osm_pipeline.py     # Overpass API fetch of context layers (roads, settlements, boundaries)
└── viirs_pipeline.py   # VIIRS Nightfire CSV skeleton (awaiting real EOG data)

src/api/                # FastAPI app: routers/, schemas/, models/, seed.py, database.py
src/analysis/           # map_report.py — static portfolio cartography
```

Each pipeline module owns one source and is runnable standalone via CLI.
Cross-module coordination happens through shared config and the API seed step,
not lateral imports — keep it that way until a coordinator becomes genuinely
necessary.

## CLI Output Format

```
[NOSDRA-ETL] Ingesting data/raw/nosdra_export.csv ... Done (2,847 records)
[NOSDRA-ETL] Cleaning ... flagged 342 records with missing coordinates
[NOSDRA-ETL] Cleaning ... normalized 56 cause variants to 8 categories
[NOSDRA-ETL] Analysis ... top 5 spill hotspots identified
[NOSDRA-ETL] Exporting data/processed/spills_20260730.geojson ... Done
[NOSDRA-ETL] Done. Pipeline completed in 4.2s — 2,505 records passed QC
```

## Date Parsing Strategy

- NOSDRA dates arrive in DD/MM/YYYY, MM/DD/YYYY, or "unknown" — plus Excel serial numbers and null sentinels
- Try multiple formats in order (config.KNOWN_DATE_FORMATS, most specific first), log failures
- Records with unparseable dates: flag, log, keep in output with null date (excluded from time-series analysis downstream)

## Coordinate Validation

- Nigeria bounds: lat 4.0–14.0, lng 2.5–15.0
- Records outside bounds: flag and exclude (log reason)
- Records with null/zero coordinates: flag and exclude (log reason)
- Records at exactly (0,0): likely placeholder, exclude

## Efficiency Calculations

- Spill frequency: incidents per year per LGA
- Flaring trend: annual volume per state
- Environmental correlation: NDVI change within buffer zones of high-spill areas (stretch goal)
