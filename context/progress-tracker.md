# Progress Tracker

## Phase Status

| Phase | Description | Status | Started | Completed |
|-------|-------------|--------|---------|-----------|
| 0 | Repo + Data Source Inventory | **Complete** | 2026-07-30 | 2026-07-30 |
| 1 | NOSDRA Spill ETL Pipeline | **Complete** | 2026-07-30 | 2026-07-30 |
| 2 | OSM Context Layer + Portfolio Map | **Complete** | 2026-07-30 | 2026-07-30 |
| 3 | Gas Flaring Data Pipeline | Not started | — | — |
| 4 | Spatial Analysis | Not started | — | — |
| 5 | Frontend Build-out | Not started | — | — |

## Phase 0 — Done When

- [x] Repo initialised with git
- [x] README.md with ethical framing
- [x] AGENTS.md created
- [x] Six-File Context System in context/
- [x] `data-sources.md` documented with URLs, formats, known limitations
- [x] NOSDRA data source verified (HTTP 200 from oilspillmonitor.ng)
- [x] VIIRS data source verified (HTTP 200 from payneinstitute.mines.edu)
- [x] NEITI / NDPC / NUPRC data sources verified (HTTP 200)
- [x] Copernicus STAC identified as GEE alternative
- [x] First raw data file note: requires manual browser export

## Phase 1 — Done When

- [x] `config.py` centralised — column names, paths, thresholds, 17 date formats
- [x] `nosdra_pipeline.py` — ETL pipeline reading GeoJSON → date parsing → coord validation → cleaned GeoJSON
- [x] 6 sample records pipeline passes cleanly
- [x] 9 edge case records (17 date formats + Excel serial + null sentinels) all pass
- [x] `requirements.txt` pinned with all deps
- [x] Null sentinel handling: 19 patterns trapped
- [x] Coordinate validation: Nigeria bounds enforced
- [x] Date fallback chain: 17 format patterns + Excel serial decoder
- [x] FastAPI schema (3 models) built and seeded
- [x] Live API fetch (`--fetch`) + API→canonical schema mapping, tested with no network
- [x] First real export processed: 21,171 records (2006–2026), zero drops, 22.6% without coords
- [x] Weekly digest: newly disclosed + newly occurred sections, state-tracked across runs, markdown output + tests
- [x] Live map timeline scrubber (cumulative/single-year), verified in browser over the full 20k record

## Phase 2 — Done When

- [x] OSM Overpass API pipeline: `src/etl/osm_pipeline.py`
- [x] Fetches Niger Delta state boundaries (16 features)
- [x] Fetches major roads (6,914 features, sampled to 500 for map)
- [x] Fetches settlements (3,455 features)
- [x] All layers respect ethical boundary — no pipelines/infrastructure
- [x] Portfolio map generator: `src/analysis/map_report.py`
- [x] 6 data layers: boundaries, roads (3 classes), settlements, spill incidents
- [x] Dark theme cartography with scale bar, north arrow, legend, metadata
- [x] State labels deduplicated (once per state, not per ring)
- [x] Proxy artist legend (no matplotlib scatter/line rendering bugs)
- [x] Ethical boundary noted in map footer: "context layers: settlements, roads, boundaries only"
- [x] Performance: roads sampled to 500 features, settlements to 200
- [x] Portfolio map output: 907 KB, 200 DPI
- [x] Old artifacts cleaned up from data/processed/

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-30 | Ethical boundary: no pipeline/wellhead/flow-station coordinates | Claude's advice — prevents targeting risk, stronger portfolio signal |
| 2026-07-30 | Start with static GeoJSON serving (Option B), not PostGIS | Faster MVP, defer database complexity until needed |
| 2026-07-30 | Use Copernicus CDSE STAC instead of GEE for satellite data | GEE account approval delays; CDSE STAC is instant-access |
| 2026-07-30 | Separate repository (not inside energy-data-dashboard) | Clear project boundary, independent portfolio piece |
| 2026-07-30 | Phase 2 redefined: OSM context layer + static portfolio map | Claude's refined project-overview.md phases; OSM provides cartographic basemap context before satellite work |
| 2026-07-30 | Overpass API for OSM data instead of planet.osm export | Instant query results, no download required, sufficient for 1-off context layers |
| 2026-07-30 | Road sampling (500/6914) and settlement sampling (200/3455) | Full resolution crashes SVG/matplotlib; sample sufficient for cartographic context |
| 2026-09-30 | First commit hygiene pass: .gitignore, MIT LICENSE, requirements.txt corrected to actual imports, docs↔code alignment, data_source field added to ETL output, pytest suite for parsers + edge fixtures | Repo had zero commits and no tests; docs claimed a stack the code didn't have. Truthful baseline before Phase 3 |
| 2026-09-30 | Deferred deps (geopandas, rasterio, pystac-client, stackstac, fiona, pyarrow, folium, h5py) moved to commented section of requirements.txt | Nothing imports them yet — they get re-promoted by the phase that first does (Phase 3) |
| 2026-10-01 | Data-quality scorecard is the flagship analysis artifact (`src/analysis/quality_scorecard.py`) | Independent audit of the official record — nobody else publishes systematic QC of NOSDRA data; methodology caveat (audits the record, not ground truth) is rendered into every output |
| 2026-10-01 | API tests isolate via OBSERVATORY_DATABASE_URL + NullPool; idempotent best-effort migrations add data_source to existing DBs | Tests must never write data/observatory.db; aiosqlite connections are loop-bound so pools break across asyncio.run/TestClient loops |
| 2026-10-03 | Scripted fetch replaces manual export as the primary NOSDRA ingest path (`--fetch` hits the SPA's own unauthenticated XHR endpoint) | The manual File System API download was unreliable; the endpoint was discovered by inspecting the SPA's network traffic and serves the full 21,171-record table (2006–2026) in one GET, gzipped |
| 2026-10-03 | Live-API schema mapped in `map_api_record` (canonical records pass through untouched); raw cause codes and unmapped state codes preserved, API-only fields dropped | One mapping layer keeps the canonical schema, API DB, scorecard, and map unchanged while the ingest path switches vocabulary; nothing is silently relabelled or dropped (first real run: 21,171 in → 21,171 out) |
| 2026-10-03 | `clean_quantity` rejects NaN/inf explicitly; API seed collapses re-reported incident ids to their latest update (20,038 of 21,171 unique) | The live export contains `"nan"` volume strings — NaN parses as float and fails every < / > comparison, silently poisoning volume sums; the serving layer enforces unique incident_id while the scorecard still audits the full record, duplicates included |
| 2026-10-09 | Weekly digest (`src/etl/digest.py`): two sections — newly disclosed (unseen incident IDs, catches backfills) vs newly occurred (date window) | "New" has two meanings on a messy register; a late-entered spill can appear in both. State (seen IDs + last run) is machine-local in data/processed/digest_state.json, never committed; first run reports the full record as baseline unless --seed |
| 2026-10-09 | Map timeline slider filters client-side via source.setData with a cumulative/single-year toggle; the prototype now paginates the full API record instead of the newest 500 | Clustering stays intact because data is re-sliced, not filtered by layer; a slider over only the newest 500 incidents would misrepresent the record's timespan (2006–2026) |

## Open Questions

- [ ] How does NOSDRA data export work? (manual CSV? API? GeoServer?) — resolved: manual SPA download via browser File System API
- [ ] VIIRS VNF raw data: download nightly files or use aggregated NOSDRA Gas Flare Tracker data?
- [ ] Does OSM road coverage in southern Bayelsa/Rivers affect map appearance enough to need a caveat?
