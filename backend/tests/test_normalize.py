from app.services.matching.normalize import normalize


def test_expands_trade_abbreviations():
    assert normalize("CONC RM") == "concrete ready mix"
    assert normalize("GYP BD") == "gypsum board"
    assert normalize("STL") == "steel"


def test_splits_numbers_from_units():
    assert normalize("50MPA") == "50 mpa"
    assert normalize("140MM") == "140 mm"


def test_splits_hyphens_and_expands_w_slash():
    assert normalize("R-20") == "r 20"
    assert normalize("CONC W/ SLAG") == "concrete with slag"


def test_lowercases_and_collapses_whitespace():
    assert normalize("BATT  INSUL") == "batt insulation"


def test_is_idempotent():
    # Normalizing an already-normalized string must not change it.
    once = normalize("CONC RM 50MPA W/ 25% SLAG")
    assert normalize(once) == once


def test_flagship_source_and_catalog_align():
    # The source abbreviation and the catalog description must share the
    # discriminating tokens after normalization.
    src = normalize("CONC RM 50MPA W/ 25% SLAG").split()
    cat = normalize("Ready-mix concrete, 50 MPa, 25% slag").split()
    for tok in ("concrete", "ready", "mix", "50", "mpa", "25%", "slag"):
        assert tok in src
        assert tok in cat
