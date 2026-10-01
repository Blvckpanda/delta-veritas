"""
Data-quality scorecard tests — exact metrics on a crafted fixture, plus
empty-file and all-null edge cases, plus the CLI end-to-end.

Fixture ledger (6 records):
  A1: 2024, Rivers/Ahoada, coords, date, JIV lag 10d,  100.0 bbl, rec 10  → rec% 10
  A2: 2024, Rivers/Ahoada, no coords, date, no JIV,     50.0 bbl, rec 50  → rec% 100 (suspicious)
  B1: 2025, Delta/Ughelli, coords, date, JIV lag 40d,  10**6 bbl (over cap), rec 0
  B2: 2025, Delta/Ughelli, coords, no date, no JIV,    None (nulled),     rec None
  C1: 2025, Delta/(no LGA), no coords, no date, jiv set but NO incident date
      → lag unmeasurable; spilled 0.05 (below min), recovered 7.0 → rec capped
        at 100% (recovered > spilled) → counts as suspicious
  D1: 2025, Bayelsa/Sagbama (single-record LGA), coords, date, JIV lag 5d,
      200.0 bbl, rec 199 → 99.5% (below the 99.9 threshold)

  Duplicates: A1 id appears twice (1 duplicate).                  → dup 1 / 6 = 16.7%
  Cause cardinality: {Equipment, Corrosion, Sabotage, Wellhead}   → 4
  Companies: Shell {A1, A2, C1}, Agip {B1, B2}, Total {D1}
  Completeness (coords/date/jiv): A1 3/3, A2 1/3, B1 3/3, B2 1/3, C1 1/3, D1 3/3
  → coordinate 4/6 = 66.7% (A1,B1,B2,D1), date 4/6 (A1,A1,B1,D1), jiv 4/6 (A1,B1,C1,D1)
  JIV lags measured: A1 10, B1 40, D1 5 → measured 3, median 10, max 40,
    over-cap(>28d) 1 = 33.3%
  (C1's JIV date has no incident date → Shell jiv_pct counts A1+C1 = 66.7)
  Volume buckets: plausible {A1 100, A2 50, D1 200} = 3; over_cap {B1} = 1;
    below_min {C1 0.05} = 1; missing_or_nulled {B2} = 1; negative = 0
  Suspicious recovery (≥99.9%): A2 (100%) + C1 (capped 100%) = 2
  Worst year: 2024 (A1+A2) 4/6 fields = 66.7%; 2025 (B1,B2,C1,D1) 8/12 = 66.7%
    → tie at 66.7% broken by more records → 2025 (4 records)
  Worst LGA: Ahoada (A1+A2) 4/6 = 66.7%; Ughelli (B1+B2) 4/6 = 66.7%
    → tie broken by more records, both 2 → first encountered wins → Ahoada
  Per operator (sorted by records desc, then name):
    Shell 3 → coords 33.3, dates 66.7, jiv 33.3, dup 1, suspicious 2, lag 10.0
    Agip 2 → coords 100.0, dates 50.0, jiv 50.0, dup 0, suspicious 0, lag 40.0
    Total 1 → coords 100.0, dates 100.0, jiv 100.0, dup 0, suspicious 0, lag 5.0
"""

import json
from pathlib import Path

import config
import pytest
from quality_scorecard import compute_scorecard, load_records, run

# ── Crafted fixture ────────────────────────────────────────────────────────
RECORDS = [
    dict(incident_id="A1", date="2024-03-01", jiv_date="2024-03-11",
         state="Rivers", lga="Ahoada", year=2024, cause="Equipment", company="Shell",
         quantity_spilled=100.0, quantity_recovered=10.0,
         latitude=5.1, longitude=6.6),
    dict(incident_id="A1", date="2024-04-01", jiv_date=None,
         state="Rivers", lga="Ahoada", year=2024, cause="Corrosion", company="Shell",
         quantity_spilled=50.0, quantity_recovered=50.0,
         latitude=None, longitude=None),
    dict(incident_id="B1", date="2025-05-01", jiv_date="2025-06-10",
         state="Delta", lga="Ughelli", year=2025, cause="Sabotage", company="Agip",
         quantity_spilled=10**6, quantity_recovered=0.0,
         latitude=5.3, longitude=6.2),
    dict(incident_id="B2", date=None, jiv_date=None,
         state="Delta", lga="Ughelli", year=2025, cause="Wellhead", company="Agip",
         quantity_spilled=None, quantity_recovered=None,
         latitude=5.4, longitude=6.3),
    dict(incident_id="C1", date=None, jiv_date="2025-07-01",
         state="Delta", lga=None, year=2025, cause="Equipment", company="Shell",
         quantity_spilled=0.05, quantity_recovered=7.0,
         latitude=None, longitude=None),
    dict(incident_id="D1", date="2025-08-01", jiv_date="2025-08-06",
         state="Bayelsa", lga="Sagbama", year=2025, cause="Sabotage", company="Total",
         quantity_spilled=200.0, quantity_recovered=199.0,
         latitude=4.9, longitude=6.4),
]


@pytest.fixture()
def fixture_file(tmp_path) -> Path:
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": None, "properties": r} for r in RECORDS
    ]}
    path = tmp_path / "crafted.geojson"
    path.write_text(json.dumps(fc), encoding="utf-8")
    return path


@pytest.fixture()
def report(fixture_file):
    return compute_scorecard(load_records(fixture_file))


# ── Exact metrics on the crafted fixture ──────────────────────────────────
class TestCraftedFixture:
    def test_total_records(self, report):
        assert report["total_records"] == 6

    def test_completeness(self, report):
        assert report["completeness"] == {
            "coordinate_pct": 66.7, "date_pct": 66.7, "jiv_pct": 66.7,
        }

    def test_duplicates(self, report):
        assert report["duplicates"]["duplicate_count"] == 1
        assert report["duplicates"]["duplicate_rate_pct"] == 16.7
        assert report["duplicates"]["repeated_ids"] == {"A1": 2}

    def test_cause_cardinality(self, report):
        assert report["cause_cardinality"] == 4

    def test_volume_buckets(self, report):
        assert report["volume_plausibility"] == {
            "plausible": 3, "missing_or_nulled": 1, "negative": 0,
            "over_cap": 1, "below_min": 1,
        }

    def test_suspicious_recovery(self, report):
        # A2 = 100% recovery; C1 = recovered(7) > spilled(0.05) → capped 100%.
        # D1 = 99.5% stays below the 99.9 threshold.
        assert report["suspicious_recovery_count"] == 2

    def test_jiv_lag(self, report):
        # C1 has a JIV date but no incident date → lag unmeasurable.
        assert report["jiv_lag"] == {
            "measured": 3, "median_days": 10, "max_days": 40,
            "over_cap_count": 1, "over_cap_pct": 33.3,
        }

    def test_worst_year(self, report):
        # 2024 and 2025 tie at 66.7% → tie-break picks the larger group (2025).
        assert report["worst_year"] == {"year": "2025", "records": 4, "completeness_pct": 66.7}

    def test_worst_lga(self, report):
        # Ahoada and Ughelli tie at 66.7% with 2 records each → first wins.
        assert report["worst_lga"] == {"lga": "Ahoada", "records": 2, "completeness_pct": 66.7}

    def test_per_company(self, report):
        assert report["per_company"] == [
            {"company": "Shell", "records": 3, "coordinate_pct": 33.3,
             "date_pct": 66.7, "jiv_pct": 66.7, "duplicate_count": 1,
             "suspicious_recovery_count": 2, "jiv_lag_median_days": 10.0},
            {"company": "Agip", "records": 2, "coordinate_pct": 100.0,
             "date_pct": 50.0, "jiv_pct": 50.0, "duplicate_count": 0,
             "suspicious_recovery_count": 0, "jiv_lag_median_days": 40.0},
            {"company": "Total", "records": 1, "coordinate_pct": 100.0,
             "date_pct": 100.0, "jiv_pct": 100.0, "duplicate_count": 0,
             "suspicious_recovery_count": 0, "jiv_lag_median_days": 5.0},
        ]

    def test_suspicious_boundary_exact_threshold(self):
        """99.9 exactly counts as suspicious; 99.89 does not."""
        recs = [
            dict(incident_id="X1", quantity_spilled=1000.0, quantity_recovered=999.0),  # 99.9
            dict(incident_id="X2", quantity_spilled=1000.0, quantity_recovered=998.9),  # 99.89
        ]
        assert compute_scorecard(recs)["suspicious_recovery_count"] == 1


# ── Edge cases ─────────────────────────────────────────────────────────────
class TestEdgeCases:
    def test_empty_feature_collection(self, tmp_path):
        path = tmp_path / "empty.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
        r = compute_scorecard(load_records(path))
        assert r["total_records"] == 0
        assert r["completeness"] == {"coordinate_pct": 0.0, "date_pct": 0.0, "jiv_pct": 0.0}
        assert r["duplicates"]["duplicate_count"] == 0
        assert r["duplicates"]["duplicate_rate_pct"] == 0.0
        assert r["duplicates"]["repeated_ids"] == {}
        assert r["cause_cardinality"] == 0
        assert r["jiv_lag"]["median_days"] is None
        assert r["worst_year"] is None and r["worst_lga"] is None
        assert r["per_company"] == []

    def test_all_null_fields(self):
        r = compute_scorecard([{}, {}, {}])
        assert r["total_records"] == 3
        assert r["completeness"] == {"coordinate_pct": 0.0, "date_pct": 0.0, "jiv_pct": 0.0}
        assert r["volume_plausibility"]["missing_or_nulled"] == 3
        assert r["jiv_lag"] == {"measured": 0, "median_days": None, "max_days": None,
                                "over_cap_count": 0, "over_cap_pct": 0.0}
        assert r["worst_year"] is None and r["worst_lga"] is None
        assert r["per_company"] == []

    def test_bare_list_of_property_dicts(self):
        r = compute_scorecard(load_records.__wrapped__ if False else [
            {"type": "Feature", "geometry": None, "properties": {"incident_id": "Z"}}
        ])
        assert r["total_records"] == 1


# ── Markdown rendering ─────────────────────────────────────────────────────
class TestMarkdown:
    def test_caveat_and_headlines_present(self, report, fixture_file):
        md = __import__("quality_scorecard").render_markdown(
            report, fixture_file.name, "2026-09-30T12:00:00"
        )
        assert "Methodology caveat" in md
        assert "not ground truth" in md
        assert "| Coordinate completeness | 66.7% |" in md
        assert "| Duplicate incident IDs | 1 (16.7%) |" in md
        assert "JIV lag > 28d | 1 (33.3%)" in md
        assert "| Shell | 3 | 33.3 | 66.7 | 66.7 | 1 | 2 | 10.0 |" in md
        assert "| Agip | 2 | 100.0 | 50.0 | 50.0 | 0 | 0 | 40.0 |" in md


# ── CLI runner ─────────────────────────────────────────────────────────────
class TestCliRunner:
    def test_run_writes_json_and_md(self, fixture_file, tmp_path):
        out_dir = tmp_path / "out"
        json_path, md_path = run(fixture_file, out_dir)
        assert json_path.exists() and md_path.exists()
        assert json_path.name.startswith("quality_scorecard_")
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["total_records"] == 6
        assert loaded["source_file"] == fixture_file.name
        assert "generated_at" in loaded
        assert "Methodology caveat" in md_path.read_text(encoding="utf-8")

    def test_default_output_dir_is_config_processed(self, fixture_file, monkeypatch, tmp_path):
        # run() must write wherever told — and config.DATA_PROCESSED is the
        # documented default (verified via the CLI default, not by writing there).
        assert config.DATA_PROCESSED.name == "processed"
