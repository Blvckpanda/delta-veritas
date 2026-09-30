# Niger Delta Environmental & Infrastructure Disclosure Observatory

## One-liner
An interactive, publicly-deployed geospatial platform tracking oil spill incidents, gas
flaring intensity, and officially disclosed infrastructure investment across the Niger
Delta — built from Port Harcourt, using only public disclosure data.

## Why this shape, not the original pitch
The first draft of this project (and an earlier AI-agent pitch) proposed mapping pipeline
routes, wellhead/flow station coordinates, and illegal refinery locations on a live,
searchable map. That's a different artifact than what's described here, and it's excluded
by design:

- **No pipeline routes, wellhead/flow station coordinates, or live infrastructure
  targeting layers.** Consolidating scattered public facts into one searchable map is
  itself the risk — the Delta has active, ongoing pipeline vandalism and bunkering, and a
  clean consolidated map is meaningfully more useful to bad actors than the same facts
  spread across a dozen PDFs.
- **No illegal refinery / artisanal site detection**, even via satellite change-detection.
  Precise geolocation of those sites risks getting real people raided or killed.
- **In scope:** spill records, flaring intensity, and infrastructure *investment
  disclosures* that government/transparency bodies have already chosen to publish
  (NOSDRA, NEITI, NDDC). Using what's already been disclosed is a different act than
  independently triangulating what wasn't.

This isn't a hedge — it's also the more defensible, more portfolio-relevant project.
Hiring panels care about sourcing rigor, data engineering, and communication, not whether
you can pinpoint a flow station.

## Audience & what each signals
Tailor the final write-up/demo emphasis depending on who's looking:

| Audience | Wants to see | Emphasize |
|---|---|---|
| Baker Hughes / oilfield services recruiter | Environmental compliance literacy, sourcing rigor | Spill/flaring analysis, methodology section |
| Oil & gas EPC consultancy | Toolchain justification, reproducibility | ETL pipeline, `context/` docs, repo hygiene |
| Grad GIS program | Methodological honesty, literature engagement | Limitations section (below), citations |

## Architecture (Direction A, environmental-data version)
- **Frontend:** Next.js + MapLibre GL — layer toggles (spills / flaring / disclosed
  investment), timeline slider, popups
- **Backend:** FastAPI serving GeoJSON/TileJSON
- **Database:** PostGIS on Supabase, or flat GeoJSON/FlatGeobuf if traffic stays light —
  don't over-provision early
- **Data pipeline:** Python, scheduled via GitHub Actions where sources allow
  (NOSDRA export is manual — see below)
- **Deploy:** Vercel (frontend), a small always-on host or serverless function for the API

## Data sources — in scope
| Source | What | Known limitation |
|---|---|---|
| NOSDRA (oilspillmonitor.ng) | Spill incidents, often geocoded | Manual export only (no headless download); expect 20–40% of records with missing/invalid coordinates, inconsistent date formats, free-text "cause" field with 40+ variants, inconsistent volume units |
| NOAA VIIRS Nightfire | Gas flaring intensity/location | ~750m native pixel — reliable for large flares (Bonny-scale), **not reliable for individual wellhead flares**, which are often sub-pixel and undercounted |
| NEITI | Facility-level production/revenue disclosures | Annual, not real-time; format varies by report year |
| NDDC | Development project locations | Project status often stale/unverified against ground truth |
| OpenStreetMap (context layer only — roads/settlements, not pipelines) | Basemap context | Coverage is dense near Port Harcourt, sparse rural — this creates a *reporting bias*, not a true absence-of-infrastructure signal. Don't use OSM density as a proxy for "distance from infrastructure" in analysis without flagging this. |

## Satellite tooling: use Copernicus STAC, not Google Earth Engine
GEE needs account approval (can take 1–3 weeks), Cloud Console setup, and a billing
account even though usage is free — a bad Phase-1 dependency. The **Copernicus Data Space
Ecosystem STAC API** needs only an instant API key, and `pystac_client` + `stackstac`
gives you xarray DataArrays that play well with geopandas. Use GEE later only if you hit a
compute ceiling STAC can't handle.

## Phased build — realistic timeline (solo, part-time)
| Phase | Work | Est. time | Signals to reader |
|---|---|---|---|
| 1 | NOSDRA manual export → ETL (date parsing, coordinate validation, dedup) | 1–2 weeks — budget for messy data, this is most of the grind | Data engineering rigor |
| 2 | OSM context layer (Overpass API) + first static map | 1 week | Basic geospatial competence |
| 3 | VIIRS flaring pipeline (Copernicus STAC / EOG export) | 2–4 weeks — harder than it looks | Willingness to work with imperfect remote-sensing data |
| 4 | Spatial analysis (spill patterns over time, flaring trends, disclosure vs. incident overlap) | 2–3 weeks | Methodological maturity — **explicitly name the OSM/reporting bias caveat in the write-up** |
| 5 | Frontend build-out, deploy, methodology write-up | 2–4 weeks | Communication, shippable product |

**Total: ~8–14 weeks**, not a straight line — expect Phase 1 and 3 to eat the most
unplanned time.

## Known analysis trap to name explicitly in your write-up
Any "distance from infrastructure" or "spill density near development" analysis is really
"distance from *known, mapped* infrastructure." Because OSM/NDDC coverage is uneven
across the Delta, sparsely-mapped rural areas will falsely look like they have fewer
spills near infrastructure. Naming this limitation in your report is a stronger signal
than pretending the data is clean — it's the difference between a student project and
something that reads like real research practice.

## Current repo state (as of this build)
- Six-File Context System in `context/` — keep the ethical boundary explicitly in
  `architecture.md` and `AGENTS.md` as already done
- NOSDRA ETL pipeline confirmed working end-to-end on sample data
- Static map generator (matplotlib) confirmed working
- VIIRS pipeline skeleton in place, pending real EOG/Copernicus data
- MapLibre interactive prototype renders correctly outside the sandboxed browser

## Next concrete step
Get a real NOSDRA export in (manual browser download, per your existing instructions),
run it through the pipeline, and get the Phase 2 static map showing real spill data. That's
your first genuine "shippable increment" for the public learning log.
