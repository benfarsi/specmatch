"""Candidate scoring.

Combines three signals into a composite confidence score in [0, 1]:

  - string_similarity : rapidfuzz token_sort_ratio over normalized text.
        token_sort_ratio (not token_set_ratio) because it stays honest about
        length -- a bare abbreviation like "STL" must not score a perfect
        match against a full catalog description.
  - category_agreement: 1.0 match / 0.0 mismatch / 0.5 when the source has
        no category (unknown is neither right nor wrong).
  - unit_compatibility: 1.0 compatible / 0.0 not / 0.5 when the source has
        no unit.

The signal weights come from Settings.matching.weights (config/settings.yaml)
and are never hardcoded here. The composite is the weighted average of the
signals, normalized by the total weight so it stays in [0, 1] even if the
configured weights don't sum to 1.
"""

from rapidfuzz import fuzz

from app.config import get_settings
from app.models.schemas import Candidate, CatalogEntry, RecordOut
from app.services.matching.interfaces import CandidateScorer
from app.services.matching.normalize import normalize

# Units that measure the same physical quantity are treated as compatible.
# Everything else must match exactly (length/area/volume/count are distinct).
_COMPATIBLE_UNITS: list[set[str]] = [
    {"kg", "t"},  # mass
]


def string_similarity(record: RecordOut, entry: CatalogEntry) -> float:
    return fuzz.token_sort_ratio(normalize(record.raw_text), normalize(entry.description)) / 100.0


def category_agreement(record: RecordOut, entry: CatalogEntry) -> float:
    if not record.category:
        return 0.5
    return 1.0 if record.category.strip().lower() == entry.category.strip().lower() else 0.0


def _units_compatible(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    if a == b:
        return True
    return any(a in group and b in group for group in _COMPATIBLE_UNITS)


def unit_compatibility(record: RecordOut, entry: CatalogEntry) -> float:
    if not record.unit:
        return 0.5
    return 1.0 if _units_compatible(record.unit, entry.unit) else 0.0


class WeightedScorer(CandidateScorer):
    """Composite scorer over the three configured signals."""

    def score(self, record: RecordOut, entry: CatalogEntry) -> Candidate:
        weights = get_settings().matching.weights
        signals = {
            "string_similarity": string_similarity(record, entry),
            "category_agreement": category_agreement(record, entry),
            "unit_compatibility": unit_compatibility(record, entry),
        }
        total_weight = sum(weights[name] for name in signals)
        composite = sum(weights[name] * value for name, value in signals.items()) / total_weight
        return Candidate(
            catalog_id=entry.catalog_id,
            description=entry.description,
            score=round(composite, 4),
            signals={name: round(value, 4) for name, value in signals.items()},
        )
