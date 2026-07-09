# ARCHITECTURE_NOTES

## How the pieces connect

```
source_records.csv ──► ingest.py ──► SQLite (records table)
                                            │
                                            ▼
                                  matching/engine.py (score)
                                            │
                                            ▼
                                  matching/tiering.py (tier)
                                            │
                                            ▼
                              SQLite (matches table, MatchResult)
                                            │
                              ┌─────────────┴─────────────┐
                              ▼                            ▼
                    routers/console.py            routers/records.py
                    (/review — needs matches)      (/records — no matching)
                              │                            │
                              ▼                            ▼
                    templates/review.html          templates/records.html
```

## 1. Trace: one record from CSV to the review console

A record starts in `source_records.csv`. On startup, `main.py` triggers
`ingest.py`, which reads the CSV and inserts each row into the SQLite DB via
`core/db.py`. The matching engine (`services/matching/engine.py`) then pulls
catalog candidates and scores them, `tiering.py` assigns green/yellow/red
based on the score, and the result gets saved back to the DB as a
`MatchResult`. When someone opens the review console, `routers/console.py`
queries those saved matches and `templates/review.html` renders them.

Modules, in order:

```
main.py → services/ingest.py → core/db.py → matching/engine.py →
matching/tiering.py → core/db.py → routers/console.py → templates/review.html
```

Worth noting: `/records` (`records.html`) renders directly from the records
table, no matching needed — that part already works. `/review` is the one
needing the engine + tiering, which is what I'm building.

## 2. Tier thresholds — moving the boundary without touching Python

Thresholds live in `config/settings.yaml` (`accept_min: 0.85`,
`review_min: 0.60`). `config.py` loads them, `tiering.py` uses them to decide
the tier. To move the accept/review boundary, you edit `accept_min`
specifically — that's the green/accept boundary (`review_min` is the
yellow/red boundary). Raising `accept_min` shrinks the auto-accept band and
pushes more records into review. No code change needed. Only catch: settings
are cached, so the app needs a restart to pick up a new value.

## 3. Dependency-failure convention

CONTRIBUTING.md requires:

> Every call to an external dependency (filesystem, network, subprocess,
> database file) must catch the dependency's specific exception type at the
> call site, log a structured `dependency_failure` event that includes the
> dependency name and enough context to reproduce, and re-raise as
> `app.core.errors.DependencyError` using `raise ... from exc`.

`ingest.py`'s `_read_csv()` follows this exactly: catches `OSError` at the
call site (wrapping the `open()` directly), logs `dependency_failure` with
`dependency="filesystem"` and `path=...`, then re-raises as `DependencyError`
from the original exception.
