"""The lexical matching engine.

For each source record the engine runs the pipeline:
retrieve a lexical shortlist -> score every candidate with the composite ->
rank by score -> assign a tier -> persist the top-k as a MatchResult.

Retrieval and scoring sit behind their interfaces (LexicalRetriever /
WeightedScorer), so alternative strategies can be swapped in without changing
this orchestration. The top-k count, signal weights, and tier thresholds all
come from Settings (config/settings.yaml).
"""

import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from app.config import get_settings
from app.core.db import get_conn
from app.core.errors import DependencyError
from app.core.logging import log_event
from app.models.schemas import CatalogEntry, MatchResult, RecordOut, Tier
from app.services.matching.interfaces import (
    CandidateRetriever,
    CandidateScorer,
    MatchingEngine,
)
from app.services.matching.retriever import LexicalRetriever
from app.services.matching.scorer import WeightedScorer
from app.services.matching.tiering import assign_tier

logger = logging.getLogger(__name__)

# Size of the lexical shortlist re-ranked by the full composite score. Larger
# than top_k so the category/unit signals can promote a candidate that ranked
# slightly lower on string similarity alone.
SHORTLIST_SIZE = 25


class LexicalMatchingEngine(MatchingEngine):
    """Retrieval + composite scoring over the ingested catalog."""

    def __init__(
        self,
        retriever: CandidateRetriever | None = None,
        scorer: CandidateScorer | None = None,
    ) -> None:
        self._retriever = retriever or LexicalRetriever()
        self._scorer = scorer or WeightedScorer()

    def match_record(self, record: RecordOut) -> MatchResult:
        conn = get_conn()
        try:
            catalog = self._load_catalog(conn)
            result = self._match(record, catalog)
            self._persist(conn, result)
            conn.commit()
        finally:
            conn.close()
        return result

    def match_all(self) -> list[MatchResult]:
        conn = get_conn()
        try:
            catalog = self._load_catalog(conn)
            records = self._load_records(conn)
            results = [self._match(record, catalog) for record in records]
            for result in results:
                self._persist(conn, result)
            conn.commit()
        finally:
            conn.close()
        tiers = Counter(result.tier.value for result in results)
        log_event(
            logger,
            logging.INFO,
            "matching_completed",
            records=len(results),
            green=tiers["green"],
            yellow=tiers["yellow"],
            red=tiers["red"],
        )
        return results

    def _match(self, record: RecordOut, catalog: list[CatalogEntry]) -> MatchResult:
        settings = get_settings()
        shortlist = self._retriever.retrieve(record, catalog, SHORTLIST_SIZE)
        scored = sorted(
            (self._scorer.score(record, entry) for entry in shortlist),
            key=lambda candidate: candidate.score,
            reverse=True,
        )
        top = scored[: settings.matching.top_k]
        best_score = top[0].score if top else 0.0
        tier = assign_tier(best_score, settings.tiers)
        return MatchResult(
            record_id=record.record_id,
            source_text=record.raw_text,
            tier=tier,
            candidates=top,
            # Green is auto-accept: pre-select the top candidate. Yellow/red
            # await a human decision through the review API.
            selected_catalog_id=top[0].catalog_id if (tier is Tier.green and top) else None,
            review=None,
            matched_at=datetime.now(timezone.utc),
        )

    def _load_catalog(self, conn: sqlite3.Connection) -> list[CatalogEntry]:
        try:
            rows = conn.execute(
                "SELECT catalog_id, description, category, unit FROM catalog"
            ).fetchall()
        except sqlite3.Error as exc:
            log_event(
                logger,
                logging.ERROR,
                "dependency_failure",
                dependency="sqlite",
                operation="load_catalog",
                error=str(exc),
            )
            raise DependencyError("could not load catalog") from exc
        return [
            CatalogEntry(
                catalog_id=row["catalog_id"],
                description=row["description"],
                category=row["category"],
                unit=row["unit"],
            )
            for row in rows
        ]

    def _load_records(self, conn: sqlite3.Connection) -> list[RecordOut]:
        try:
            rows = conn.execute(
                "SELECT record_id, raw_text, category, unit, quantity, ingested_at"
                " FROM records ORDER BY id"
            ).fetchall()
        except sqlite3.Error as exc:
            log_event(
                logger,
                logging.ERROR,
                "dependency_failure",
                dependency="sqlite",
                operation="load_records",
                error=str(exc),
            )
            raise DependencyError("could not load records") from exc
        return [
            RecordOut(
                record_id=row["record_id"],
                raw_text=row["raw_text"],
                category=row["category"] or None,
                unit=row["unit"] or None,
                quantity=row["quantity"] or None,
                ingested_at=row["ingested_at"],
            )
            for row in rows
        ]

    def _persist(self, conn: sqlite3.Connection, result: MatchResult) -> None:
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
                operation="persist_match",
                record_id=result.record_id,
                error=str(exc),
            )
            raise DependencyError("could not persist match") from exc
