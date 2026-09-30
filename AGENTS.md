# Niger Delta Environmental Risk Observatory — Agent Context

## Context Files (read before implementing)

Read these in order. Do not begin writing code until all are read.

1. `context/project-overview.md` — product definition, goals, features, core user flow, ethical boundaries
2. `context/architecture.md` — stack, data flow, storage model, invariants
3. `context/code-standards.md` — Python conventions, docstrings, config discipline, output format
4. `context/ai-workflow-rules.md` — scoping rules, split decisions, protected files, verification checklist
5. `context/progress-tracker.md` — phase status, done-when checklists, decisions log

## Hard Rules

- Every function has a docstring. No exceptions.
- `src/etl/config.py` is the single source of truth for column names, file paths, date formats, thresholds.
- Raw data files in `data/raw/` are never modified.
- `logs/etl_pipeline.log` is append-only. Never truncate.
- Output filenames include an ISO date timestamp.
- Modules do not import each other laterally. Only `pipeline.py` imports from stage modules.
- No Python traceback reaches the user. All exceptions caught and surfaced as plain-English messages.
- No infrastructure coordinates are collected, stored, or published.
- Every data point must trace to a public, authoritative source.
