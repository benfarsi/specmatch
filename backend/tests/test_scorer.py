from datetime import datetime, timezone

from app.models.schemas import CatalogEntry, RecordOut
from app.services.matching.scorer import (
    WeightedScorer,
    category_agreement,
    string_similarity,
    unit_compatibility,
)

NOW = datetime.now(timezone.utc)


def rec(text, category=None, unit=None):
    return RecordOut(
        record_id="SRC-TEST", raw_text=text, category=category, unit=unit, ingested_at=NOW
    )


def entry(desc, category, unit, cid="CAT-TEST"):
    return CatalogEntry(catalog_id=cid, description=desc, category=category, unit=unit)


def test_string_similarity_high_for_good_match():
    s = string_similarity(
        rec("CONC RM 50MPA W/ 25% SLAG"),
        entry("Ready-mix concrete, 50 MPa, 25% slag", "Concrete", "m3"),
    )
    assert s > 0.9


def test_string_similarity_low_for_vague_abbreviation():
    # A bare "STL" must not score a confident match against a full spec.
    s = string_similarity(rec("STL"), entry("Steel beam W360x57", "Structural Steel", "kg"))
    assert s < 0.5


def test_category_agreement_match_mismatch_and_blank():
    e = entry("x", "Concrete", "m3")
    assert category_agreement(rec("x", category="Concrete"), e) == 1.0
    assert category_agreement(rec("x", category="Masonry"), e) == 0.0
    assert category_agreement(rec("x", category=None), e) == 0.5  # unknown, not wrong


def test_unit_compatibility_match_mismatch_blank_and_mass_group():
    e = entry("x", "Concrete", "m3")
    assert unit_compatibility(rec("x", unit="m3"), e) == 1.0
    assert unit_compatibility(rec("x", unit="kg"), e) == 0.0
    assert unit_compatibility(rec("x", unit=None), e) == 0.5
    # kg and t both measure mass -> compatible
    assert unit_compatibility(rec("x", unit="kg"), entry("x", "Structural Steel", "t")) == 1.0


def test_composite_high_for_good_match_with_all_signals():
    cand = WeightedScorer().score(
        rec("CONC RM 50MPA W/ 25% SLAG", "Concrete", "m3"),
        entry("Ready-mix concrete, 50 MPa, 25% slag", "Concrete", "m3", "CAT-0041"),
    )
    assert cand.catalog_id == "CAT-0041"
    assert cand.score > 0.85
    assert set(cand.signals) == {
        "string_similarity",
        "category_agreement",
        "unit_compatibility",
    }


def test_wrong_category_and_unit_sink_a_good_string_match():
    # "Right words, wrong domain" must not be confident: disagreeing
    # category and unit pull a decent string match down into red territory.
    cand = WeightedScorer().score(
        rec("CONC RM 50MPA W/ 25% SLAG", "Concrete", "m3"),
        entry("Concrete sealer, 50%", "Finishes", "unit"),
    )
    assert cand.score < 0.6


def test_score_stays_within_unit_interval():
    cand = WeightedScorer().score(
        rec("anything at all", "Concrete", "m3"),
        entry("Ready-mix concrete, 20 MPa", "Concrete", "m3"),
    )
    assert 0.0 <= cand.score <= 1.0
