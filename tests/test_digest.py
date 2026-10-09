"""
Weekly digest tests — exact section counts and groupings on a crafted
fixture, first-run/second-run behaviour through run(), state seeding,
--since override, and corrupt-state handling.

Fixture ledger (10 records, 9 with usable incident IDs):
  N1: 2026-09-29, Rivers/Ogba/Egbema/Ndoni, NAOC, sab, 100.0 spilled / 10.0 rec
  N2: 2026-10-01, Rivers/Ahoada-West, SPDC, eqf, 50.0 / None
  N3: 2026-10-02, Bayelsa/Southern-Ijaw, Aiteo, sab, 200.0 / 200.0
  N4: 2026-09-28, Rivers/Ogba/Egbema/Ndoni, NAOC, sab, 25.0 / None
  OLD1: 2020-05-05, Delta/Ughelli, NPDC, cor, 75.0 — backfilled historic spill
  NODATE: no date, Rivers/Ogba/Egbema/Ndoni, NAOC, no volumes
  OLD2: 2019-01-01, no state/lga/company → unknown bucket
  SEEN1: 2026-10-02, Rivers/Ahoada-West, SPDC, cor, 30.0 — already seen
  SEEN2: 2020-01-01, Delta/Ughelli, NPDC — already seen
  EMPTY_ID: incident_id "" — invisible to the digest

With seen_ids = {SEEN1, SEEN2} and occurred_since = 2026-09-26:
  newly disclosed = N1, N2, N3, N4, OLD1, NODATE, OLD2        → 7
  newly occurred  = N1, N2, N3, N4, SEEN1                     → 5
  Ogba/Egbema/Ndoni disclosed = 3 (spilled 100+25, recovered 10)
  Ahoada-West occurred = 2 (spilled 50+30)
"""

import json
from datetime import date
from pathlib import Path

import pytest
from digest import _load_state, compute_digest, render_markdown, run

OCCURRED_SINCE = date(2026, 9, 26)
SEEN_IDS = {"SEEN1", "SEEN2"}

RECORDS = [
    dict(incident_id="N1", date="2026-09-29", year=2026, state="Rivers",
         lga="Ogba/Egbema/Ndoni", company="NAOC", cause="sab",
         quantity_spilled=100.0, quantity_recovered=10.0),
    dict(incident_id="N2", date="2026-10-01", year=2026, state="Rivers",
         lga="Ahoada-West", company="SPDC", cause="eqf",
         quantity_spilled=50.0, quantity_recovered=None),
    dict(incident_id="N3", date="2026-10-02", year=2026, state="Bayelsa",
         lga="Southern-Ijaw", company="Aiteo", cause="sab",
         quantity_spilled=200.0, quantity_recovered=200.0),
    dict(incident_id="N4", date="2026-09-28", year=2026, state="Rivers",
         lga="Ogba/Egbema/Ndoni", company="NAOC", cause="sab",
         quantity_spilled=25.0, quantity_recovered=None),
    dict(incident_id="OLD1", date="2020-05-05", year=2020, state="Delta",
         lga="Ughelli", company="NPDC", cause="cor",
         quantity_spilled=75.0, quantity_recovered=None),
    dict(incident_id="NODATE", date=None, year=None, state="Rivers",
         lga="Ogba/Egbema/Ndoni", company="NAOC", cause=None,
         quantity_spilled=None, quantity_recovered=None),
    dict(incident_id="OLD2", date="2019-01-01", year=2019, state="",
         lga="", company="", cause="other:",
         quantity_spilled=5.0, quantity_recovered=None),
    dict(incident_id="SEEN1", date="2026-10-02", year=2026, state="Rivers",
         lga="Ahoada-West", company="SPDC", cause="cor",
         quantity_spilled=30.0, quantity_recovered=None),
    dict(incident_id="SEEN2", date="2020-01-01", year=2020, state="Delta",
         lga="Ughelli", company="NPDC", cause="sab",
         quantity_spilled=None, quantity_recovered=None),
    dict(incident_id="", date="2026-10-01", year=2026, state="Rivers",
         lga="Ahoada-West", company="SPDC", cause="sab",
         quantity_spilled=10.0, quantity_recovered=None),
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
def digest(fixture_file):
    return compute_digest(RECORDS, SEEN_IDS, OCCURRED_SINCE)


# ── Section membership ─────────────────────────────────────────────────────
class TestComputeDigest:
    def test_newly_disclosed_total(self, digest):
        # All but SEEN1/SEEN2 (already seen) and EMPTY_ID (unidentifiable).
        assert digest["disclosed_total"] == 7

    def test_newly_occurred_total(self, digest):
        # N1, N2, N3, N4 in the window; OLD1/NODATE/OLD2 too old or undated;
        # SEEN1 occurred in the window too (occurred ≠ disclosed).
        assert digest["occurred_total"] == 5

    def test_first_run_discloses_everything(self):
        first = compute_digest(RECORDS, set(), OCCURRED_SINCE)
        assert first["disclosed_total"] == 9

    def test_current_ids_exclude_empty(self, digest):
        assert "" not in digest["current_ids"]
        assert digest["current_ids"] == {r["incident_id"] for r in RECORDS} - {""}

    def test_backfill_in_disclosed_only(self, digest):
        # OLD1 (2020) enters via disclosure, not the occurrence window.
        disclosed_lgas = {r["lga"] for r in digest["disclosed_rows"]}
        occurred_lgas = {r["lga"] for r in digest["occurred_rows"]}
        assert "Ughelli" in disclosed_lgas
        assert "Ughelli" not in occurred_lgas

    def test_grouping_by_state_lga(self, digest):
        ogba = next(r for r in digest["disclosed_rows"]
                    if r["lga"] == "Ogba/Egbema/Ndoni")
        assert ogba["state"] == "Rivers"
        assert ogba["incidents"] == 3  # N1, N4, NODATE

    def test_volume_sums_skip_nones(self, digest):
        ogba = next(r for r in digest["disclosed_rows"]
                    if r["lga"] == "Ogba/Egbema/Ndoni")
        assert ogba["spilled_bbl"] == 125.0  # 100 + 25; NODATE contributes nothing
        assert ogba["recovered_bbl"] == 10.0

    def test_top_operators_labelled(self, digest):
        ogba = next(r for r in digest["disclosed_rows"]
                    if r["lga"] == "Ogba/Egbema/Ndoni")
        assert ogba["operators"] == "NAOC (3)"

    def test_unknown_state_bucketed(self, digest):
        unknown = next(r for r in digest["disclosed_rows"] if r["state"] == "(unknown)")
        assert unknown["lga"] == "(unknown)"
        assert unknown["incidents"] == 1  # OLD2

    def test_rows_sorted_by_incidents_desc(self, digest):
        counts = [r["incidents"] for r in digest["disclosed_rows"]]
        assert counts == sorted(counts, reverse=True)


# ── Markdown rendering ─────────────────────────────────────────────────────
class TestRenderMarkdown:
    def test_headers_and_totals(self, digest, fixture_file):
        md = render_markdown(digest, fixture_file.name, "2026-10-03T12:00:00",
                             OCCURRED_SINCE, is_first_run=False)
        assert "# NOSDRA Weekly Digest — What Changed" in md
        assert "## Newly disclosed since last run" in md
        assert "## Newly occurred since last run" in md
        assert "**Total: 7 incidents**" in md
        assert "**Total: 5 incidents**" in md
        assert f"- **Occurrence window:** {OCCURRED_SINCE.isoformat()} →" in md

    def test_table_rows_render(self, digest, fixture_file):
        md = render_markdown(digest, fixture_file.name, "2026-10-03T12:00:00",
                             OCCURRED_SINCE, is_first_run=False)
        assert "| Rivers | Ogba/Egbema/Ndoni | 3 | 125.0 | 10.0 | NAOC (3) |" in md
        assert "| (unknown) | (unknown) | 1 | 5.0 | 0.0 | (unknown) (1) | other: (1) |" in md

    def test_first_run_note(self, digest, fixture_file):
        md = render_markdown(digest, fixture_file.name, "2026-10-03T12:00:00",
                             OCCURRED_SINCE, is_first_run=True)
        assert "First run — the full record is reported as the baseline" in md
        assert "`--seed`" in md

    def test_caveat_present(self, digest, fixture_file):
        md = render_markdown(digest, fixture_file.name, "2026-10-03T12:00:00",
                             OCCURRED_SINCE, is_first_run=False)
        assert "not ground truth" in md
        assert "excluded from the sums" in md

    def test_empty_section_note(self, fixture_file):
        empty = compute_digest([], set(), OCCURRED_SINCE)
        md = render_markdown(empty, fixture_file.name, "2026-10-03T12:00:00",
                             OCCURRED_SINCE, is_first_run=False)
        assert md.count("_None in this window._") == 2


# ── Runner + state ─────────────────────────────────────────────────────────
class TestRunner:
    def test_first_run_writes_md_and_state(self, fixture_file, tmp_path):
        out_dir = tmp_path / "out"
        state_path = tmp_path / "digest_state.json"
        md_path = run(fixture_file, state_path, out_dir)
        assert md_path is not None and md_path.exists()
        assert md_path.name.startswith("digest_")
        md = md_path.read_text(encoding="utf-8")
        assert "First run — the full record is reported as the baseline" in md
        state = _load_state(state_path)
        assert state["last_run_utc"] is not None
        assert len(state["seen_incident_ids"]) == 9
        assert "SEEN1" in state["seen_incident_ids"]
        assert "" not in state["seen_incident_ids"]

    def test_second_run_reports_only_new(self, fixture_file, tmp_path):
        state_path = tmp_path / "digest_state.json"
        out_dir = tmp_path / "out"
        run(fixture_file, state_path, out_dir)

        # A backfilled historic spill enters the record between runs.
        fc = json.loads(fixture_file.read_text(encoding="utf-8"))
        fc["features"].append({"type": "Feature", "geometry": None, "properties": dict(
            incident_id="BACKFILL", date="2021-06-01", year=2021, state="Rivers",
            lga="Gokana", company="SPDC", cause="sab",
            quantity_spilled=40.0, quantity_recovered=None)})
        fixture_file.write_text(json.dumps(fc), encoding="utf-8")

        md_path = run(fixture_file, state_path, out_dir)
        md = md_path.read_text(encoding="utf-8")
        assert "**Total: 1 incidents**" in md
        assert "Everything not present at the previous run, backfills included." in md
        # The window starts at the last run (today) — no fixture date qualifies.
        assert "_None in this window._" in md
        assert len(_load_state(state_path)["seen_incident_ids"]) == 10

    def test_seed_records_state_without_md(self, fixture_file, tmp_path):
        out_dir = tmp_path / "out"
        state_path = tmp_path / "digest_state.json"
        md_path = run(fixture_file, state_path, out_dir, seed=True)
        assert md_path is None
        assert not list(out_dir.glob("digest_*.md"))
        assert len(_load_state(state_path)["seen_incident_ids"]) == 9

    def test_since_override_widens_occurrence_window(self, fixture_file, tmp_path):
        state_path = tmp_path / "digest_state.json"
        out_dir = tmp_path / "out"
        md_path = run(fixture_file, state_path, out_dir, since=date(2018, 1, 1))
        md = md_path.read_text(encoding="utf-8")
        # Everyone with a date from 2018 on: all but NODATE (no date) = 8.
        assert "**Total: 8 incidents**" in md

    def test_no_new_incidents_reports_zero(self, fixture_file, tmp_path):
        state_path = tmp_path / "digest_state.json"
        out_dir = tmp_path / "out"
        run(fixture_file, state_path, out_dir)
        md_path = run(fixture_file, state_path, out_dir)
        md = md_path.read_text(encoding="utf-8")
        assert "**Total: 0 incidents**" in md
        assert md.count("_None in this window._") == 2

    def test_corrupt_state_raises_clear_error(self, fixture_file, tmp_path):
        state_path = tmp_path / "digest_state.json"
        state_path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="corrupt digest state"):
            run(fixture_file, state_path, tmp_path / "out")

    def test_unrecognised_state_raises_clear_error(self, fixture_file, tmp_path):
        state_path = tmp_path / "digest_state.json"
        state_path.write_text('{"something": "else"}', encoding="utf-8")
        with pytest.raises(ValueError, match="unrecognised digest state"):
            run(fixture_file, state_path, tmp_path / "out")
