"""Candidate retrieval.

Narrows the full catalog to the entries worth scoring for one source record,
ranking by rapidfuzz string similarity over normalized text. Retrieval is
lexical and sits behind the CandidateRetriever interface, so an embedding or
TF-IDF retriever could be swapped in without touching the engine.

We score against the whole catalog (no category pre-filter): category is a
weighted signal in the scorer, not a hard gate, so blank/mislabeled source
categories don't hide the right candidate. To keep that affordable, each
catalog description is normalized once and cached by catalog_id.
"""

from rapidfuzz import fuzz, process

from app.models.schemas import CatalogEntry, RecordOut
from app.services.matching.interfaces import CandidateRetriever
from app.services.matching.normalize import normalize


class LexicalRetriever(CandidateRetriever):
    """Top-k retrieval by token_sort_ratio over normalized descriptions."""

    def __init__(self) -> None:
        self._normalized: dict[str, str] = {}

    def _norm_entry(self, entry: CatalogEntry) -> str:
        cached = self._normalized.get(entry.catalog_id)
        if cached is None:
            cached = normalize(entry.description)
            self._normalized[entry.catalog_id] = cached
        return cached

    def retrieve(
        self, record: RecordOut, catalog: list[CatalogEntry], limit: int
    ) -> list[CatalogEntry]:
        query = normalize(record.raw_text)
        choices = [self._norm_entry(entry) for entry in catalog]
        # process.extract returns (choice, score, index) tuples, best first.
        ranked = process.extract(
            query, choices, scorer=fuzz.token_sort_ratio, limit=limit
        )
        return [catalog[index] for _, _, index in ranked]
