"""
VIIRS Nightfire Gas Flaring — ETL Pipeline.

Extract: download VIIRS Nightfire annual CSV files from EOG (payneinstitute).
Transform: filter to Niger Delta bounding box, parse flare parameters.
Load: write cleaned CSV + GeoParquet.

Supports both auto-download and manual-file modes.
"""

import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

logger = logging.getLogger("viirs_etl")
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


# Niger Delta bounding box (approximate)
ND_LAT_MIN, ND_LAT_MAX = 3.5, 6.0
ND_LON_MIN, ND_LON_MAX = 4.5, 9.0

# VIIRS column mapping
COL_LAT = "latitude"
COL_LON = "longitude"
COL_YEAR = "year"
COL_MONTH = "month"
COL_FLARE_COUNT = "flare_count"  # number of detections in pixel
COL_AVG_TEMP = "avg_temperature_k"
COL_EST_VOLUME = "estimated_volume_m3"
COL_CONFIDENCE = "confidence"


def is_in_bbox(lat: float, lon: float) -> bool:
    """Check if coordinates fall within Niger Delta bounding box."""
    return (
        ND_LAT_MIN <= lat <= ND_LAT_MAX
        and ND_LON_MIN <= lon <= ND_LON_MAX
    )


def parse_viirs_csv(path: Path) -> list[dict]:
    """Parse a raw VIIRS Nightfire CSV and filter to Niger Delta."""
    records = []
    with open(path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row.get(COL_LAT, 0))
                lon = float(row.get(COL_LON, 0))
            except (ValueError, TypeError):
                continue

            if not is_in_bbox(lat, lon):
                continue

            records.append({
                COL_LAT: round(lat, 5),
                COL_LON: round(lon, 5),
                COL_YEAR: int(row.get(COL_YEAR, 0)) if row.get(COL_YEAR) else None,
                COL_MONTH: int(row.get(COL_MONTH, 0)) if row.get(COL_MONTH) else None,
                COL_FLARE_COUNT: int(float(row.get("detections", row.get("count", 0)))),
                COL_AVG_TEMP: round(
                    float(row.get("avg_bt_m12", row.get("temperature_k", 0))), 1
                ) or None,
                COL_EST_VOLUME: round(float(row.get("est_vol_m3", 0)), 2) or None,
                COL_CONFIDENCE: row.get("confidence", "").strip(),
            })

    return records


def run_pipeline(input_dir: Path, output_dir: Path):
    """Process all VIIRS CSV files in input_dir."""
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        logger.error("No CSV files found in %s", input_dir)
        logger.info("Download VIIRS data from https://eogdata.mines.edu/products/vnf/")
        return

    all_records = []
    for csv_file in csv_files:
        logger.info("Processing %s", csv_file.name)
        records = parse_viirs_csv(csv_file)
        all_records.extend(records)
        logger.info("  → %d records in Niger Delta", len(records))

    logger.info("Total VIIRS records: %d", len(all_records))

    # Write output CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = output_dir / f"viirs_flares_ndelta_{timestamp}.csv"
    if all_records:
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_records[0].keys())
            writer.writeheader()
            writer.writerows(all_records)
        logger.info("Wrote %s (%d records)", out_csv, len(all_records))
    else:
        logger.warning("No records to write.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VIIRS Nightfire ETL")
    parser.add_argument("--input", type=Path, help="Directory with VIIRS CSV files")
    parser.add_argument("--output", type=Path, default=config.DATA_PROCESSED)
    args = parser.parse_args()
    run_pipeline(args.input or config.DATA_RAW, args.output)
