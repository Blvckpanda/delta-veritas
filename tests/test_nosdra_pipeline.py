"""
NOSDRA ETL pipeline tests.

Covers the three pure cleaning functions (parse_date, validate_coords,
clean_quantity) against every known date format, Excel serials, null
sentinels, coordinate edge cases, and quantity thresholds — then runs the
full pipeline over the 9-record edge-case fixture and asserts its
documented behaviour. Also covers the live-API schema mapping
(map_api_record) and the scripted export fetch (fetch_latest, mocked —
no network in tests).
"""

import gzip
import json
from pathlib import Path
from typing import ClassVar

import config
import pytest
from nosdra_pipeline import (
    clean_quantity,
    fetch_latest,
    map_api_record,
    parse_date,
    run_pipeline,
    transform_feature,
    validate_coords,
)

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
EDGE_CASE_FILE = RAW_DIR / "nosdra_test_edge_cases.json"


# ── parse_date ─────────────────────────────────────────────────────────────
class TestParseDate:
    """Every format in config.KNOWN_DATE_FORMATS must round-trip to ISO."""

    # (raw input, expected ISO date) — one case per configured format,
    # in the same order as KNOWN_DATE_FORMATS, plus the special handlers.
    CASES: ClassVar[list[tuple[str, str | None]]] = [
        ("2025-03-15T14:30:00+0100", "2025-03-15"),
        ("2025-03-15T14:30:00Z", "2025-03-15"),
        ("2025-03-15T14:30:00", "2025-03-15"),
        ("2025-03-15", "2025-03-15"),
        ("15/03/2025", "2025-03-15"),      # DD/MM/YYYY before US-style
        ("03/15/2025", "2025-03-15"),      # US-style (only parses as month=3)
        ("15-Mar-2025", "2025-03-15"),
        ("15-March-2025", "2025-03-15"),
        ("15/Mar/2025", "2025-03-15"),
        ("15/March/2025", "2025-03-15"),
        ("2025/03/15", "2025-03-15"),
        ("2025-03-15 14:30", "2025-03-15"),
        ("15/03/2025 14:30", "2025-03-15"),
        ("March 15, 2025", "2025-03-15"),
        ("15 March 2025", "2025-03-15"),
        ("Mar 15, 2025", "2025-03-15"),
        ("15 Mar 2025", "2025-03-15"),
        # Excel serials (days since 1899-12-30; 45658 = 2025-01-01)
        ("45678", "2025-01-21"),
        ("45000", "2023-03-15"),
        # Null sentinels → None, not an error
        ("N/A", None),
        ("n/a", None),
        ("null", None),
        ("none", None),
        ("—", None),
        ("-", None),
        ("", None),
        ("0000-00-00", None),
        ("99/99/9999", None),
    ]

    @pytest.mark.parametrize(("raw", "expected"), CASES)
    def test_known_inputs(self, raw, expected):
        assert parse_date(raw) == expected

    def test_unparseable_returns_none_and_not_raises(self):
        assert parse_date("not-a-date") is None

    def test_none_input_returns_none(self):
        assert parse_date(None) is None

    def test_dd_mm_beats_mm_dd_for_ambiguous_early_day(self):
        """15/03/2025 must be March 15, not July 3 — Nigeria convention first."""
        assert parse_date("15/03/2025") == "2025-03-15"

    def test_short_digit_strings_are_not_excel_serials(self):
        """'2025' is a year, not an Excel serial — must not be mangled."""
        assert parse_date("2025") is None


# ── validate_coords ───────────────────────────────────────────────────────
class TestValidateCoords:
    """Nigeria bounds from config: lat 2.0-14.0, lon 2.5-15.0."""

    def test_valid_delta_point(self):
        assert validate_coords(4.82, 7.05) == (4.82, 7.05)

    def test_out_of_bounds_latitude(self):
        assert validate_coords(20.0, 7.05) == (None, None)

    def test_out_of_bounds_longitude(self):
        assert validate_coords(4.82, 30.0) == (None, None)

    def test_zero_zero_placeholder(self):
        assert validate_coords(0, 0) == (None, None)

    def test_null_inputs(self):
        assert validate_coords(None, None) == (None, None)

    def test_string_numbers_are_coerced(self):
        assert validate_coords("4.82", "7.05") == (4.82, 7.05)

    def test_non_numeric_strings(self):
        assert validate_coords("abc", "7.05") == (None, None)

    def test_bounds_are_inclusive(self):
        lat_min, lat_max = config.LAT_MIN, config.LAT_MAX
        lon_min, lon_max = config.LON_MIN, config.LON_MAX
        assert validate_coords(lat_min, lon_min) == (lat_min, lon_min)
        assert validate_coords(lat_max, lon_max) == (lat_max, lon_max)


# ── clean_quantity ────────────────────────────────────────────────────────
class TestCleanQuantity:
    """Thresholds from config: min 0.1 bbl, cap 500,000 bbl."""

    def test_valid_volume(self):
        assert clean_quantity(45.5) == 45.5

    def test_negative_volume_rejected(self):
        assert clean_quantity(-5.0) is None

    def test_below_minimum_rejected(self):
        assert clean_quantity(0.05) is None

    def test_at_minimum_accepted(self):
        assert clean_quantity(0.1) == 0.1

    def test_over_cap_rejected(self):
        assert clean_quantity(config.MAX_SPILL_QUANTITY + 1) is None

    def test_at_cap_accepted(self):
        assert clean_quantity(config.MAX_SPILL_QUANTITY) == config.MAX_SPILL_QUANTITY

    def test_string_volume_coerced(self):
        assert clean_quantity("120") == 120.0

    def test_non_numeric_rejected(self):
        assert clean_quantity("lots") is None

    def test_none_rejected(self):
        assert clean_quantity(None) is None

    def test_rounded_to_two_decimals(self):
        assert clean_quantity(45.123456) == 45.12


# ── Full pipeline over the edge-case fixture ──────────────────────────────
class TestEdgeCaseFixture:
    """The 9-record fixture documents real NOSDRA grubbiness; the pipeline
    must handle all of it without raising and produce expected outputs."""

    @pytest.fixture(scope="class")
    def result(self, tmp_path_factory):
        out_dir = tmp_path_factory.mktemp("processed")
        return run_pipeline(EDGE_CASE_FILE, out_dir)

    def test_all_9_records_kept(self, result):
        # Records with missing coords/dates are kept and flagged, not dropped.
        assert len(result["features"]) == 9

    def test_every_record_has_data_source(self, result):
        for feat in result["features"]:
            assert feat["properties"]["data_source"] == "NOSDRA"

    def test_coordinate_summary_matches_documented_behaviour(self, result):
        # Fixture has 1 record with null coords (T5); 8 must be geocoded.
        with_coords = sum(
            1 for f in result["features"] if f["geometry"] is not None
        )
        assert with_coords == 8

    def test_date_summary_matches_documented_behaviour(self, result):
        # T6 is "N/A", T8 is "—" → 7 parseable dates.
        with_dates = sum(
            1 for f in result["features"] if f["properties"]["date"]
        )
        assert with_dates == 7

    def test_excel_serial_date_decoded(self, result):
        t5 = next(
            f for f in result["features"]
            if f["properties"]["incident_id"] == "T5"
        )
        assert t5["properties"]["date"] == "2025-01-21"  # serial 45678
        assert t5["geometry"] is None  # still no coords

    def test_negative_volume_nulled(self, result):
        t9 = next(
            f for f in result["features"]
            if f["properties"]["incident_id"] == "T9"
        )
        assert t9["properties"]["quantity_spilled"] is None

    def test_zero_volume_nulled(self, result):
        t8 = next(
            f for f in result["features"]
            if f["properties"]["incident_id"] == "T8"
        )
        assert t8["properties"]["quantity_spilled"] is None

    def test_recovery_pct_computed_and_capped(self, result):
        t1 = next(
            f for f in result["features"]
            if f["properties"]["incident_id"] == "T1"
        )
        # 32.1 / 45.5 = 70.549…% → rounded to 70.5
        assert t1["properties"]["recovery_pct"] == 70.5

    def test_written_file_is_valid_geojson(self, tmp_path_factory):
        # run_pipeline writes as it runs — verify the artifact round-trips.
        out_dir = tmp_path_factory.mktemp("verify")
        fc = run_pipeline(EDGE_CASE_FILE, out_dir)
        path = next(out_dir.glob("nosdra_clean_*.geojson"))
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["type"] == "FeatureCollection"
        assert len(loaded["features"]) == len(fc["features"])


# ── Live API schema mapping ────────────────────────────────────────────────
class TestApiMapping:
    """map_api_record: the live export's vocabulary → canonical schema."""

    def test_full_api_record_maps_exactly(self):
        raw = {
            "id": "2",
            "status": "confirmed",
            "company": "ADDAX",
            "incidentnumber": "HSE/OBO/0611/101",
            "incidentdate": "2006-11-23",
            "contaminant": "cr",
            "estimatedquantity": "225",
            "sitelocationname": "Subsea Platform (OML123)",
            "spillareahabitat": "of",
            "latitude": "4.82",
            "longitude": "7.05",
            "cause": "sab",
            "jivdate": "2006-12-01",
            "statesaffected": "RI",
            "lga": "Bonny",
            "lastupdatedby": "NOSDRA",   # API-only field → dropped
            "attachments": "x.pdf",      # API-only field → dropped
        }
        mapped = map_api_record(raw)
        assert mapped["incident_id"] == "HSE/OBO/0611/101"
        assert mapped["date"] == "2006-11-23"
        assert mapped["state"] == "Rivers"
        assert mapped["lga"] == "Bonny"
        assert mapped["community"] == "Subsea Platform (OML123)"
        assert mapped["company"] == "ADDAX"
        assert mapped["cause"] == "sab"            # raw codes preserved
        assert mapped["quantity_spilled"] == "225"  # cleaned later by the ETL
        assert mapped["quantity_recovered"] is None
        assert mapped["impact_area"] == "of"
        assert mapped["jiv_date"] == "2006-12-01"
        assert mapped["status"] == "confirmed"
        assert mapped["contaminant"] == "cr"
        assert "lastupdatedby" not in mapped
        assert "attachments" not in mapped

    def test_canonical_records_pass_through_untouched(self):
        canonical = {"incident_id": "X1", "date": "2025-01-01", "state": "Rivers"}
        assert map_api_record(canonical) is canonical

    def test_unknown_vocabulary_passes_through(self):
        weird = {"spill_name": "mystery", "when": "yesterday"}
        assert map_api_record(weird) is weird

    def test_blank_incidentnumber_falls_back_to_api_id(self):
        mapped = map_api_record(
            {"id": "4242", "incidentdate": "2015-06-01", "incidentnumber": ""}
        )
        assert mapped["incident_id"] == "NOSDRA-API-4242"

    def test_missing_incidentnumber_falls_back_to_api_id(self):
        mapped = map_api_record({"id": "77", "incidentdate": "2015-06-01"})
        assert mapped["incident_id"] == "NOSDRA-API-77"

    def test_state_codes_decode(self):
        for code, name in config.NOSDRA_STATE_CODES.items():
            mapped = map_api_record({"incidentdate": "2020-01-01", "statesaffected": code})
            assert mapped["state"] == name

    def test_unknown_state_code_passes_through_raw(self):
        mapped = map_api_record({"incidentdate": "2020-01-01", "statesaffected": "ZZ"})
        assert mapped["state"] == "ZZ"

    def test_lowercase_state_code_still_decodes(self):
        mapped = map_api_record({"incidentdate": "2020-01-01", "statesaffected": "ri"})
        assert mapped["state"] == "Rivers"

    def test_full_name_state_passes_through(self):
        mapped = map_api_record({"incidentdate": "2020-01-01", "statesaffected": "KADUNA"})
        assert mapped["state"] == "KADUNA"

    def test_null_sentinel_state_emptied(self):
        mapped = map_api_record({"incidentdate": "2020-01-01", "statesaffected": "N/A"})
        assert mapped["state"] == ""

    def test_nil_quantity_maps_raw_then_nulls_in_etl(self):
        # "nil" survives mapping untouched; the ETL's clean_quantity nulls it.
        rec = transform_feature(map_api_record(
            {"id": "1", "incidentdate": "2020-01-01", "estimatedquantity": "nil"}
        ))
        assert rec["quantity_spilled"] is None

    def test_typo_quantity_maps_raw_then_nulls_in_etl(self):
        rec = transform_feature(map_api_record(
            {"id": "1", "incidentdate": "2020-01-01", "estimatedquantity": "I.5"}
        ))
        assert rec["quantity_spilled"] is None

    def test_string_coordinates_validate_in_etl(self):
        rec = transform_feature(map_api_record({
            "id": "1", "incidentdate": "2020-01-01",
            "latitude": "4.82", "longitude": "7.05",
        }))
        assert (rec["latitude"], rec["longitude"]) == (4.82, 7.05)

    def test_out_of_bounds_coords_nulled_in_etl(self):
        rec = transform_feature(map_api_record({
            "id": "1", "incidentdate": "2020-01-01",
            "latitude": "51.5", "longitude": "-0.12",
        }))
        assert rec["latitude"] is None and rec["longitude"] is None

    def test_api_record_end_to_end_through_pipeline(self, tmp_path):
        raw = {"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [7.05, 4.82]},
             "properties": {
                 "id": "9", "status": "confirmed", "company": "SHELL",
                 "incidentnumber": "HSE/PHC/2020/001", "incidentdate": "2020-02-15",
                 "cause": "cor", "estimatedquantity": "120.5",
                 "quantityrecovered": "60", "jivdate": "2020-03-01",
                 "sitelocationname": "Okrika", "spillareahabitat": "sw",
                 "statesaffected": "RI", "lga": "Okrika",
                 "latitude": "4.73", "longitude": "7.08",
             }},
        ]}
        path = tmp_path / "api_export.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        fc = run_pipeline(path, tmp_path)
        props = fc["features"][0]["properties"]
        assert props["incident_id"] == "HSE/PHC/2020/001"
        assert props["date"] == "2020-02-15"
        assert props["year"] == 2020
        assert props["state"] == "Rivers"
        assert props["quantity_spilled"] == 120.5
        assert props["quantity_recovered"] == 60.0
        assert props["recovery_pct"] == 49.8  # 60 / 120.5 = 49.79… → 49.8
        assert props["data_source"] == "NOSDRA"
        assert fc["features"][0]["geometry"]["coordinates"] == [7.08, 4.73]


# ── fetch_latest (mocked — no network in tests) ────────────────────────────
class _FakeResponse:
    """Minimal context-manager stand-in for urlopen's return value."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestFetchLatest:
    def test_writes_verbatim_and_returns_count(self, tmp_path, monkeypatch):
        payload = json.dumps([{"id": "1", "incidentdate": "2020-01-01"}]).encode()
        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout: _FakeResponse(payload))
        out = tmp_path / "raw" / "nosdra.json"
        path, count = fetch_latest(out)
        assert path == out and count == 1
        assert json.loads(out.read_text(encoding="utf-8")) == [
            {"id": "1", "incidentdate": "2020-01-01"}
        ]

    def test_gzip_response_is_decompressed(self, tmp_path, monkeypatch):
        """The server gzips regardless of Accept-Encoding; urllib must cope."""
        payload = gzip.compress(json.dumps([{"id": "1", "incidentdate": "2020-01-01"}]).encode())
        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout: _FakeResponse(payload))
        out = tmp_path / "out.json"
        _, count = fetch_latest(out)
        assert count == 1
        assert json.loads(out.read_text(encoding="utf-8")) == [
            {"id": "1", "incidentdate": "2020-01-01"}
        ]

    def test_unexpected_shape_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout: _FakeResponse(b'{"error": "nope"}'))
        with pytest.raises(ValueError, match="unexpected export shape"):
            fetch_latest(tmp_path / "out.json")

    def test_empty_array_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout: _FakeResponse(b"[]"))
        with pytest.raises(ValueError):
            fetch_latest(tmp_path / "out.json")

    def test_uses_config_url_user_agent_and_timeout(self, tmp_path, monkeypatch):
        seen = {}

        def fake_urlopen(req, timeout):
            seen["url"] = req.full_url
            seen["ua"] = req.headers.get("User-agent")
            seen["timeout"] = timeout
            return _FakeResponse(b'[{"id": "1"}]')

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        fetch_latest(tmp_path / "out.json")
        assert seen["url"] == config.NOSDRA_EXPORT_URL
        assert seen["ua"] == config.NOSDRA_FETCH_USER_AGENT
        assert seen["timeout"] == config.NOSDRA_FETCH_TIMEOUT_S
