# SpecMatch — AI assistant context

SpecMatch matches messy construction-material records to a canonical
catalog, assigns confidence tiers, and exposes the results through a
FastAPI API and a server-rendered (Jinja2) review console.

## Layout

- `backend/app/` — FastAPI application; `routers/` stay thin, logic lives
  in `services/`.
- `backend/app/models/schemas.py` — API contracts. **FROZEN: never modify.**
- `backend/app/services/matching/` — matching interfaces; the engine
  implementation goes here.
- `config/settings.yaml` — scoring weights and tier thresholds. Read them
  via `app.config.get_settings()`; never hardcode.
- `data/` — fixture CSVs ingested at startup.

## Commands

- Run locally: `cd backend && uvicorn app.main:app --reload`
- Tests: `cd backend && pytest`
- Full stack: `docker compose up --build` (API + console on :8000)

## Conventions

See CONTRIBUTING.md for the commit, logging, and error-handling rules.
The project-specific rules below are enforced in review; follow them exactly.

### Frozen contracts

- **Never modify `backend/app/models/schemas.py`.** CI verifies its SHA-256
  against `.github/schema.sha256`; any byte change fails the pipeline. If a
  contract seems wrong, document it in the README — do not edit the file.
- Endpoints must match those Pydantic contracts exactly (field names,
  optionality, response shapes).

### Configuration

- Scoring weights (`matching.weights`), `top_k`, and tier thresholds
  (`accept_min`, `review_min`) live in `config/settings.yaml` and are read
  through `app.config.get_settings()`. **Never hardcode them in Python.**
- Tier assignment goes through `services/matching/tiering.assign_tier`; both
  thresholds are *inclusive* lower bounds.

### Error handling & logging

- Every external-dependency call (filesystem, sqlite) must catch the specific
  exception at the call site, log a structured `dependency_failure` event with
  the dependency name and reproducible context, and re-raise as
  `app.core.errors.DependencyError` using `raise ... from exc`. See
  `services/ingest.py` and `services/matches.py` for the pattern.
- All logging goes through `app.core.logging.log_event(logger, level, event,
  **fields)` with a snake_case `event`. No `print()`, no interpolated prose.

### Matching engine

- The pipeline is: `normalize` → retrieve (`CandidateRetriever`) → score
  (`CandidateScorer`, composite of string/category/unit signals) → tier →
  persist. Implementations live in `services/matching/` behind the interfaces
  in `interfaces.py` so retrieval/scoring stay swappable.
- Normalization (`normalize.py`) is applied to **both** source text and
  catalog descriptions; keep it consistent across both sides.
- Persistence and reads of the `matches` table go through the repository in
  `services/matches.py` (`save_match`, `list_matches`, `get_match`,
  `apply_review`) — the engine and the API both use it; do not write raw SQL
  against `matches` elsewhere.

### Data & routers

- Ingest is idempotent: source records and catalog upsert via
  `INSERT OR REPLACE` on a unique key. Re-running ingest must not duplicate.
- Routers stay thin — request/response shaping only; all logic in `services/`.

### Testing

- Reproduce a bug with a failing test committed **before** the fix; reference
  the issue number in the fix commit (`Fixes #N`).
- Matching tests assert that named records land in the tiers the README
  claims (including at least one deliberate red).
