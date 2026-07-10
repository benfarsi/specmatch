"""Repository for the `matches` table: persistence, queries, and reviews.

Keeps SQL out of the routers (which stay thin) and gives the engine and the
API one place to read and write MatchResults. Every database call follows the
dependency-failure convention (see CONTRIBUTING.md).
"""

import logging
import sqlite3
from datetime import datetime, timezone

from app.core.errors import DependencyError
from app.core.logging import log_event
from app.models.schemas import MatchResult, Review, ReviewAction, ReviewRequest, Tier

logger = logging.getLogger(__name__)


def save_match(conn: sqlite3.Connection, result: MatchResult) -> None:
    """Upsert one MatchResult (keyed on record_id). The caller commits."""
    try:
        conn.execute(
            "INSERT OR REPLACE INTO matches (record_id, payload, tier, matched_at)"
            " VALUES (?, ?, ?, ?)",
            (
                result.record_id,
                result.model_dump_json(),
                result.tier.value,
                result.matched_at.isoformat(),
            ),
        )
    except sqlite3.Error as exc:
        log_event(
            logger,
            logging.ERROR,
            "dependency_failure",
            dependency="sqlite",
            operation="save_match",
            record_id=result.record_id,
            error=str(exc),
        )
        raise DependencyError("could not persist match") from exc


def list_matches(
    conn: sqlite3.Connection, tier: Tier | None, limit: int, offset: int
) -> tuple[int, list[MatchResult]]:
    clause, params = "", []
    if tier is not None:
        clause, params = " WHERE tier = ?", [tier.value]
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM matches{clause}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT payload FROM matches{clause} ORDER BY record_id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    except sqlite3.Error as exc:
        log_event(
            logger,
            logging.ERROR,
            "dependency_failure",
            dependency="sqlite",
            operation="list_matches",
            error=str(exc),
        )
        raise DependencyError("could not read matches") from exc
    return total, [MatchResult.model_validate_json(row["payload"]) for row in rows]


def tier_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return the number of matches in each tier (missing tiers are 0)."""
    counts = {tier.value: 0 for tier in Tier}
    try:
        rows = conn.execute(
            "SELECT tier, COUNT(*) AS n FROM matches GROUP BY tier"
        ).fetchall()
    except sqlite3.Error as exc:
        log_event(
            logger,
            logging.ERROR,
            "dependency_failure",
            dependency="sqlite",
            operation="tier_counts",
            error=str(exc),
        )
        raise DependencyError("could not count tiers") from exc
    for row in rows:
        if row["tier"] in counts:
            counts[row["tier"]] = row["n"]
    return counts


def get_match(conn: sqlite3.Connection, record_id: str) -> MatchResult | None:
    try:
        row = conn.execute(
            "SELECT payload FROM matches WHERE record_id = ?", (record_id,)
        ).fetchone()
    except sqlite3.Error as exc:
        log_event(
            logger,
            logging.ERROR,
            "dependency_failure",
            dependency="sqlite",
            operation="get_match",
            record_id=record_id,
            error=str(exc),
        )
        raise DependencyError("could not read match") from exc
    return MatchResult.model_validate_json(row["payload"]) if row else None


def apply_review(
    conn: sqlite3.Connection, record_id: str, request: ReviewRequest
) -> MatchResult:
    """Persist a review decision and return the updated MatchResult.

    Raises LookupError if the record has no match, and ValueError if the
    request is inconsistent (e.g. an override that names a candidate not in
    the record's candidate list).
    """
    match = get_match(conn, record_id)
    if match is None:
        raise LookupError(record_id)

    candidate_ids = {candidate.catalog_id for candidate in match.candidates}
    action = request.action

    if action is ReviewAction.reject:
        selected = None
    elif action is ReviewAction.override:
        if not request.catalog_id:
            raise ValueError("override requires a catalog_id")
        if request.catalog_id not in candidate_ids:
            raise ValueError("catalog_id is not among the listed candidates")
        selected = request.catalog_id
    else:  # accept
        if request.catalog_id and request.catalog_id not in candidate_ids:
            raise ValueError("catalog_id is not among the listed candidates")
        selected = request.catalog_id or (
            match.candidates[0].catalog_id if match.candidates else None
        )

    review = Review(
        action=action,
        catalog_id=request.catalog_id,
        note=request.note,
        reviewed_at=datetime.now(timezone.utc),
    )
    updated = match.model_copy(update={"selected_catalog_id": selected, "review": review})
    save_match(conn, updated)
    conn.commit()
    log_event(
        logger,
        logging.INFO,
        "review_persisted",
        record_id=record_id,
        action=action.value,
        selected_catalog_id=selected,
    )
    return updated
