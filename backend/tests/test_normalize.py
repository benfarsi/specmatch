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


def test_converts_gypsum_imperial_thickness_to_metric():
    # Source writes gypsum thickness in inches; catalog uses millimetres.
    assert normalize("GYP BD 5/8in TYPE X") == "gypsum board 15.9 mm type x"
    assert "12.7 mm" in normalize("GYP BD 1/2IN TYPE X")


def test_hss_bare_fractions_are_not_converted():
    # HSS uses bare fractions with no trailing "in" (and the catalog matches
    # that form), so they must be left alone -- converting them would break
    # ~40 steel matches.
    out = normalize("STL HSS 8X8X1/2 GR B")
    assert "1/2" in out
    assert "12.7 mm" not in out


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
