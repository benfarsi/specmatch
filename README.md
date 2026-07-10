# SpecMatch

Matches messy construction-material records to a canonical catalog, assigns a
confidence tier (green / yellow / red), and exposes the results through a
FastAPI API and a server-rendered (Jinja2) review console.

## System overview

The system is a pipeline with a thin web layer in front. CSVs are ingested
into SQLite at startup, every source record is matched against the catalog and
tiered, results are persisted, and they are served both as JSON and as a
human review console.

```
source_records.csv ──► ingest.py ──► SQLite (records table)
                                            │
                                            ▼
                                  matching/engine.py (retrieve → score)
                                            │
                                            ▼
                                  matching/tiering.py (assign tier)
                                            │
                                            ▼
                              SQLite (matches table, MatchResult JSON)
                                            │
                              ┌─────────────┴─────────────┐
                              ▼                            ▼
                    routers/matches.py            routers/console.py
                    (JSON API)                     (/, /review — Jinja2)
```

- `backend/app/main.py` — assembles the app; at startup runs ingest then the
  matching engine (`lifespan`).
- `backend/app/config.py` — loads `config/settings.yaml` (weights, `top_k`,
  tier thresholds) into cached, frozen dataclasses.
- `backend/app/models/schemas.py` — Pydantic API contracts. **Frozen** (CI
  verifies its SHA-256).
- `backend/app/services/matching/` — `normalize` → `retriever` → `scorer` →
  `engine`/`tiering`, all behind the interfaces in `interfaces.py`.
- `backend/app/services/matches.py` — repository for the `matches` table
  (persistence, queries, reviews); shared by the engine and the API.
- `backend/app/routers/` — thin HTTP handlers (health, records, matches,
  console).
- `backend/app/templates/` — server-rendered record table and review console.

## Setup

### Docker (API + console on :8000)

```bash
cp .env.example .env
docker compose up --build
```

- Console: http://localhost:8000/ · Review: http://localhost:8000/review
- API docs (Swagger): http://localhost:8000/docs
- Data persists across restarts via the `specmatch-data` volume
  (`DATA_DIR=/data`).

### Local (without Docker)

Requires Python 3.11+.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API reference

All responses conform to the frozen contracts in
`backend/app/models/schemas.py`.

### `GET /health`

```bash
curl http://localhost:8000/health
```
```json
{ "status": "ok", "records": 150, "matched": 150,
  "tiers": { "green": 81, "yellow": 58, "red": 11 } }
```

### `GET /matches`

Query params: `tier` (`green|yellow|red`, optional), `limit` (1–500,
default 50), `offset` (default 0).

```bash
curl "http://localhost:8000/matches?tier=yellow&limit=5&offset=0"
```
Returns `{ "total": <int>, "items": [ MatchResult, ... ] }`. Each
`MatchResult` includes `candidates` with per-signal `signals`
(`string_similarity`, `category_agreement`, `unit_compatibility`), the
assigned `tier`, `selected_catalog_id`, and any `review`.

### `POST /matches/{record_id}/review`

Persists an auditable review decision and returns the updated `MatchResult`.
Body: `{ "action": "accept"|"override"|"reject", "catalog_id": <str|null>,
"note": <str|null> }`.

```bash
# accept the top candidate
curl -X POST http://localhost:8000/matches/SRC-0007/review \
  -H "Content-Type: application/json" \
  -d '{"action":"accept","note":"correct channel"}'

# override with a specific listed candidate
curl -X POST http://localhost:8000/matches/SRC-0007/review \
  -H "Content-Type: application/json" \
  -d '{"action":"override","catalog_id":"CAT-0143"}'

# reject (no acceptable candidate)
curl -X POST http://localhost:8000/matches/SRC-0002/review \
  -H "Content-Type: application/json" \
  -d '{"action":"reject"}'
```

Unknown `record_id` → `404`; an override naming a candidate not in the
record's list → `400`.

## Running tests

```bash
cd backend
pytest                    # 48 tests
ruff check app tests      # lint (also run in CI)
```

CI (`.github/workflows/ci.yml`) runs, on every push to `main`: the
schema-freeze check, lint, tests, and a Docker build.

## Matching-engine design

Retrieval uses rapidfuzz `token_sort_ratio` over normalized text to narrow
the ~800-entry catalog to the top candidates per record, since exact matching
fails on abbreviations and reordered words, and full embeddings were
unnecessary overhead for a small, domain-specific vocabulary. I chose
`token_sort_ratio` over `token_set_ratio` because the set variant gave a bare
`STL` a perfect score against a full beam spec (over-confident), while the sort
variant stays honest about length and discriminates specs better.

Before scoring, both the source text and the catalog descriptions pass through
the **same** normalization (`normalize.py`): lowercasing, trade-abbreviation
expansion (`CONC`→concrete, `MW`→mineral wool, …), splitting numbers from
units (`50MPA`→`50 mpa`), and a small static imperial→metric lookup for gypsum
board thicknesses (`5/8in`→`15.9 mm`). Applying identical rules to both sides
is the point — consistency matters more than perfection.

Scoring combines three weighted signals from `config/settings.yaml` — string
similarity (0.60), category agreement (0.25), and unit compatibility (0.15) —
because no single signal is trustworthy alone: two records can be textually
similar but the wrong category, or the right category but the wrong spec. Blank
category/unit score a neutral 0.5 (unknown is neither right nor wrong). I chose
**whole-catalog scoring over category pre-filtering**: with only 800 entries the
cost is negligible, and pre-filtering risks silently dropping the right match
for the 35 records with blank/mislabeled categories — category earns its weight
as a signal, not a gate.

### Tier distribution (over all 150 fixture records)

| tier | count | share |
|------|-------|-------|
| 🟢 green (auto-accept) | 81 | 54.0% |
| 🟡 yellow (review) | 58 | 38.7% |
| 🔴 red (no acceptable match) | 11 | 7.3% |

The spread reflects real confidence, not an avoidance strategy:

- **Green** — `BATT INSUL MW R-22` → `Batt insulation, mineral wool, R-22`
  (score 1.00): a confident, exact match after abbreviation expansion.
- **Green (via imperial→metric)** — `GYP BD 5/8in TYPE X` →
  `Gypsum board, 15.9 mm, Type X` (score 0.90): the normalization lookup
  converts `5/8in`→`15.9 mm`, aligning imperial source with metric catalog.
- **Yellow** — `STL CHAN C310X31` → `Steel channel C310x31, CSA G40.21 300W`
  (score 0.76): the correct channel, but the catalog carries extra spec detail
  the source lacks, so it is routed to human review rather than auto-accepted.
- **Red** — `MATL PER DWG S-501` (best 0.41): a genuinely vague input
  ("material per drawing") with no honest catalog match.

### Known limitation

The imperial→metric conversion is a deliberately small static lookup covering
only the gypsum board thicknesses present in the data (`1/2in`, `5/8in`); it is
not a general unit converter. The `unit_compatibility` signal operates on the
metric-only `unit` column (exact match, with `kg`/`t` treated as compatible
mass). A record whose sole discriminator was an unhandled imperial dimension
could still be mis-scored — a documented tradeoff, not a bug. Retrieval sits
behind the `CandidateRetriever` interface, so an embedding/TF-IDF layer could
be added later without changing the engine.

## Issue fixes

Each issue was reproduced with a failing test committed **before** the fix,
with the issue number in the fix commit.

### Issue #1 — duplicate records after re-running ingest

- **Symptom:** after restarting the stack (or re-running ingest), `/health`
  reported double the record count and the console listed every record twice.
- **Root cause:** record ingestion was **not idempotent**. `ingest_records`
  used a plain `INSERT` into a `records` table whose `record_id` had no
  uniqueness constraint, so every run appended a fresh copy — unlike the
  catalog, which was already idempotent via `INSERT OR REPLACE` on a
  `PRIMARY KEY`.
- **Fix (following convention):** added a `UNIQUE` constraint on
  `records.record_id` (`core/db.py`) and switched to `INSERT OR REPLACE`
  (`services/ingest.py`), mirroring the catalog's existing upsert pattern so a
  re-run overwrites instead of appending.

### Issue #2 — wrong confidence tier at a threshold boundary

- **Symptom:** a composite score of exactly `0.85` (`accept_min`) was assigned
  `yellow`, though the config documents both thresholds as inclusive lower
  bounds, so it should be `green`.
- **Root cause:** `tiering.py:14` used a strict `>` (`score > accept_min`) at
  the green boundary, contradicting the inclusive-lower-bound contract stated
  in `settings.yaml` and the `TierThresholds` docstring.
- **Fix (following convention):** changed `>` to `>=` at the `accept_min`
  boundary. Thresholds remain read from config; a boundary regression test
  (plus a guard for the `review_min` boundary) locks the behavior.

### Issue #3 — record table empties after switching filter back to "All categories"

- **Symptom:** selecting a specific category filtered correctly, but switching
  back to "All categories" showed "No records"; a plain reload of `/` worked.
- **Root cause:** a **sentinel mismatch** between template and router. The
  template's "All categories" option submitted the literal string `"All"`
  (`value="All"`), while the router treated "no filter" as `None` (an absent
  param). So `"All"` was used as a real category filter, matching nothing.
- **Fix (following convention):** the option now submits an empty value, and
  the router normalizes a blank category to `None`
  (`category = category or None`), so both ends agree that "no filter" means
  empty/absent. Router stays thin; a regression test reproduces the empty
  table.

## Deviations from PLAN.md

- **Metric:** PLAN described "token-set similarity"; the implementation uses
  `token_sort_ratio` after empirically comparing the two — `token_set_ratio`
  over-scored bare abbreviations (e.g. `STL`).
- **Imperial→metric normalization** (gypsum thicknesses) was added after
  noticing the `5/8in`↔`15.9mm` gap; it was not in the original plan. It is
  scoped to the `fraction+in` form so it cannot affect HSS steel sizes, which
  use bare fractions on both sides.
- **Optional stretch deferred:** the embedding/TF-IDF retrieval layer was
  intentionally not built, to keep a strong core (as PLAN allowed). The
  `CandidateRetriever` interface keeps it a drop-in.
- Otherwise the plan held: issues (Task 2) before the engine (Task 3), then
  API, console, and Docker/CI in order.

## AI usage

I used Claude Code throughout, but stayed the one making design decisions and
writing my own `ARCHITECTURE_NOTES.md` / `PLAN.md` answers rather than
accepting drafted ones. One concrete correction: I initially asked for an
imperial↔metric unit-conversion lookup inside the unit-compatibility signal.
Claude Code flagged that this would be dead code — the `unit` column in this
dataset is already all-metric — and that the real ambiguity lived in the
description text instead, which changed where (and whether) I built that logic
(it moved into `normalize.py`, scoped so it couldn't break HSS matching). I
kept manual: all design tradeoffs (whole-catalog vs. pre-filter, issue
root-cause diagnosis before any fix). I delegated: boilerplate router/template
code, test scaffolding, and CI configuration.
