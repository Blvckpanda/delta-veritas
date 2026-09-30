# Niger Delta Environmental Risk Observatory

**Live map:** *deployed.vercel.app* (coming after Phase 3)

An interactive geospatial dashboard mapping environmental risk, oil spill history, gas flaring, and development disclosure across the Niger Delta — built entirely from public, authoritative data sources.

## What this project does

- Maps **NOSDRA oil spill incidents** (2010–2026) — location, cause, volume, company, remediation status
- Visualises **VIIRS gas flaring** intensity and trends over time
- Tracks **NDDC/NEITI development disclosures** and Host Community trust fund allocation
- Shows **land-use change** via Sentinel-2 satellite imagery

## What this project does NOT do

- ❌ Maps precise pipeline routes, wellhead coordinates, or flow-station perimeters
- ❌ Provides real-time incident monitoring or alerts
- ❌ Detects or maps illegal refinery locations
- ❌ Triangulates undisclosed facility locations from multiple sources

This ethical boundary is intentional. The project focuses on **environmental risk and compliance intelligence** — which is stronger for portfolio purposes anyway. See `context/project-overview.md` for the full scoping rationale.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Data pipeline | Python 3.11, stdlib + pandas + matplotlib (geopandas deferred to Phase 3) |
| API | FastAPI + SQLAlchemy 2 (async) over SQLite/aiosqlite — PostGIS on Supabase only if/when traffic demands it |
| Frontend | MapLibre GL prototype today; Next.js + TypeScript considered for Phase 5 |
| Testing | pytest (ETL parsers, edge-case fixtures), ruff for lint |
| Deployment | Not yet deployed — static GeoJSON serving first (per decisions log) |
| Automation | GitHub Actions (planned, for tests + scheduled data refreshes) |

## Project structure

```
├── src/
│   ├── etl/          # Data ingestion, cleaning, export
│   ├── api/          # FastAPI app serving cleaned data
│   └── analysis/     # Spatial analysis and statistics
├── tests/            # pytest suite (parsers, edge-case fixtures)
├── data/
│   ├── raw/          # Source data (never modified)
│   └── processed/    # Cleaned, analysis-ready output (gitignored)
├── context/          # Six-File Context System
├── docs/             # Data source documentation, prototype
├── logs/             # Append-only ETL logs (gitignored)
└── spikes/           # Throwaway experiments
```

## Status

**Phases 0–2 complete** — repo, NOSDRA ETL pipeline (tested), OSM context layer + static portfolio map, FastAPI serving layer. Next: Phase 3 (VIIRS gas flaring pipeline).

## License

MIT — but the data is owned by its respective sources (NOSDRA, EOG/NOAA, NEITI, etc.).
