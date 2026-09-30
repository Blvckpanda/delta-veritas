"""
Load cleaned NOSDRA data into the API database.

Usage:
    python src/api/seed.py                          # loads latest nosdra_clean_*.geojson
    python src/api/seed.py --file data/processed/nosdra_clean_20260730_*.geojson
"""

import argparse
import asyncio
import contextlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.api.database import async_session_factory, init_db
from src.api.models.spill import SpillIncident


async def seed_from_geojson(filepath: Path):
    """Load features from a cleaned NOSDRA GeoJSON into the database."""
    with open(filepath) as f:
        fc = json.load(f)

    features = fc.get("features", [])
    print(f"Loading {len(features)} features from {filepath.name}")

    async with async_session_factory() as session:
        count = 0
        for feat in features:
            props = feat.get("properties", {})
            if not props.get("incident_id"):
                continue

            # Convert date strings to date objects
            raw_date = props.get("date")
            parsed_date = None
            if raw_date:
                with contextlib.suppress(ValueError, TypeError):
                    parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()

            raw_jiv = props.get("jiv_date")
            jiv = None
            if raw_jiv:
                with contextlib.suppress(ValueError, TypeError):
                    jiv = datetime.strptime(raw_jiv, "%Y-%m-%d").date()

            incident = SpillIncident(
                incident_id=props.get("incident_id", ""),
                date=parsed_date,
                year=props.get("year"),
                month=props.get("month"),
                state=props.get("state"),
                lga=props.get("lga"),
                community=props.get("community"),
                company=props.get("company"),
                cause=props.get("cause"),
                spill_type=props.get("spill_type"),
                quantity_spilled=props.get("quantity_spilled"),
                quantity_recovered=props.get("quantity_recovered"),
                recovery_pct=props.get("recovery_pct"),
                impact_area=props.get("impact_area"),
                jiv_date=jiv,
                contaminant=props.get("contaminant"),
                status=props.get("status"),
                latitude=props.get("latitude"),
                longitude=props.get("longitude"),
            )
            session.add(incident)
            count += 1

        await session.commit()
        print(f"Seeded {count} records into database")


async def main():
    parser = argparse.ArgumentParser(description="Seed API database")
    parser.add_argument(
        "--file", "-f",
        type=Path,
        help="Path to cleaned GeoJSON file (default: latest in data/processed/)",
    )
    args = parser.parse_args()

    await init_db()

    if args.file:
        filepath = args.file
    else:
        processed_dir = Path("data/processed")
        candidates = sorted(processed_dir.glob("nosdra_clean_*.geojson"))
        if not candidates:
            print("No cleaned GeoJSON files found in data/processed/")
            print("Run src/etl/nosdra_pipeline.py first")
            return
        filepath = candidates[-1]

    await seed_from_geojson(filepath)


if __name__ == "__main__":
    asyncio.run(main())
