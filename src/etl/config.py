"""
Niger Delta Environmental Risk Observatory — Configuration.

Single source of truth for all column names, file paths, date formats,
and thresholds used across the ETL pipeline.
"""

from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
LOGS_DIR = PROJECT_ROOT / "logs"
DOCS_DIR = PROJECT_ROOT / "docs"

# Ensure directories exist
for d in [DATA_RAW, DATA_PROCESSED, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── NOSDRA Spill Data ──────────────────────────────────────────────────────
# Input file name (exported from oilspillmonitor.ng via download button)
NOSDRA_INPUT_FILENAME = "nosdra.json"

# Clean output filenames (ISO date appended at runtime)
NOSDRA_CLEAN_GEOJSON = "nosdra_spills_clean.geojson"
NOSDRA_CLEAN_PARQUET = "nosdra_spills_clean.parquet"
NOSDRA_Q12_FILTERED = "nosdra_spills_q1_2.parquet"  # Q1 & Q2 2025 sample

# ── NOSDRA export fetch (live API) ─────────────────────────────────────────
# The oilspillmonitor.ng SPA loads its full historical incident table from
# this endpoint via a plain, unauthenticated XHR — the same data its manual
# Download button wraps. Scripted fetch is the primary ingest path; the
# manual browser export stays as fallback (docs/nosdra-export-guide.md).
NOSDRA_EXPORT_URL = (
    "https://oilspillmonitor.ng/api/spill-data.php?dataset=nosdra&format=json"
)
NOSDRA_FETCH_TIMEOUT_S = 120
NOSDRA_FETCH_USER_AGENT = "niger-delta-observatory/0.1 (public-disclosure ETL)"

# `statesaffected` in the live export arrives as 2-letter codes plus stray
# full names (54 distinct variants observed on 2026-10-03). Only
# unambiguous Niger Delta codes are decoded; anything else passes through
# raw and is logged so nothing is silently mislabelled.
NOSDRA_STATE_CODES = {
    "RI": "Rivers",
    "BY": "Bayelsa",
    "DE": "Delta",
    "AK": "Akwa Ibom",
    "IM": "Imo",
    "AB": "Abia",
    "ED": "Edo",
    "ON": "Ondo",
    "CR": "Cross River",
}

# ── Column Names (mapped from NOSDRA GeoJSON properties) ───────────────────
COL_INCIDENT_ID = "incident_id"
COL_DATE = "date"  # date of spill incident
COL_STATE = "state"
COL_LGA = "lga"
COL_COMMUNITY = "community"
COL_COMPANY = "company"
COL_CAUSE = "cause"
COL_SPILL_TYPE = "spill_type"
COL_QTY_SPILLED = "quantity_spilled"
COL_QTY_RECOVERED = "quantity_recovered"
COL_IMPACT_AREA = "impact_area"
COL_JIV_DATE = "jiv_date"
COL_LATITUDE = "latitude"
COL_LONGITUDE = "longitude"
COL_STATUS = "status"
COL_CONTAMINANT = "contaminant"

# Internally derived columns
COL_YEAR = "year"
COL_MONTH = "month"
COL_RECOVERY_PCT = "recovery_pct"  # percentage recovered
COL_DATA_SOURCE = "data_source"    # provenance tag on every output record

# Provenance values
SOURCE_NOSDRA = "NOSDRA"

# Coordinate validation
LAT_MIN, LAT_MAX = 2.0, 14.0  # Nigeria lat bounds
LON_MIN, LON_MAX = 2.5, 15.0  # Nigeria lon bounds

# ── Date formats ───────────────────────────────────────────────────────────
# NOSDRA uses multiple formats; these are the known patterns.
# Order matters — more specific formats first to avoid false positives.
KNOWN_DATE_FORMATS = [
    # ISO 8601 with timezone
    "%Y-%m-%dT%H:%M:%S%z",     # 2025-03-15T14:30:00+0100
    "%Y-%m-%dT%H:%M:%SZ",       # 2025-03-15T14:30:00Z
    "%Y-%m-%dT%H:%M:%S",        # 2025-03-15T14:30:00
    # ISO date
    "%Y-%m-%d",                  # 2025-03-15
    # DD/MM/YYYY (Nigeria convention — before US-style to reduce ambiguity)
    "%d/%m/%Y",                  # 15/03/2025
    # US-style
    "%m/%d/%Y",                  # 03/15/2025
    # DD-MMM-YYYY
    "%d-%b-%Y",                  # 15-Mar-2025
    "%d-%B-%Y",                  # 15-March-2025
    # DD/MMM/YYYY
    "%d/%b/%Y",                  # 15/Mar/2025
    "%d/%B/%Y",                  # 15/March/2025
    # Slash ISO
    "%Y/%m/%d",                  # 2025/03/15
    # With time as HH:MM (no seconds)
    "%Y-%m-%d %H:%M",            # 2025-03-15 14:30
    "%d/%m/%Y %H:%M",            # 15/03/2025 14:30
    # Month name variants
    "%B %d, %Y",                 # March 15, 2025
    "%d %B %Y",                  # 15 March 2025
    "%b %d, %Y",                 # Mar 15, 2025
    "%d %b %Y",                  # 15 Mar 2025
]

# Sentinel strings that indicate no actual date (not parseable)
NULL_DATE_STRINGS = {"na", "n/a", "null", "none", "—", "-", "", "0000-00-00", "99/99/9999"}

OUTPUT_DATE_FORMAT = "%Y-%m-%d"  # ISO 8601 for all outputs

# ── Thresholds ─────────────────────────────────────────────────────────────
MIN_VALID_SPILL_QUANTITY = 0.1        # barrels; below this = data entry error
MAX_SPILL_QUANTITY = 500_000          # plausibility cap
VALID_RECOVERY_PCT_RANGE = (0, 100)   # plausible recovery %

# ── Logging ────────────────────────────────────────────────────────────────
# ── Data-quality scorecard thresholds (src/analysis/quality_scorecard.py) ──
# Fields whose presence defines per-record completeness and the
# worst-year / worst-LGA ranking.
QC_COMPLETENESS_FIELDS = (COL_LATITUDE, COL_DATE, COL_JIV_DATE)
# A JIV (Joint Investigation Visit) more than this many days after the
# incident is flagged as a slow/late investigation.
QC_JIV_LAG_CAP_DAYS = 28
# recovered/spilled ratio at or above this percentage is flagged as
# suspicious — near-total recovery claims are a known reporting artifact.
QC_SUSPICIOUS_RECOVERY_PCT = 99.9
# Volume plausibility window (same bounds the ETL validates against).
QC_VOLUME_PLAUSIBILITY = (MIN_VALID_SPILL_QUANTITY, MAX_SPILL_QUANTITY)

# ── Weekly digest (src/etl/digest.py) ──────────────────────────────────
# Runtime state (seen incident IDs + last run timestamp) lives in
# DATA_PROCESSED and is machine-local — never committed.
DIGEST_STATE_FILENAME = "digest_state.json"
DIGEST_OUTPUT_PREFIX = "digest_"
DIGEST_LOG_FILE = LOGS_DIR / "digest.log"
# Occurrence window for the very first run (before any state exists).
DIGEST_DEFAULT_WINDOW_DAYS = 7
DIGEST_UNKNOWN_LABEL = "(unknown)"

LOG_FILE = LOGS_DIR / "etl_pipeline.log"
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── CRS ────────────────────────────────────────────────────────────────────
INPUT_CRS = "EPSG:4326"       # WGS84 (geographic, lat/lon)
OUTPUT_CRS = "EPSG:26332"     # Nigeria projected CRS (for area/distance calcs)
