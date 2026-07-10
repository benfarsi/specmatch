from datetime import datetime, timezone

from app.models.schemas import CatalogEntry, RecordOut
from app.services.matching.retriever import LexicalRetriever

NOW = datetime.now(timezone.utc)

CATALOG = [
    CatalogEntry(
        catalog_id="CAT-1",
        description="Ready-mix concrete, 50 MPa, 25% slag",
        category="Concrete",
        unit="m3",
    ),
    CatalogEntry(
        catalog_id="CAT-2",
        description="Gypsum board, 15.9 mm, Type X fire rated",
        category="Gypsum",
        unit="m2",
    ),
    CatalogEntry(
        catalog_id="CAT-3",
        description="Steel beam W360x57",
        category="Structural Steel",
        unit="kg",
    ),
    CatalogEntry(
        catalog_id="CAT-4",
        description="Mineral wool batt insulation, R-20",
        category="Insulation",
        unit="m2",
    ),
]


def rec(text: str) -> RecordOut:
    return RecordOut(record_id="SRC-T", raw_text=text, ingested_at=NOW)


def test_retrieves_best_match_first():
    out = LexicalRetriever().retrieve(rec("CONC RM 50MPA W/ 25% SLAG"), CATALOG, limit=3)
    assert out[0].catalog_id == "CAT-1"


def test_matches_across_abbreviation_and_reordering():
    out = LexicalRetriever().retrieve(rec("BATT INSUL MW R-20"), CATALOG, limit=1)
    assert out[0].catalog_id == "CAT-4"


def test_respects_limit():
    out = LexicalRetriever().retrieve(rec("CONC RM 50MPA"), CATALOG, limit=2)
    assert len(out) == 2
