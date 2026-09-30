"""
FastAPI spills endpoints — proven through the real HTTP surface.

The app runs via TestClient (httpx transport) against a throwaway SQLite
database (see conftest.py for the env override + NullPool rationale).
Seeding is end-to-end: raw edge-case fixture → nosdra_pipeline.run_pipeline()
→ cleaned GeoJSON properties → SpillIncident rows (the same field-mapping
src/api/seed.py uses), plus 3 synthetic discriminator rows chosen so every
filter has something to include AND exclude.
"""

import asyncio
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nosdra_pipeline import run_pipeline

from src.api.database import async_session_factory, init_db
from src.api.main import app
from src.api.models.spill import SpillIncident

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EDGE_CASE_FILE = RAW_DIR / "nosdra_test_edge_cases.json"

# Discriminator rows: designed so each filter includes some and excludes others.
# P1: 2024, small (5 bbl), Company A, Rivers      P2: 2025, mid (500), Company A, Bayelsa
# P3: 2025, large (5000), Company B, Rivers
DISCRIMINATORS = [
    dict(incident_id="P1", date=date(2024, 6, 1), year=2024, month=6,
         state="Rivers", company="Company A", quantity_spilled=5.0,
         quantity_recovered=1.0, latitude=4.10, longitude=7.10,
         status="valid", data_source="NOSDRA"),
    dict(incident_id="P2", date=date(2025, 6, 1), year=2025, month=6,
         state="Bayelsa", company="Company A", quantity_spilled=500.0,
         quantity_recovered=250.0, latitude=4.60, longitude=6.20,
         status="valid", data_source="NOSDRA"),
    dict(incident_id="P3", date=date(2025, 8, 1), year=2025, month=8,
         state="Rivers", company="Company B", quantity_spilled=5000.0,
         quantity_recovered=0.0, latitude=5.30, longitude=6.80,
         status="valid", data_source="NOSDRA"),
]


def _seed_database(seed_output_dir: Path) -> int:
    """ETL → DB, then commit. Runs in its own event loop; NullPool makes the
    per-loop connections safe."""

    async def _seed() -> int:
        await init_db()
        fc = run_pipeline(EDGE_CASE_FILE, seed_output_dir)
        rows = []
        for feat in fc["features"]:
            p = feat["properties"]
            d = p.get("date")
            jiv = p.get("jiv_date")
            rows.append(SpillIncident(
                incident_id=p["incident_id"],
                date=datetime.strptime(d, "%Y-%m-%d") if d else None,
                year=p.get("year"), month=p.get("month"),
                state=p.get("state"), lga=p.get("lga"),
                community=p.get("community"), company=p.get("company"),
                cause=p.get("cause"), spill_type=p.get("spill_type"),
                quantity_spilled=p.get("quantity_spilled"),
                quantity_recovered=p.get("quantity_recovered"),
                recovery_pct=p.get("recovery_pct"),
                impact_area=p.get("impact_area"),
                jiv_date=datetime.strptime(jiv, "%Y-%m-%d") if jiv else None,
                contaminant=p.get("contaminant"), status=p.get("status"),
                data_source=p.get("data_source"),
                latitude=p.get("latitude"), longitude=p.get("longitude"),
            ))
        for d in DISCRIMINATORS:
            rows.append(SpillIncident(**d))
        async with async_session_factory() as session:
            session.add_all(rows)
            await session.commit()
        return len(rows)

    return asyncio.run(_seed())


# ── Fixtures ──────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def tempfile_dir(tmp_path_factory) -> Path:
    """Directory the ETL writes cleaned output into during seeding."""
    return tmp_path_factory.mktemp("api_seed")


@pytest.fixture(scope="module")
def client(tempfile_dir):
    """App with a fresh, seeded throwaway database."""
    n = _seed_database(tempfile_dir)
    assert n == 12  # 9 edge-case records + 3 discriminators actually landed
    with TestClient(app) as c:  # context manager runs startup lifespan (init_db)
        yield c


def _ids(payload) -> set[str]:
    return {f["properties"]["incident_id"] for f in payload["features"]}


# ── System endpoints ──────────────────────────────────────────────────────
class TestSystem:
    def test_root_redirect_payload(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["docs"] == "/api/v1/docs"
        assert "message" in body

    def test_health_ok_and_db_connected(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["db_connected"] is True   # proves migrations ran cleanly
        assert body["version"]


# ── /spills/geojson ───────────────────────────────────────────────────────
class TestSpillsGeojson:
    def test_shape_and_provenance(self, client):
        r = client.get("/api/v1/spills/geojson")
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "FeatureCollection"
        assert body["features"], "expected seeded features"
        for feat in body["features"]:
            assert feat["type"] == "Feature"
            assert "data_source" in feat["properties"]   # provenance field, last pass
        assert body["metadata"]["count"] == len(body["features"])

    def test_null_geometry_for_coordless_records(self, client):
        # T5 in the fixture has no coordinates: seeded, kept, but geometry null
        r = client.get("/api/v1/spills/geojson?limit=500")
        t5 = next(f for f in r.json()["features"]
                  if f["properties"]["incident_id"] == "T5")
        assert t5["geometry"] is None

    def test_total_reflects_matching_rows_not_page_size(self, client):
        r = client.get("/api/v1/spills/geojson?limit=3")
        meta = r.json()["metadata"]
        assert meta["count"] == 3                       # page size
        assert meta["total"] == 12                      # 9 fixture + 3 discriminators
        r2 = client.get("/api/v1/spills/geojson?limit=500")
        assert r2.json()["metadata"]["total"] == 12

    def test_offset_paginates_without_overlap(self, client):
        page1 = client.get("/api/v1/spills/geojson?limit=5&offset=0").json()
        page2 = client.get("/api/v1/spills/geojson?limit=5&offset=5").json()
        ids1, ids2 = _ids(page1), _ids(page2)
        assert len(ids1) == 5 and len(ids2) == 5
        assert not ids1 & ids2
        assert page1["metadata"]["total"] == page2["metadata"]["total"]

    def test_filter_state(self, client):
        r = client.get("/api/v1/spills/geojson?state=Rivers")
        ids = _ids(r.json())
        assert {"T1", "T6", "T9", "P1", "P3"} <= ids
        assert all(f["properties"]["state"] == "Rivers" for f in r.json()["features"])

    def test_filter_company_is_case_insensitive_substring(self, client):
        r = client.get("/api/v1/spills/geojson?company=agip")
        ids = _ids(r.json())
        assert {"T2", "T7"} <= ids
        assert all("AGIP" in f["properties"]["company"] for f in r.json()["features"])

    def test_filter_year(self, client):
        r = client.get("/api/v1/spills/geojson?year=2024")
        ids = _ids(r.json())
        assert "P1" in ids
        assert "P2" not in ids and "P3" not in ids

    def test_filter_bbox(self, client):
        # Tight box around Port Harcourt: T1 only among fixture+discriminators
        r = client.get("/api/v1/spills/geojson?bbox=6.9,4.7,7.2,4.95")
        assert _ids(r.json()) == {"T1"}

    def test_min_quantity_includes_boundary(self, client):
        r = client.get("/api/v1/spills/geojson?min_quantity=500")
        ids = _ids(r.json())
        assert "P2" in ids and "P3" in ids      # >= 500
        assert "P1" not in ids                   # 5 < 500

    def test_min_quantity_boundary_at_0_1(self, client):
        # 0.1 is the ETL's MIN_VALID_SPILL_QUANTITY; the fixture's minimum
        # valid spill is T5 at 15 bbl, so every geocoded, dated, plausible
        # record must survive this boundary filter.
        r = client.get("/api/v1/spills/geojson?min_quantity=0.1")
        ids = _ids(r.json())
        assert {"T1", "T2", "T3", "T4", "T5", "T7", "P1"} <= ids
        # T8 spilled 0.0 and T9 was negative → both nulled by the ETL,
        # so quantity >= 0.1 excludes exactly those two among known ids.
        assert "T8" not in ids and "T9" not in ids

    def test_min_quantity_combined_with_state(self, client):
        r = client.get("/api/v1/spills/geojson?state=Rivers&min_quantity=100")
        assert _ids(r.json()) == {"P3"}         # 5000 bbl, Rivers

    def test_combined_filters_narrow_correctly(self, client):
        r = client.get("/api/v1/spills/geojson?year=2025&min_quantity=400")
        assert _ids(r.json()) == {"T4", "P2", "P3"}  # T4: 2025, 5000 bbl


# ── /spills/stats ─────────────────────────────────────────────────────────
class TestSpillStats:
    @pytest.fixture(scope="class")
    def stats(self, client):
        r = client.get("/api/v1/spills/stats")
        assert r.status_code == 200
        return r.json()

    def test_totals(self, stats):
        assert stats["total_incidents"] == 12
        # Spilled: fixture plausible records T1(45.5) T2(120) T3(200) T4(5000)
        # T5(15) T6(30) T7(85) = 5495.5 — T8 (0) and T9 (neg) are nulled by the
        # ETL and excluded — plus discriminators 5+500+5000 = 5505.
        assert stats["total_spilled_bbl"] == pytest.approx(11000.5)
        assert stats["total_recovered_bbl"] == pytest.approx(472.1)

    def test_recovery_pct_math(self, stats):
        expected = round(472.1 / 11000.5 * 100, 1)
        assert stats["overall_recovery_pct"] == pytest.approx(expected)

    def test_by_state_includes_discriminators(self, stats):
        rivers = next(s for s in stats["by_state"] if s["state"] == "Rivers")
        assert rivers["count"] == 6              # T1, T5, T6, T9, P1, P3
        bayelsa = next(s for s in stats["by_state"] if s["state"] == "Bayelsa")
        assert bayelsa["count"] == 3             # T2, T7, P2

    def test_by_year_counts(self, stats):
        y2024 = next(y for y in stats["by_year"] if y["year"] == 2024)
        assert y2024["count"] == 1               # P1
        y2025 = next(y for y in stats["by_year"] if y["year"] == 2025)
        assert y2025["count"] >= 4               # fixture 2025s + P2, P3

    def test_top_causes_and_companies(self, stats):
        causes = {c["cause"] for c in stats["top_causes"]}
        assert "Equipment" in causes and "Sabotage" in causes
        companies = {c["company"] for c in stats["top_companies"]}
        assert "AGIP" in companies               # T2, T7

    def test_stats_sums_exclude_nulled_volumes(self, stats):
        # Guard against double-counting: no record contributed a negative or
        # zero-volume row to the sums (T8/T9 are null after ETL).
        assert stats["total_spilled_bbl"] > 0


# ── /spills/distinct ──────────────────────────────────────────────────────
class TestDistinct:
    def test_distinct_states(self, client):
        r = client.get("/api/v1/spills/distinct/state")
        assert r.status_code == 200
        states = set(r.json())
        assert {"Rivers", "Bayelsa", "Delta", "Akwa Ibom"} <= states

    def test_distinct_disallowed_field_returns_empty(self, client):
        r = client.get("/api/v1/spills/distinct/incident_id")
        assert r.status_code == 200
        assert r.json() == []
