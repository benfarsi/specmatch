# PLAN

## Order of work

I'm following the spec's own task numbering straight through, because when
this time-boxed it's the right call — no cleverness needed:

**Task 2 (issues) → Task 3 (engine) → Task 4 (API) → Task 5 (console) →
Task 6 (Docker/CI).**

Issues before engine is deliberate: Issue #2 is a bug in the tiering
boundary logic, and the engine calls `tiering`. Building the engine on top
of a known-broken boundary means I'd have to redo tier-distribution testing
after the fix anyway, so I fix the boundary first.

## Task 2 — the three issues

Each issue: reproduce with a **failing test committed first**, then fix
following existing conventions, with the **issue number in the commit
message**. Diagnosis (root cause, not symptom) is part of the task.

- **Issue #1** — duplicate records after re-running ingest.
- **Issue #2** — a record lands in the wrong confidence tier at a boundary
  value (the tiering boundary logic).
- **Issue #3** — the review console shows an empty list after changing a
  filter.

## Task 3 — matching engine (the core)

Retrieval uses rapidfuzz token-set similarity to narrow ~800 catalog
entries to the top-k candidates per record, since exact matching fails on
abbreviations and reordered words, and full embeddings are unnecessary
overhead for a same-language, domain-specific vocabulary; scoring combines
string similarity, category agreement, and unit compatibility as weighted
signals from `settings.yaml`, because no single signal is trustworthy alone
— two records can be textually similar but wrong category, or same category
but wrong spec.

Mechanics, behind the interfaces in `interfaces.py`:

- Retrieve top-k candidates (`Settings.matching.top_k`) via rapidfuzz.
- Score each with a composite in [0, 1] from the three signals, weighted by
  `Settings.matching.weights` — never hardcoded.
- Assign tier via `tiering.assign_tier` using `Settings.tiers`.
- Persist top-k per record with the per-signal breakdown, so I can answer:
  what matched, with what score, from which signals, and why that tier.
- Report the resulting tier distribution over the full fixture set in the
  README (graders reproduce it). Target a defensible spread, not everything
  in yellow or everything in green.

## Task 4 — API

Complete the stubbed endpoints to the **frozen** contracts in
`schemas.py` exactly: `GET /health`, `GET /matches` (tier filter +
limit/offset), `POST /matches/{record_id}/review` (persisted, auditable).
Leave `GET /records` behavior intact (Issue #1 aside). Routers stay thin.

## Task 5 — review console

Fill in the stubbed review panel: yellow/red queues with visible counts,
source text + top candidates + per-signal breakdown, and accept / override
/ reject actions that persist through the API. Follow the existing console
routing/template conventions.

## Task 6 — Docker & CI

`docker compose up --build` works from a clean clone, data persists across
restarts. Extend CI so every push to main runs: tests, lint, Docker build,
and the schema-freeze check. CI green on the final commit. No credentials
in the repo.

## Risk

The main risk is abbreviation/unit inconsistency (blank units, inconsistent
abbreviations like 'MW'/'LW') causing the engine to either dump everything
into yellow (safe but uninformative) or overconfidently green things that
shouldn't be — the goal is a tier distribution I can defend, not just one
that avoids obviously wrong answers.

## Time budget

Deadline: Fri **July 10, 2026, 11:59 PM ET**.

- **Thu (remaining today):** finish Task 1 docs; Task 2 — all three issues
  (test-first, fix, commit referencing the issue).
- **Fri morning:** Task 3 — the matching engine (the big block; the piece I
  most need to understand and defend).
- **Fri afternoon:** Task 4 (API) then Task 5 (review console).
- **Fri evening:** Task 6 (Docker/CI), README (system overview + diagram,
  API reference, matching design + tier distribution, issue root causes, AI
  usage), final green-CI check before the deadline.

If time runs short, I stop after Task 4: a working API over a defensible
engine demos the whole pipeline; the review panel is the most cuttable
piece. Deviations from this plan get noted in the README.
