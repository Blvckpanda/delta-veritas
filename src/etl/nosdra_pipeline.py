"""
NOSDRA Spill Data — ETL Pipeline.

Extract: load raw GeoJSON exported from oilspillmonitor.ng.
Transform: parse dates, validate coordinates, normalise fields, flag outliers.
Load: write cleaned GeoJSON + Parquet (with and without valid geometry).

Usage:
    python src/etl/nosdra_pipeline.py                    # use default paths
    python src/etl/nosdra_pipeline.py --input data/raw/my_export.geojson

Supports both single-file and batch directory mode.
"""

import argparse
import gzip
import json
import logging
import math
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# Ensure config is importable when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


# ── Logging setup ──────────────────────────────────────────────────────────
def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("nosdra_etl")
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
    return logger


logger = _setup_logger()


# ── Date parsing ───────────────────────────────────────────────────────────
def _try_excel_serial(val: str) -> str | None:
    """Handle Excel serial date numbers (days since 1900-01-01)."""
    try:
        serial = int(val)
    except (ValueError, TypeError):
        return None
    if serial < 40000 or serial > 120000:
        return None
    try:
        from datetime import timedelta
        excel_epoch = datetime(1899, 12, 30)  # Excel's epoch (bug included)
        dt = excel_epoch + timedelta(days=serial)
        return dt.strftime("%Y-%m-%d")
    except (OverflowError, ValueError):
        return None


def _is_null_date(raw: str) -> bool:
    """Check if a string is a null/placeholder date value."""
    if not raw or not isinstance(raw, str):
        return True
    stripped = raw.strip().lower().replace("\u2014", "-")  # em-dash →
    return stripped in config.NULL_DATE_STRINGS


def parse_date(raw: str) -> str | None:
    """Try known date formats; return ISO date string or None.

    Handles:
    - Multiple text formats via config.KNOWN_DATE_FORMATS
    - Excel serial numbers (e.g., 45678 → 2025-01-10)
    - Null sentinels (N/A, null, —, …)
    - Timestamp ISO strings with time components
    """
    raw = str(raw).strip() if raw is not None else ""

    if _is_null_date(raw):
        return None

    # Check for Excel serial number (numeric string that looks like a date serial)
    if raw.isdigit() and len(raw) >= 5:
        result = _try_excel_serial(raw)
        if result:
            return result

    # Try text-based format patterns
    for fmt in config.KNOWN_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime(config.OUTPUT_DATE_FORMAT)
        except (ValueError, TypeError):
            continue

    logger.warning("Unparseable date: %r", raw)
    return None


# ── Coordinate validation ──────────────────────────────────────────────────
def validate_coords(lat, lon):
    """Return (lat, lon) if within Nigeria bounds, else (None, None)."""
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None
    if not (config.LAT_MIN <= lat_f <= config.LAT_MAX):
        return None, None
    if not (config.LON_MIN <= lon_f <= config.LON_MAX):
        return None, None
    return lat_f, lon_f


# ── Quantity cleaning ──────────────────────────────────────────────────────
def clean_quantity(val):
    """Parse numeric quantity; return None if missing/implausible."""
    try:
        q = float(val)
    except (TypeError, ValueError):
        return None
    # NaN/inf parse as floats and fail every < / > comparison below, so they
    # must be rejected explicitly (live export contains "nan" quantities).
    if not math.isfinite(q):
        return None
    if q < config.MIN_VALID_SPILL_QUANTITY or q > config.MAX_SPILL_QUANTITY:
        return None
    return round(q, 2)


# ── Live API schema mapping ────────────────────────────────────────────────
def _text(val) -> str:
    """Strip a raw value to text; None becomes ''."""
    return "" if val is None else str(val).strip()


def map_api_record(props: dict) -> dict:
    """Map one raw oilspillmonitor.ng API record to the canonical schema.

    The live endpoint (config.NOSDRA_EXPORT_URL) returns a bare JSON array
    of flat dicts whose keys use a different vocabulary from the manual
    browser export this pipeline was originally built on:

        incidentnumber    → incident_id  (falls back to "NOSDRA-API-<id>"
                                          when blank — ~23% of records)
        incidentdate      → date
        statesaffected    → state        (codes decoded via
                                          config.NOSDRA_STATE_CODES)
        sitelocationname  → community
        spillareahabitat  → impact_area
        estimatedquantity → quantity_spilled
        quantityrecovered → quantity_recovered
        jivdate           → jiv_date

    company / cause / status / contaminant / latitude / longitude keep their
    names. Raw cause codes ("sab", "eqf", …) are preserved verbatim — cause
    normalisation is a deliberate later stage. API-only fields (reportdate,
    formadate, remediation*, attachments, …) are dropped: the canonical
    schema and the API database stay fixed.

    Records already in canonical form (carrying `incident_id`) — or in any
    other unknown vocabulary — pass through untouched, so hand-authored
    fixtures keep flowing unchanged.
    """
    if config.COL_INCIDENT_ID in props:
        return props
    if not ({"incidentnumber", "incidentdate"} & props.keys()):
        return props

    incident_id = str(props.get("incidentnumber") or "").strip()
    if not incident_id:
        incident_id = f"NOSDRA-API-{props.get('id', '')}"

    state = _text(props.get("statesaffected"))
    if state.lower() in config.NULL_DATE_STRINGS:
        state = ""
    else:
        state = config.NOSDRA_STATE_CODES.get(state.upper(), state)

    return {
        config.COL_INCIDENT_ID: incident_id,
        config.COL_DATE: _text(props.get("incidentdate")),
        config.COL_STATE: state,
        config.COL_LGA: _text(props.get("lga")),
        config.COL_COMMUNITY: _text(props.get("sitelocationname")),
        config.COL_COMPANY: _text(props.get("company")),
        config.COL_CAUSE: _text(props.get("cause")),
        config.COL_SPILL_TYPE: "",  # live export has no direct equivalent
        config.COL_QTY_SPILLED: props.get("estimatedquantity"),
        config.COL_QTY_RECOVERED: props.get("quantityrecovered"),
        config.COL_IMPACT_AREA: _text(props.get("spillareahabitat")),
        config.COL_JIV_DATE: _text(props.get("jivdate")),
        config.COL_LATITUDE: props.get("latitude"),
        config.COL_LONGITUDE: props.get("longitude"),
        config.COL_STATUS: _text(props.get("status")),
        config.COL_CONTAMINANT: _text(props.get("contaminant")),
    }


# ── Live export fetch ─────────────────────────────────────────────────────
def fetch_latest(output_path: Path) -> tuple[Path, int]:
    """Download the live NOSDRA export and write it verbatim to output_path.

    A single unauthenticated GET against config.NOSDRA_EXPORT_URL — the same
    public XHR the oilspillmonitor.ng map loads in the browser. Returns
    (path, record_count) after sanity-checking the response shape (a bare
    JSON array); reshaping into the canonical schema happens in the ETL, so
    raw files are never modified after download.
    """
    request = urllib.request.Request(
        config.NOSDRA_EXPORT_URL,
        headers={"User-Agent": config.NOSDRA_FETCH_USER_AGENT},
    )
    logger.info("Fetching NOSDRA export from %s", config.NOSDRA_EXPORT_URL)
    with urllib.request.urlopen(request, timeout=config.NOSDRA_FETCH_TIMEOUT_S) as response:
        payload = response.read()

    # The server gzips the response regardless of Accept-Encoding, and urllib
    # (unlike a browser) does not decompress transparently.
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)

    records = json.loads(payload)
    if not isinstance(records, list) or not records:
        shape = type(records).__name__
        count = len(records) if isinstance(records, list) else "n/a"
        raise ValueError(f"unexpected export shape: {shape} (count={count})")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    logger.info(
        "Wrote %s — %d raw records, %.1f KB", output_path, len(records), len(payload) / 1024
    )
    return output_path, len(records)


# ── Feature transformation ────────────────────────────────────────────────
def transform_feature(props: dict):
    """Normalise a single NOSDRA feature's properties."""
    incident_id = props.get(
        config.COL_INCIDENT_ID,
        str(props.get("incident_number", props.get("id", ""))),
    )
    date = parse_date(props.get(config.COL_DATE, ""))
    jiv_date = parse_date(props.get(config.COL_JIV_DATE, ""))

    lat, lon = validate_coords(
        props.get(config.COL_LATITUDE), props.get(config.COL_LONGITUDE)
    )

    qty = clean_quantity(props.get(config.COL_QTY_SPILLED))
    recovered = clean_quantity(props.get(config.COL_QTY_RECOVERED))

    recovery_pct = None
    if qty and recovered is not None and qty > 0:
        recovery_pct = round(min(recovered / qty * 100, 100), 1)

    year = None
    month = None
    if date:
        try:
            dt = datetime.strptime(date, config.OUTPUT_DATE_FORMAT)
            year, month = dt.year, dt.month
        except ValueError:
            pass

    return {
        config.COL_INCIDENT_ID: incident_id,
        config.COL_DATE: date,
        config.COL_YEAR: year,
        config.COL_MONTH: month,
        config.COL_STATE: (props.get(config.COL_STATE) or "").strip(),
        config.COL_LGA: (props.get(config.COL_LGA) or "").strip(),
        config.COL_COMMUNITY: (props.get(config.COL_COMMUNITY) or "").strip(),
        config.COL_COMPANY: (props.get(config.COL_COMPANY) or "").strip(),
        config.COL_CAUSE: (props.get(config.COL_CAUSE) or "").strip(),
        config.COL_SPILL_TYPE: (props.get(config.COL_SPILL_TYPE) or "").strip(),
        config.COL_QTY_SPILLED: qty,
        config.COL_QTY_RECOVERED: recovered,
        config.COL_RECOVERY_PCT: recovery_pct,
        config.COL_IMPACT_AREA: (props.get(config.COL_IMPACT_AREA) or "").strip(),
        config.COL_JIV_DATE: jiv_date,
        config.COL_LATITUDE: lat,
        config.COL_LONGITUDE: lon,
        config.COL_STATUS: (props.get(config.COL_STATUS) or "").strip(),
        config.COL_CONTAMINANT: (props.get(config.COL_CONTAMINANT) or "").strip(),
        config.COL_DATA_SOURCE: config.SOURCE_NOSDRA,
    }


# ── Main pipeline ──────────────────────────────────────────────────────────
def _load_geojson(path: Path) -> list:
    """Load GeoJSON and return list of features."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data  # array of features
    if isinstance(data, dict):
        features = data.get("features", [])
        # A plain properties dict rather than a FeatureCollection?
        if not features and any(k in data for k in ("incident_id", "incident_number", "id")):
            return [data]
        return features
    return []


def run_pipeline(input_path: Path, output_dir: Path):
    """Execute full ETL pipeline on one file."""
    logger.info("Input file: %s", input_path)
    features = _load_geojson(input_path)
    logger.info("Loaded %d raw features", len(features))

    records = []
    api_mapped = 0
    dropped_no_coords = 0
    dropped_no_date = 0
    dropped_other = 0

    for feat in features:
        props = feat.get("properties", feat)
        mapped = map_api_record(props)
        if mapped is not props:
            api_mapped += 1
        rec = transform_feature(mapped)
        if not rec[config.COL_INCIDENT_ID]:
            dropped_other += 1
            continue
        if rec[config.COL_LATITUDE] is None and rec[config.COL_LONGITUDE] is None:
            dropped_no_coords += 1
        if rec[config.COL_DATE] is None:
            dropped_no_date += 1
        records.append(rec)

    logger.info(
        "Transformed %d records (no_coords=%d, no_date=%d, other_drop=%d)",
        len(records), dropped_no_coords, dropped_no_date, dropped_other,
    )
    if api_mapped:
        logger.info(
            "Schema mapping: %d records converted from the live API vocabulary",
            api_mapped,
        )

    # Build output FeatureCollection
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": (
                    {
                        "type": "Point",
                        "coordinates": [r[config.COL_LONGITUDE], r[config.COL_LATITUDE]],
                    }
                    if r[config.COL_LATITUDE] is not None
                    else None
                ),
                "properties": dict(r),
            }
            for r in records
        ],
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"nosdra_clean_{timestamp}.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2, default=str)
    logger.info("Wrote %s (%d features)", out_path, len(fc["features"]))

    # Summary stats
    with_coords = sum(1 for r in records if r[config.COL_LATITUDE] is not None)
    with_date = sum(1 for r in records if r[config.COL_DATE] is not None)
    logger.info(
        "Summary: %d total | %d with coords | %d with dates",
        len(records), with_coords, with_date,
    )

    return fc


def main():
    parser = argparse.ArgumentParser(description="NOSDRA spill data ETL")
    parser.add_argument("--input", type=Path, default=None,
                        help="Path to raw NOSDRA GeoJSON file")
    parser.add_argument("--output", type=Path, default=config.DATA_PROCESSED,
                        help="Output directory (default: data/processed/)")
    parser.add_argument("--fetch", action="store_true",
                        help="Download the live export from the NOSDRA API first")
    args = parser.parse_args()

    input_path = args.input or config.DATA_RAW / config.NOSDRA_INPUT_FILENAME
    if args.fetch:
        try:
            fetch_latest(input_path)
        except (OSError, ValueError) as exc:
            logger.error("Fetch failed: %s", exc)
            sys.exit(1)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        logger.info(
            "Export data from https://oilspillmonitor.ng (click download button) "
            "and save as %s", input_path
        )
        sys.exit(1)

    run_pipeline(input_path, args.output)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
