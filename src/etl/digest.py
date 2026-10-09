"""
Weekly Digest — what changed in the NOSDRA record since the last run.

Answers the scorecard audience's operating question: what is new? Two
sections, because "new" has two meanings on a messy public register:

  Newly disclosed — incident IDs not present at the previous run. Includes
      backfilled historic spills entering the record for the first time.
  Newly occurred  — incidents whose recorded spill date falls inside the
      window since the last run. A late-entered spill can appear in both
      sections; the sections measure different things.

State lives in data/processed/digest_state.json (seen incident IDs + the
last run timestamp) and is machine-local, never committed. The first run
reports the full record as the baseline unless --seed establishes the
baseline silently.

Usage:
    python src/etl/digest.py                       # after each weekly ETL
    python src/etl/digest.py --seed                # first run: baseline only
    python src/etl/digest.py --since 2026-09-01    # ad-hoc occurrence window
    python src/etl/digest.py --input data/processed/nosdra_clean_X.geojson
"""

import argparse
import contextlib
import json
import logging
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

# Ensure config is importable when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config


# ── Logging setup (same pattern as nosdra_pipeline, own append-only file) ──
def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("nosdra_digest")
    logger.setLevel(logging.DEBUG)

    fh = logging.FileHandler(config.DIGEST_LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(config.LOG_FORMAT, config.LOG_DATE_FORMAT))

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    # Windows consoles default to a non-UTF-8 codepage; drop characters the
    # console cannot encode instead of crashing mid-report.
    if hasattr(sh.stream, "reconfigure"):
        with contextlib.suppress(OSError, ValueError):
            sh.stream.reconfigure(encoding="utf-8", errors="replace")

    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


logger = _setup_logger()


# ── Loading ────────────────────────────────────────────────────────────────
def _load_records(path: Path) -> list[dict]:
    """Load a cleaned GeoJSON and return the list of feature properties.

    Deliberately a local copy of the scorecard's loader (kept independent
    of src/analysis per the no-lateral-imports rule in
    context/code-standards.md). Accepts a FeatureCollection, a bare list of
    features, or a bare list of property dicts.
    """
    data = json.loads(path.read_text(encoding="utf-8"))

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


def _iso_date(raw) -> date | None:
    """Parse an ISO date string (YYYY-MM-DD) into a date, else None."""
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), config.OUTPUT_DATE_FORMAT).date()
    except ValueError:
        return None


# ── Aggregation (pure) ─────────────────────────────────────────────────────
def _label(value) -> str:
    """Normalise a grouping label; blanks/sentinels become the unknown bucket."""
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in config.NULL_DATE_STRINGS:
        return config.DIGEST_UNKNOWN_LABEL
    return text


def _group_rows(records: list[dict]) -> list[dict]:
    """Aggregate records into state → LGA rows sorted by incident count."""
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in records:
        key = (_label(r.get(config.COL_STATE)), _label(r.get(config.COL_LGA)))
        groups.setdefault(key, []).append(r)

    rows = []
    for (state, lga), members in groups.items():
        operators = Counter(_label(m.get(config.COL_COMPANY)) for m in members)
        causes = Counter(_label(m.get(config.COL_CAUSE)) for m in members)
        rows.append({
            "state": state,
            "lga": lga,
            "incidents": len(members),
            "spilled_bbl": sum(
                v for m in members
                if isinstance((v := m.get(config.COL_QTY_SPILLED)), (int, float))
            ),
            "recovered_bbl": sum(
                v for m in members
                if isinstance((v := m.get(config.COL_QTY_RECOVERED)), (int, float))
            ),
            "operators": ", ".join(f"{op} ({n})" for op, n in operators.most_common(2)),
            "causes": ", ".join(f"{cs} ({n})" for cs, n in causes.most_common(2)),
        })
    rows.sort(key=lambda row: (-row["incidents"], row["state"], row["lga"]))
    return rows


def compute_digest(
    records: list[dict], seen_ids: set[str], occurred_since: date
) -> dict:
    """Split the record into newly-disclosed and newly-occurred groupings.

    Newly disclosed: incident ID absent from seen_ids (backfills included).
    Newly occurred:  recorded spill date >= occurred_since.
    """
    disclosed: list[dict] = []
    occurred: list[dict] = []
    current_ids: set[str] = set()

    for r in records:
        incident_id = str(r.get(config.COL_INCIDENT_ID) or "").strip()
        if not incident_id:
            continue  # unidentifiable rows are invisible to digest state
        current_ids.add(incident_id)
        if incident_id not in seen_ids:
            disclosed.append(r)
        incident_date = _iso_date(r.get(config.COL_DATE))
        if incident_date is not None and incident_date >= occurred_since:
            occurred.append(r)

    return {
        "total_records": len(records),
        "disclosed_total": len(disclosed),
        "disclosed_rows": _group_rows(disclosed),
        "occurred_total": len(occurred),
        "occurred_rows": _group_rows(occurred),
        "current_ids": current_ids,
    }


# ── Markdown rendering ─────────────────────────────────────────────────────
def _fmt_vol(value: float | int | None) -> str:
    """Volume cell: thousands separators, em-dash when nothing was summed."""
    if value is None:
        return "—"
    return f"{value:,.1f}"


def _table(rows: list[dict]) -> str:
    """Render one section's state/LGA table, or a none-in-window note."""
    if not rows:
        return "_None in this window._\n"
    lines = [
        "| State | LGA | Incidents | Spilled (bbl) | Recovered (bbl) "
        "| Top operators | Top causes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['state']} | {r['lga']} | {r['incidents']:,} | "
            f"{_fmt_vol(r['spilled_bbl'])} | {_fmt_vol(r['recovered_bbl'])} | "
            f"{r['operators']} | {r['causes']} |"
        )
    return "\n".join(lines) + "\n"


def render_markdown(
    digest: dict, source_name: str, generated_at: str,
    occurred_since: date, is_first_run: bool,
) -> str:
    """Render the digest as a human-readable Markdown report."""
    first_note = (
        "First run — the full record is reported as the baseline. "
        "Run with `--seed` to establish the baseline silently."
        if is_first_run
        else "Everything not present at the previous run, backfills included."
    )
    window_end = date.today().isoformat()
    return "\n".join([
        "# NOSDRA Weekly Digest — What Changed",
        "",
        f"- **Generated:** {generated_at}",
        f"- **Source:** `{source_name}`",
        f"- **Records in source:** {digest['total_records']:,}",
        f"- **Occurrence window:** {occurred_since.isoformat()} → {window_end}",
        "",
        "> **Caveat:** this digest audits the *record* — what NOSDRA and",
        "> operators reported — not ground truth. Volumes nulled by cleaning",
        f"> (absent, `nil`, implausible) are excluded from the sums; {config.DIGEST_UNKNOWN_LABEL}",
        "> buckets mark records missing a usable state/LGA/company/cause.",
        "",
        "## Newly disclosed since last run",
        "",
        f"**Total: {digest['disclosed_total']:,} incidents** — {first_note}",
        "",
        _table(digest["disclosed_rows"]),
        "## Newly occurred since last run",
        "",
        f"**Total: {digest['occurred_total']:,} incidents** with a "
        "recorded spill date in the window.",
        "",
        _table(digest["occurred_rows"]),
        "## Notes",
        "",
        "- *Newly disclosed* = incident ID not present at the previous run; "
        "catches backfilled historic spills.",
        "- *Newly occurred* = recorded spill date inside the window; "
        "a late-entered spill can appear in both sections.",
        "",
    ])


# ── Digest state (machine-local, never committed) ─────────────────────────
def _load_state(path: Path) -> dict:
    """Read the digest state, or return a fresh baseline marker if absent."""
    if not path.exists():
        return {"version": 1, "last_run_utc": None, "seen_incident_ids": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"corrupt digest state file {path}: {exc}") from exc
    if not isinstance(state, dict) or "seen_incident_ids" not in state:
        raise ValueError(f"unrecognised digest state file: {path}")
    state.setdefault("seen_incident_ids", [])
    return state


def _save_state(path: Path, seen_ids: set[str], last_run_utc: str) -> None:
    """Persist seen incident IDs and the run timestamp."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1,
        "last_run_utc": last_run_utc,
        "seen_incident_ids": sorted(seen_ids),
    }, ensure_ascii=False), encoding="utf-8")


# ── Runner ─────────────────────────────────────────────────────────────────
def run(
    input_path: Path, state_path: Path, output_dir: Path,
    since: date | None = None, seed: bool = False,
) -> Path | None:
    """Compute, write (unless seeding), update state, and return the md path.

    The occurrence window starts at `since` when given, else at the previous
    run's date, else DIGEST_DEFAULT_WINDOW_DAYS back for the first run.
    """
    records = _load_records(input_path)
    state = _load_state(state_path)

    last_run = state.get("last_run_utc")
    is_first_run = last_run is None
    if since is not None:
        occurred_since = since
    elif last_run:
        occurred_since = datetime.fromisoformat(last_run).date()
    else:
        occurred_since = date.today() - timedelta(days=config.DIGEST_DEFAULT_WINDOW_DAYS)

    digest = compute_digest(records, set(state["seen_incident_ids"]), occurred_since)

    md_path = None
    if not seed:
        generated_at = datetime.now().isoformat(timespec="seconds")
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = output_dir / f"{config.DIGEST_OUTPUT_PREFIX}{ts}.md"
        md_path.write_text(
            render_markdown(
                digest, input_path.name, generated_at, occurred_since, is_first_run,
            ),
            encoding="utf-8",
        )

    _save_state(
        state_path, digest["current_ids"], datetime.now().isoformat(timespec="seconds")
    )

    logger.info(
        "Digest from %s: %d records, %d newly disclosed, %d newly occurred "
        "(window since %s%s)",
        input_path.name, digest["total_records"], digest["disclosed_total"],
        digest["occurred_total"], occurred_since.isoformat(),
        ", baseline seeded" if seed else "",
    )
    if md_path:
        logger.info("Wrote %s", md_path)
    logger.info(
        "State: %d seen incident ids → %s", len(digest["current_ids"]), state_path
    )
    return md_path


def main() -> None:
    """CLI entry point: parse flags, resolve the input file, and run the digest."""
    parser = argparse.ArgumentParser(description="Weekly digest of new NOSDRA incidents")
    parser.add_argument("--input", type=Path, default=None,
                        help="Spill GeoJSON (default: latest cleaned ETL output)")
    parser.add_argument("--state-file", type=Path,
                        default=config.DATA_PROCESSED / config.DIGEST_STATE_FILENAME,
                        help="Digest state file (default: data/processed/digest_state.json)")
    parser.add_argument("--output-dir", type=Path, default=config.DATA_PROCESSED)
    parser.add_argument("--since", type=date.fromisoformat, default=None,
                        help="Occurrence window start, YYYY-MM-DD "
                             "(default: since the last run, else 7 days)")
    parser.add_argument("--seed", action="store_true",
                        help="Record the baseline (all current IDs seen) without emitting a digest")
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

    run(input_path, args.state_file, args.output_dir, since=args.since, seed=args.seed)


if __name__ == "__main__":
    main()
