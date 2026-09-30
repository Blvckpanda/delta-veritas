# AI Workflow Rules

## Scoping

- Work on ONE phase at a time in strict order.
- Check `progress-tracker.md` before starting any work.
- Do NOT implement future-phase features even if convenient.
- When a task needs a decision, present options with tradeoffs; don't guess.

## Splitting Work

- If a task will take >5 tool calls, split into subtasks.
- Mark each subtask in `todo` with `in_progress` status.
- Update `todo` as each subtask completes.

## Data Quality

- Always validate data before processing.
- Log every quality issue encountered.
- Document schema changes in the data-source reference doc.
- Never silently discard data — log the reason.

## Protected Files

Never modify:
- `data/raw/*` — raw source data is read-only
- `logs/data_quality.log` — append-only
- `docs/data-sources.md` — source documentation is authorative reference

## Verification Checklist

Before marking a phase complete:

1. ✅ Every checklist item in the phase's done-when list passes (verified by running the script, not by inspection)
2. ✅ No invariant in `architecture.md` was violated
3. ✅ `progress-tracker.md` reflects the completed phase and all decisions made
4. ✅ Every new function has a docstring
5. ✅ No column name, file path, or threshold was hardcoded outside `config.py`
6. ✅ Learning log entry written for the phase

## Ethical Guard

- Before processing ANY location data, confirm it is a public disclosure, not triangulated coordinates
- If uncertain about a data source's disclosure status, flag it and do not publish
- Document the decision in the progress tracker
