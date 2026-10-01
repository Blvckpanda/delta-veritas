"""
Data-Quality Scorecard — independent audit of the NOSDRA spill record.

Reads a spill dataset (cleaned pipeline output or raw export), computes
per-dataset quality metrics, and writes:

  data/processed/quality_scorecard_<ts>.json  — machine-readable report
  data/processed/quality_scorecard_<ts>.md    — human-readable report

METHODOLOGY CAVEAT (also rendered into every .md output): these metrics
audit the *record* — what NOSDRA and operators chose to report — not the
ground truth. A 100% complete dataset would mean only that every field is
filled, not that every spill was counted or measured honestly. Known
reporting biases (undetected spills, disputed JIV volumes, company-vs-
regulator discrepancies) are invisible to any record-level audit.

Usage:
    python src/analysis/quality_scorecard.py
    python src/analysis/quality_scorecard.py --input data/processed/nosdra_clean_X.geojson
    python src/analysis/quality_scorecard.py --input data/raw/nosdra.json \
        --output-dir data/processed
"""

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))
import config


# ── Loading ────────────────────────────────────────────────────────────────
def load_records(path: Path) -> list[dict]:
    """Load a GeoJSON file and return the list of feature properties.

    Accepts a FeatureCollection dict, a bare list of features, or a bare
    list of property dicts. Features with null geometry are kept — their
    properties still carry reportable (null) fields.
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        feats = data
    elif isinstance(data, dict):
        feats = data.get("features", [])
    else:
        return []

    records = []
    for feat in feats:
        if isinstance(feat, dict) and "properties" in feat:
            records.append(feat.get("properties") or {})
        elif isinstance(feat, dict):
            records.append(feat)
    return records


# ── Per-record predicates (pure) ───────────────────────────────────────────
def _has_coords(rec: dict) -> bool:
    """True when the record carries non-null latitude AND longitude."""
    return rec.get(config.COL_LATITUDE) is not None and rec.get(config.COL_LONGITUDE) is not None


def _has_date(rec: dict) -> bool:
    """True when the record carries a parsed ISO date string."""
    return bool(rec.get(config.COL_DATE))


def _has_jiv(rec: dict) -> bool:
    """True when the record carries a parsed JIV date string."""
    return bool(rec.get(config.COL_JIV_DATE))


def _iso(rec: dict, key: str) -> date | None:
    """Parse an ISO date string (YYYY-MM-DD) from a property, else None."""
    raw = rec.get(key)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), config.OUTPUT_DATE_FORMAT).date()
    except ValueError:
        return None


def _recovery_pct(rec: dict) -> float | None:
    """Effective recovery percentage: derived column if present, else
    computed from spilled/recovered. None when not computable."""
    if rec.get(config.COL_RECOVERY_PCT) is not None:
        return float(rec[config.COL_RECOVERY_PCT])
    spilled, recovered = rec.get(config.COL_QTY_SPILLED), rec.get(config.COL_QTY_RECOVERED)
    if spilled and recovered is not None and spilled > 0:
        return min(recovered / spilled * 100, 100.0)
    return None


def _completeness(rec: dict) -> float:
    """Fraction (0–1) of the configured completeness fields present."""
    checks = {
        config.COL_LATITUDE: _has_coords,
        config.COL_DATE: _has_date,
        config.COL_JIV_DATE: _has_jiv,
    }
    present = sum(1 for field in config.QC_COMPLETENESS_FIELDS if checks[field](rec))
    return present / len(config.QC_COMPLETENESS_FIELDS)


# ── Metric groups (pure) ───────────────────────────────────────────────────
def _completeness_metrics(records: list[dict]) -> dict:
    """Coordinate / date / JIV completeness percentages."""
    total = len(records)
    pct = lambda n: round(n / total * 100, 1) if total else 0.0  # noqa: E731
    return {
        "coordinate_pct": pct(sum(1 for r in records if _has_coords(r))),
        "date_pct": pct(sum(1 for r in records if _has_date(r))),
        "jiv_pct": pct(sum(1 for r in records if _has_jiv(r))),
    }


def _duplicate_metrics(records: list[dict]) -> dict:
    """Duplicates = extra records sharing a non-empty incident_id."""
    ids = [str(r.get(config.COL_INCIDENT_ID) or "").strip() for r in records]
    counts = Counter(i for i in ids if i)
    dup_count = sum(c - 1 for c in counts.values() if c > 1)
    rate = round(dup_count / len(records) * 100, 1) if records else 0.0
    return {
        "duplicate_count": dup_count,
        "duplicate_rate_pct": rate,
        "repeated_ids": {i: c for i, c in sorted(counts.items()) if c > 1},
    }


def _volume_metrics(records: list[dict]) -> dict:
    """Volume plausibility against config.QC_VOLUME_PLAUSIBILITY.

    On cleaned pipeline output the implausible buckets are expected to be
    zero (the ETL nulls them) — non-zero counts there mean the input was
    raw or the cleaning regressed. `missing_or_nulled` covers both absent
    and cleaned-away values.
    """
    lo, hi = config.QC_VOLUME_PLAUSIBILITY
    buckets = {"negative": 0, "over_cap": 0, "below_min": 0, "missing_or_nulled": 0, "plausible": 0}
    for r in records:
        qty = r.get(config.COL_QTY_SPILLED)
        if not isinstance(qty, (int, float)):
            buckets["missing_or_nulled"] += 1
        elif qty < 0:
            buckets["negative"] += 1
        elif qty > hi:
            buckets["over_cap"] += 1
        elif qty < lo:
            buckets["below_min"] += 1
        else:
            buckets["plausible"] += 1
    return buckets


def _suspicious_recovery(records: list[dict]) -> int:
    """Records claiming >= QC_SUSPICIOUS_RECOVERY_PCT recovery."""
    return sum(
        1 for r in records
        if (p := _recovery_pct(r)) is not None and p >= config.QC_SUSPICIOUS_RECOVERY_PCT
    )


def _jiv_lag_metrics(records: list[dict]) -> dict:
    """Lag in days between incident date and JIV date."""
    lags = _lag_values(records)
    over = sum(1 for lag in lags if lag > config.QC_JIV_LAG_CAP_DAYS)
    return {
        "measured": len(lags),
        "median_days": round(float(statistics.median(lags)), 1) if lags else None,
        "max_days": max(lags) if lags else None,
        "over_cap_count": over,
        "over_cap_pct": round(over / len(lags) * 100, 1) if lags else 0.0,
    }


def _lag_values(records: list[dict]) -> list[int]:
    """All measurable JIV lags in days (records with both dates set)."""
    lags = []
    for r in records:
        d, j = _iso(r, config.COL_DATE), _iso(r, config.COL_JIV_DATE)
        if d and j:
            lags.append((j - d).days)
    return lags


def _company_breakdown(records: list[dict]) -> list[dict]:
    """Per-operator quality metrics — the litigation-relevant view.

    Every operator with at least one attributed record appears (unlike
    worst-year/worst-LGA, single-record groups are kept: a one-spill
    operator's record is still accountable). Sorted by volume of records,
    then name.
    """
    groups: dict[str, list[dict]] = {}
    for r in records:
        name = (r.get(config.COL_COMPANY) or "").strip()
        if not name or name.lower() in config.NULL_DATE_STRINGS:
            continue
        groups.setdefault(name, []).append(r)

    rows = []
    for name, members in groups.items():
        comp = _completeness_metrics(members)
        dup = _duplicate_metrics(members)
        lags = _lag_values(members)
        rows.append({
            "company": name,
            "records": len(members),
            "coordinate_pct": comp["coordinate_pct"],
            "date_pct": comp["date_pct"],
            "jiv_pct": comp["jiv_pct"],
            "duplicate_count": dup["duplicate_count"],
            "suspicious_recovery_count": _suspicious_recovery(members),
            "jiv_lag_median_days": round(float(statistics.median(lags)), 1) if lags else None,
        })
    rows.sort(key=lambda row: (-row["records"], row["company"].casefold()))
    return rows


def _worst_completeness(records: list[dict], key: str) -> dict | None:
    """Group by `key` and return the group with the lowest field completeness.

    Groups with a single record are skipped (a 33% completeness on one
    record is not a pattern). Returns None when nothing qualifies.
    """
    groups: dict[str, list[dict]] = {}
    for r in records:
        raw = r.get(key)
        name = "" if raw is None else str(raw).strip()
        # Treat missing values and null sentinels ("na", "null", "—", …)
        # alike as absent — reuse the config's sentinel vocabulary.
        if not name or name.lower() in config.NULL_DATE_STRINGS:
            continue
        groups.setdefault(name, []).append(r)

    scored = []
    for name, members in groups.items():
        if len(members) < 2:
            continue
        scored.append({
            key: name,
            "records": len(members),
            "completeness_pct": round(
                sum(_completeness(m) for m in members) / len(members) * 100, 1
            ),
        })
    if not scored:
        return None
    return min(scored, key=lambda g: (g["completeness_pct"], -g["records"]))


# ── Report assembly ────────────────────────────────────────────────────────
def compute_scorecard(records: list[dict]) -> dict:
    """Assemble the full scorecard dict from a list of record properties."""
    return {
        "total_records": len(records),
        "completeness": _completeness_metrics(records),
        "duplicates": _duplicate_metrics(records),
        "cause_cardinality": len({
            c for r in records if (c := (r.get(config.COL_CAUSE) or "").strip())
        }),
        "volume_plausibility": _volume_metrics(records),
        "suspicious_recovery_count": _suspicious_recovery(records),
        "jiv_lag": _jiv_lag_metrics(records),
        "worst_year": _worst_completeness(records, config.COL_YEAR),
        "worst_lga": _worst_completeness(records, config.COL_LGA),
        "per_company": _company_breakdown(records),
    }


# ── Markdown rendering ─────────────────────────────────────────────────────
def render_markdown(report: dict, source_name: str, generated_at: str) -> str:
    """Render the scorecard as a human-readable Markdown report."""
    comp, dup = report["completeness"], report["duplicates"]
    vol, lag = report["volume_plausibility"], report["jiv_lag"]
    lines = [
        "# Data-Quality Scorecard",
        "",
        f"- **Source:** `{source_name}`",
        f"- **Generated:** {generated_at}",
        f"- **Records audited:** {report['total_records']}",
        "",
        "> **Methodology caveat:** this scorecard audits the *record* — what",
        "> NOSDRA and operators reported — not ground truth. 100% completeness",
        "> would mean every field is filled, not that every spill was counted",
        "> or measured honestly. Record-level metrics cannot see spills that",
        "> were never reported, volumes disputed between companies and the",
        "> regulator, or JIV processes contested by communities.",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Coordinate completeness | {comp['coordinate_pct']}% |",
        f"| Date completeness | {comp['date_pct']}% |",
        f"| JIV completeness | {comp['jiv_pct']}% |",
        f"| Duplicate incident IDs | {dup['duplicate_count']} ({dup['duplicate_rate_pct']}%) |",
        f"| Distinct raw causes | {report['cause_cardinality']} |",
        f"| Suspicious recovery claims (≥{config.QC_SUSPICIOUS_RECOVERY_PCT}%) "
        f"| {report['suspicious_recovery_count']} |",
        f"| JIV lag median | {lag['median_days'] if lag['median_days'] is not None else 'n/a'} "
        f"days |",
        f"| JIV lag > {config.QC_JIV_LAG_CAP_DAYS}d "
        f"| {lag['over_cap_count']} ({lag['over_cap_pct']}%) |",
        "",
        "## Volume plausibility",
        "",
        "| Bucket | Count |",
        "|---|---|",
        f"| Plausible | {vol['plausible']} |",
        f"| Missing or nulled by cleaning | {vol['missing_or_nulled']} |",
        f"| Negative | {vol['negative']} |",
        f"| Below min ({config.QC_VOLUME_PLAUSIBILITY[0]} bbl) | {vol['below_min']} |",
        f"| Over cap ({config.QC_VOLUME_PLAUSIBILITY[1]:,} bbl) | {vol['over_cap']} |",
        "",
        "## Worst completeness",
        "",
        f"- **Year:** {report['worst_year']}",
        f"- **LGA:** {report['worst_lga']}",
        "",
        "## Per-operator breakdown",
        "",
        "| Operator | Records | Coords % | Dates % | JIV % | Dups | "
        "Suspicious recovery | JIV lag median (d) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in report["per_company"]:
        lines.append(
            f"| {row['company']} | {row['records']} | {row['coordinate_pct']} | "
            f"{row['date_pct']} | {row['jiv_pct']} | {row['duplicate_count']} | "
            f"{row['suspicious_recovery_count']} | "
            f"{row['jiv_lag_median_days'] if row['jiv_lag_median_days'] is not None else 'n/a'} |"
        )
    lines += [
        "",
        "*Operator attribution is exactly as recorded — variants of the same "
        "company (e.g. “Shell” vs “Shell Petroleum Dev Co”) are counted "
        "separately until cause/company normalisation lands.*",
        "",
    ]
    return "\n".join(lines)


# ── Runner ─────────────────────────────────────────────────────────────────
def run(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Compute, write (JSON + MD), and return the two output paths."""
    records = load_records(input_path)
    generated_at = datetime.now().isoformat(timespec="seconds")

    report = compute_scorecard(records)
    report["source_file"] = input_path.name
    report["generated_at"] = generated_at

    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"quality_scorecard_{ts}.json"
    md_path = output_dir / f"quality_scorecard_{ts}.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report, input_path.name, generated_at), encoding="utf-8")
    print(f"[SCORECARD] {len(records)} records audited from {input_path.name}")
    print(f"[SCORECARD] wrote {json_path.name} and {md_path.name}")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Data-quality scorecard for spill datasets")
    parser.add_argument("--input", type=Path, default=None,
                        help="Spill GeoJSON (default: latest cleaned ETL output)")
    parser.add_argument("--output-dir", type=Path, default=config.DATA_PROCESSED)
    args = parser.parse_args()

    input_path = args.input
    if input_path is None:
        candidates = sorted(config.DATA_PROCESSED.glob("nosdra_clean_*.geojson"))
        if not candidates:
            parser.error("no nosdra_clean_*.geojson in data/processed — "
                         "run the ETL first or pass --input")
        input_path = candidates[-1]

    if not input_path.exists():
        parser.error(f"input not found: {input_path}")

    run(input_path, args.output_dir)


if __name__ == "__main__":
    main()
