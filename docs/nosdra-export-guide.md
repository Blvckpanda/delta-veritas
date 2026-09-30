# Getting the Real NOSDRA Export + Reading the Scorecard

## Part 1 — Exporting from oilspillmonitor.ng

NOSDRA's Oil Spill Monitor is a single-page app; its download uses the
browser's File System API, so there is no scripted/URL fetch — you export
manually once per refresh cycle.

1. Open **https://nosdra.oilspillmonitor.ng** in Chrome or Edge.
2. Let the incident layer load (the map fills with spill markers).
3. Set filters to **all years, all states** unless you deliberately want a
   subset — the export inherits whatever is filtered. Note your filter set
   in the learning log; it defines the dataset's scope.
4. Click **Download**. The browser saves a GeoJSON file (array of features
   or FeatureCollection — the pipeline accepts both).
5. Move it to `data/raw/nosdra.json` (the pipeline's default input name;
   back up the sample file first). Raw files are never modified after this.
6. Run the pipeline:

   ```
   python src/etl/nosdra_pipeline.py
   ```

   It writes `data/processed/nosdra_clean_<timestamp>.geojson` and logs
   every cleaning decision to `logs/etl_pipeline.log` (append-only).

### What to expect from real data

- **20–40% of records without valid coordinates** — they are kept, dated,
  and analyzed, just not mapped.
- **Dozens of `cause` variants** — free text is preserved; normalisation
  is a future stage. The scorecard reports the raw cardinality.
- **Mixed date formats** — 17 known patterns + Excel serials are handled;
  truly unparseable dates stay null and are logged.
- **Volume outliers** — negatives and placeholder zeros are nulled by the
  ETL; the scorecard's volume buckets will show them as `missing_or_nulled`
  on cleaned data (non-zero `negative`/`over_cap` buckets on cleaned output
  would indicate a cleaning regression — check it).

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
