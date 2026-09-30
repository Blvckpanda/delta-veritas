"""
OSM Context Layer — ETL Pipeline.

Fetches OpenStreetMap context layers for the Niger Delta via Overpass API:
- Administrative boundaries (states)
- Major roads (trunk, primary, secondary)
- Settlements (towns, cities)
- Coastline / major water bodies

Ethical constraint: Only fetches public basemap context (roads, settlements,
boundaries). Does NOT fetch pipelines, wellheads, flow stations, or any
hydrocarbon infrastructure.

Output: Cleaned GeoJSON files in data/processed/osm_*.geojson

Usage:
    python src/etl/osm_pipeline.py                    # fetch all layers
    python src/etl/osm_pipeline.py --layer roads      # fetch only roads
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

logger = logging.getLogger("osm_etl")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(config.LOG_FILE, mode="a", encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter(config.LOG_FORMAT, config.LOG_DATE_FORMAT))
sh = logging.StreamHandler(sys.stdout)
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
logger.handlers.clear()
logger.addHandler(fh)
logger.addHandler(sh)


# ── Niger Delta bounding box (slightly wider than ND for context) ─────────
# Format: south, west, north, east (Overpass convention)
ND_BBOX = "4.0,4.5,7.0,9.0"  # lat_min, lon_min, lat_max, lon_max
# Alternative format often used: min_lat, min_lon, max_lat, max_lon (same)

# Overpass API endpoint
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Rate limiting: 1 request per 5 seconds (be polite)
REQUEST_DELAY = 5

# Niger Delta states (for boundary queries)
ND_STATES = [
    "Akwa Ibom",
    "Bayelsa",
    "Cross River",
    "Delta",
    "Edo",
    "Imo",
    "Ondo",
    "Rivers",
]


# ── Overpass queries ──────────────────────────────────────────────────────

def _build_overpass_query(query_fragment: str) -> str:
    """Wrap a query fragment in the full Overpass QL skeleton."""
    return f"[out:json][timeout:45];({query_fragment});out geom;"


def _fetch_overpass(query: str, retries: int = 3) -> dict[str, Any] | None:
    """Send a query to the Overpass API with retry logic."""
    params = f"data={query}".encode()
    req = Request(OVERPASS_URL, data=params, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "NigerDeltaObservatory/0.1 (portfolio project)")

    for attempt in range(retries):
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            logger.warning("Overpass attempt %d/%d failed: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(REQUEST_DELAY)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from Overpass: %s", e)
            return None

    logger.error("Overpass query failed after %d retries", retries)
    return None


def query_state_boundaries() -> dict | None:
    """Fetch Niger Delta state boundaries from OSM via bounding box."""
    # Use bbox to get admin_level=4 boundaries in the region
    query = _build_overpass_query(
        f'rel["admin_level"="4"]["boundary"="administrative"]({ND_BBOX});'
    )
    logger.info("Fetching state boundaries...")
    return _fetch_overpass(query)


def query_major_roads() -> dict | None:
    """Fetch major roads (trunk, primary, secondary) in the Niger Delta bbox."""
    query = _build_overpass_query(
        f'way["highway"~"trunk|primary|secondary"]({ND_BBOX});'
    )
    logger.info("Fetching major roads...")
    return _fetch_overpass(query)


def query_settlements() -> dict | None:
    """Fetch towns and cities in the Niger Delta bbox."""
    query = _build_overpass_query(
        f'node["place"~"city|town|village"]({ND_BBOX});'
    )
    logger.info("Fetching settlements...")
    return _fetch_overpass(query)


# ── OSM response → GeoJSON converter ──────────────────────────────────────

def _osm_element_to_geojson(element: dict) -> dict | None:
    """Convert a single Overpass element to a GeoJSON Feature."""
    elem_type = element.get("type")
    tags = element.get("tags", {})

    geometry = None

    if elem_type == "node":
        lon = element.get("lon")
        lat = element.get("lat")
        if lon is not None and lat is not None:
            geometry = {"type": "Point", "coordinates": [lon, lat]}

    elif elem_type == "way":
        coords = _extract_way_coords(element)
        if coords and len(coords) >= 2:
            # Determine if it's an area (closed way) or a line
            if coords[0] == coords[-1] and len(coords) > 3:
                geometry = {"type": "Polygon", "coordinates": [coords]}
            else:
                geometry = {"type": "LineString", "coordinates": coords}

    elif elem_type == "relation":
        # For boundaries — extract outer members as MultiPolygon
        polys = _extract_relation_polygons(element)
        if len(polys) == 1:
            geometry = {"type": "Polygon", "coordinates": polys[0]}
        elif len(polys) > 1:
            geometry = {"type": "MultiPolygon", "coordinates": [[p] for p in polys]}

    if geometry is None:
        return None

    # Build properties from tags + metadata
    properties = {**tags}
    properties["_osm_id"] = element.get("id")
    properties["_osm_type"] = elem_type

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


def _extract_way_coords(element: dict) -> list[list[float]] | None:
    """Extract node coordinates from a way's geometry."""
    geom = element.get("geometry")
    if not geom or not isinstance(geom, list):
        return None
    coords = []
    for node in geom:
        lon = node.get("lon")
        lat = node.get("lat")
        if lon is not None and lat is not None:
            coords.append([lon, lat])
    return coords if coords else None


def _extract_relation_polygons(element: dict) -> list[list[list[float]]]:
    """Extract polygon coordinates from a relation's members."""
    members = element.get("members", [])
    polygons = []
    for member in members:
        if member.get("role") != "outer":
            continue
        geom = member.get("geometry", [])
        coords = []
        for node in geom:
            lon = node.get("lon")
            lat = node.get("lat")
            if lon is not None and lat is not None:
                coords.append([lon, lat])
        if coords and len(coords) >= 3:
            # Close the ring if needed
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            polygons.append(coords)
    return polygons


def overpass_to_geojson(overpass_response: dict) -> dict:
    """Convert an Overpass API response to a GeoJSON FeatureCollection."""
    elements = overpass_response.get("elements", [])
    features = []

    for element in elements:
        feat = _osm_element_to_geojson(element)
        if feat:
            features.append(feat)

    return {
        "type": "FeatureCollection",
        "features": features,
    }


# ── Layer-specific processing ─────────────────────────────────────────────

def process_boundaries(raw: dict) -> dict:
    """Process boundary relations into simplified GeoJSON."""
    fc = overpass_to_geojson(raw)
    # Clean up properties — keep only name and admin_level
    for feat in fc["features"]:
        props = feat["properties"]
        clean = {
            "name": props.get("name", "(unnamed)"),
            "admin_level": props.get("admin_level"),
            "type": props.get("boundary"),
            "_osm_id": props.get("_osm_id"),
        }
        feat["properties"] = clean
    logger.info("  → %d boundary features", len(fc["features"]))
    return fc


def process_roads(raw: dict) -> dict:
    """Process road geometries into simplified GeoJSON."""
    fc = overpass_to_geojson(raw)
    for feat in fc["features"]:
        props = feat["properties"]
        clean = {
            "name": props.get("name", "(unnamed)"),
            "highway": props.get("highway"),
            "ref": props.get("ref", ""),
            "oneway": props.get("oneway", "no"),
            "surface": props.get("surface", "unknown"),
            "_osm_id": props.get("_osm_id"),
        }
        feat["properties"] = clean
    logger.info("  → %d road features", len(fc["features"]))
    return fc


def process_settlements(raw: dict) -> dict:
    """Process settlement points into simplified GeoJSON."""
    fc = overpass_to_geojson(raw)
    for feat in fc["features"]:
        props = feat["properties"]
        clean = {
            "name": props.get("name", "(unnamed)"),
            "place": props.get("place"),
            "population": props.get("population"),
            "_osm_id": props.get("_osm_id"),
        }
        feat["properties"] = clean
    logger.info("  → %d settlement features", len(fc["features"]))
    return fc


# ── Main runner ───────────────────────────────────────────────────────────

LAYER_HANDLERS = {
    "boundaries": (query_state_boundaries, process_boundaries, "osm_boundaries"),
    "roads": (query_major_roads, process_roads, "osm_roads"),
    "settlements": (query_settlements, process_settlements, "osm_settlements"),
}


def run_pipeline(output_dir: Path, layers: list[str] | None = None):
    """Fetch specified OSM layers and write cleaned GeoJSON files."""
    if layers is None:
        layers = list(LAYER_HANDLERS.keys())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for i, layer in enumerate(layers):
        if layer not in LAYER_HANDLERS:
            logger.warning("Unknown layer: %s — skipping", layer)
            continue

        query_fn, process_fn, filename_prefix = LAYER_HANDLERS[layer]

        # Rate limit: delay between requests (not on first)
        if i > 0:
            logger.info("Waiting %ds before next request...", REQUEST_DELAY)
            time.sleep(REQUEST_DELAY)

        raw = query_fn()
        if raw is None:
            logger.error("Failed to fetch layer: %s", layer)
            continue

        fc = process_fn(raw)
        if not fc["features"]:
            logger.warning("No features in layer: %s", layer)
            continue

        out_path = output_dir / f"{filename_prefix}_{timestamp}.geojson"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(fc, f, indent=2)
        logger.info("Wrote %s (%d features)", out_path, len(fc["features"]))

    logger.info("OSM pipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OSM Context Layer ETL")
    parser.add_argument(
        "--layer", "-l",
        choices=list(LAYER_HANDLERS.keys()),
        help="Single layer to fetch (default: all)",
    )
    parser.add_argument("--output", type=Path, default=config.DATA_PROCESSED)
    args = parser.parse_args()

    layers = [args.layer] if args.layer else None
    run_pipeline(args.output, layers)
