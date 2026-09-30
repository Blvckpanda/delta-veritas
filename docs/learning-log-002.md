# Learning Log 002 — Phase 2: OSM Context Layer + Portfolio Map

## Date
2026-07-30

## What I built
1. **OSM Overpass pipeline** (`src/etl/osm_pipeline.py`): Python ETL that queries the Overpass API for three context layers across the Niger Delta (bbox 4.0–7.0°N, 4.5–9.0°E):
   - State administrative boundaries — 16 relation features
   - Major roads (trunk, primary, secondary) — 6,914 features
   - Settlements (cities, towns, villages) — 3,455 features

2. **Portfolio map generator** (`src/analysis/map_report.py`): matplotlib thematic map compositing all layers with:
   - Dark theme (`#1a1a2e` background)
   - Scale bar (50 km), north arrow, dual-column legend
   - Color-coded roads (yellow/orange/brown), settlements (blue), spills (red for oil, cyan for condensate)
   - State labels with background box (deduplicated — each state once)
   - Metadata footer + ethical boundary note

## What went well
- **Overpass API is remarkably accessible**: POST a QL query, get GeoJSON-like output. 3 queries returned 10K+ features in under 10 seconds total.
- **URL encoding matters**: The raw bytes-encoding approach to POST data failed with 400 errors; switching to `data={query}` form-urlencoding fixed it.
- **matplotlib proxy artists**: Using `Circle` patches instead of `plt.scatter([], [])` for legend entries eliminated the rendering bug where condensate spill showed as a line.
- **State label deduplication**: The Overpass response had multiple geometry rings per boundary feature; moving the label call outside the ring loop and tracking `labeled_states` with a `set()` fixed the duplicate label problem in one line.

## What I'd do differently
- **Fetch fewer OSM roads**: 6,914 was more than the map needs. Even sampling to 500 looked fine. I should reduce the Overpass query to trunk+primary only (skip secondary) for the map, and keep secondary only for spatial analysis.
- **Boundary fetching**: The current approach uses bbox filtering which gives us "Southwest", "Abia", "Anambra" etc. from outside the core Niger Delta. I filter by state name in `map_report.py` but it would be cleaner to do a targeted name-filtered query in the pipeline.
- **matplotlib for portfolio**: This works but 200 DPI PNG is not the ideal portfolio format. For Baker Hughes/EPC audiences, I'd want SVG or a tileset that zooms. Worth considering FlatGeobuf for the interactive version.

## Ethical check
- All OSM data downloaded is public basemap context (roads, settlements, boundaries).
- The map footer explicitly states: "Context layers: settlements, roads, boundaries only."

## Phase 3 preview
Next: VIIRS gas flaring pipeline. The skeleton in `src/etl/viirs_pipeline.py` (123 lines) needs to be fleshed out with:
- Real data download from EOG/NOAA
- Temperature filtering (600K–2000K)
- Plume aggregation (VIIRS ~750m pixels → flare sites)
- Spatial joining with OSM context to identify nearest settlement/state
