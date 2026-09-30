# Data Source Inventory

## 1. NOSDRA Oil Spill Data
- **Source:** https://nosdra.oilspillmonitor.ng
- **Full-screen app:** https://oilspillmonitor.ng
- **Access:** Web interface with filter/download. Download button exports `nosdra.json` (GeoJSON).
- **Coverage:** 2006–present, ~5,000+ records
- **Schema (inferred):**  
  `incident_id`, `date`, `state`, `lga`, `community`, `company`, `cause`, `spill_type`, `quantity_spilled`, `quantity_recovered`, `impact_area`, `jiv_date`, `latitude`, `longitude`, `status`, `contaminant`
- **Format:** JSON/GeoJSON via UI export
- **Limitations:** ~20-40% of records have missing/null coordinates. Date formats inconsistent. `cause` field is free-text, not normalized.
- **License:** Public government data (NOSDRA, Nigerian Ministry of Environment)

## 2. NOSDRA Gas Flare Data (VIIRS Nightfire)
- **Source:** https://nosdra.gasflaretracker.ng
- **Full-screen app:** https://gasflaretracker.ng
- **Backend:** EOG VIIRS Nightfire dataset (Colorado School of Mines)
- **Coverage:** 2012–present, monthly composites
- **Schema:** `location`, `state`, `year`, `month`, `flare_count`, `avg_temperature_k`, `estimated_volume_m3`, `latitude`, `longitude`
- **Spatial resolution:** Native ~750m pixel (VIIRS), with sub-pixel analysis
- **Limitations:** Small flares systematically under-detected. Co-located flares merged. Volume estimates have wide error margins.
- **Access:** Web interface by state/year, or raw VIIRS Nightfire data from https://eogdata.mines.edu/products/vnf/

## 3. NEITI Oil & Gas Industry Reports
- **Source:** https://neiti.gov.ng
- **Content:** Annual reports with facility-level production, lifting, and royalty data
- **Relevant years:** 2020–2025 (most recent available)
- **Format:** PDF reports, some Excel appendices
- **Key data:** Production volumes per facility, flare volumes, royalty payments, transportation losses

## 4. NUPRC (HostComply) — HCDT Compliance
- **Source:** https://hostcomply.nuprc.gov.ng
- **Content:** Host Community Development Trust (HCDT) compliance data under PIA 2021
- **Data:** Community trust boundaries, operator contributions (3% OPEX), project allocations
- **Format:** Web portal with some downloadable reports

## 5. Copernicus Sentinel-2 (STAC API)
- **Source:** https://browser.stac.dataspace.copernicus.eu
- **API:** Copernicus Data Space Ecosystem STAC API
- **Coverage:** Niger Delta region, 2016–present, 5-day revisit
- **Resolution:** 10m (visible/NIR), 20m (SWIR)
- **Use case:** NDVI change detection, vegetation loss, mangrove health

## 6. NOAA VIIRS Nightfire (Raw)
- **Source:** https://eogdata.mines.edu/products/vnf/
- **Access:** Direct file download (annual/monthly CSV + KML)
- **Coverage:** Global, 2012–present
- **Use case:** Gas flaring volume estimation, flare count trends
- **Resolution:** ~750m pixels, sub-pixel temperature analysis

## 7. OpenStreetMap (Overpass API)
- **Source:** https://overpass-api.de
- **Data:** Roads, settlements, water bodies, administrative boundaries for Niger Delta
- **Use case:** Base map layers, community boundary approximation, distance analysis
- **Access:** Overpass QL queries
