# Getting the Real NOSDRA Export + Reading the Scorecard

## Part 1 — Getting the NOSDRA Export

### Scripted fetch (primary)

The Oil Spill Monitor SPA loads its full historical incident table from an
unauthenticated endpoint — the same data the Download button wraps:

```
python src/etl/nosdra_pipeline.py --fetch
```

One GET downloads every incident since 2006 (~21,000 records) to
`data/raw/nosdra.json` and then runs the pipeline over it. The response is
a bare JSON array of flat dicts in the live API's own vocabulary
(`incidentnumber`, `incidentdate`, `statesaffected`, `estimatedquantity`,
`jivdate`, …); `map_api_record` converts it to the canonical schema before
cleaning — raw `cause` codes (`sab`, `eqf`, `cor`, `ome`, …) are preserved
verbatim, unknown `statesaffected` values pass through untouched, and
~2% administrative-only rows (remediation certificates, cleanup updates)
are kept with `NOSDRA-API-<id>`/`<id>` identifiers. Re-run `--fetch`
anytime for a fresh snapshot; raw files are never modified after download.

### Manual export (fallback)

If the endpoint is ever unreachable, the manual path still works — it is a
single-page app whose download uses the browser's File System API:

1. Open **https://nosdra.oilspillmonitor.ng** in Chrome or Edge.
2. Let the incident layer load (the map fills with spill markers).
3. Set filters to **all years, all states** unless you deliberately want a
   subset — the export inherits whatever is filtered. Note your filter set
   in the learning log; it defines the dataset's scope.
4. Click **Download**. The browser saves a GeoJSON file (array of features
   or FeatureCollection — the pipeline accepts both).
5. Move it to `data/raw/nosdra.json` (the pipeline's default input name;
   the previous file survives in git history). Raw files are never modified
   after this.
6. Run the pipeline:

   ```
   python src/etl/nosdra_pipeline.py
   ```

   It writes `data/processed/nosdra_clean_<timestamp>.geojson` and logs
   every cleaning decision to `logs/etl_pipeline.log` (append-only).

### What to expect from real data

- **20–40% of records without valid coordinates** — they are kept, dated,
  and analyzed, just not mapped. (First live fetch: 22.6%.)
- **Cause arrives as abbreviated codes** from the live API (`sab` =
  sabotage, `eqf` = equipment failure, `cor` = corrosion, `ome` =
  operations/maintenance error, `other:`) — preserved verbatim; the
  scorecard reports the raw cardinality. Normalisation is a future stage.
- **Mixed date formats** — 17 known patterns + Excel serials are handled;
  truly unparseable dates stay null and are logged.
- **Volume outliers** — negatives and placeholder zeros are nulled by the
  ETL; the scorecard's volume buckets will show them as `missing_or_nulled`
  on cleaned data (non-zero `negative`/`over_cap` buckets on cleaned output
  would indicate a cleaning regression — check it).

## Part 1b — The Weekly Digest

The digest answers "what changed since the last run?" in two sections:
**newly disclosed** (incident IDs not present at the previous run — backfilled
historic spills included) and **newly occurred** (recorded spill date inside
the window). Grouped by state/LGA with volumes and top operators.

```
python src/etl/digest.py                 # after each weekly ETL + fetch
python src/etl/digest.py --seed          # first ever run: baseline only, no report
python src/etl/digest.py --since 2026-09-01   # ad-hoc occurrence window
python src/etl/digest.py --input data/processed/nosdra_clean_X.geojson
```

It writes `data/processed/digest_<timestamp>.md`, logs to `logs/digest.log`
(append-only), and tracks state in `data/processed/digest_state.json`
(machine-local — never committed). A late-entered spill can appear in both
sections; they measure different things. Delete the state file to re-baseline.

## Part 2 — The Data-Quality Scorecard

Run it against the latest cleaned export:

```
python src/analysis/quality_scorecard.py
# or explicitly:
python src/analysis/quality_scorecard.py --input data/processed/nosdra_clean_X.geojson
```

It writes two timestamped files into `data/processed/`:
`quality_scorecard_<ts>.json` (machine-readable) and `.md` (readable).

### Interpreting the metrics

| Metric | What it tells you | What it does NOT tell you |
|---|---|---|
| Coordinate / date / JIV completeness | How much of the official record is usable | Whether reported locations/dates are *correct* |
| Duplicate incident IDs | Double-entry or re-registration hygiene | Whether distinct incidents were wrongly merged upstream |
| Cause cardinality | How unstandardised reporting is | Which cause labels are honest |
| Volume plausibility buckets | Data-entry quality (negatives, caps, units) | Whether plausible volumes are truthful |
| Suspicious recovery (≥99.9%) | Claims of near-total recovery — a known artifact | Intent; some are legitimate |
| JIV lag (median, >28d rate) | Investigation responsiveness as recorded | Whether JIVs happened at all when unrecorded |
| Worst year / worst LGA | Where record-keeping is weakest | Why (staffing, conflict, or concealment) |

### The methodology caveat (rendered into every report)

The scorecard audits the **record**, not ground truth. A 100%-complete
dataset means every field is filled — not that every spill was counted or
measured honestly. Spills that were never reported, volumes disputed
between companies and the regulator, and contested JIV processes are
invisible to any record-level audit. This is a tool for interrogating the
official record's *consistency and usability*, and for generating
questions worth asking — not for asserting what actually happened on the
ground.
