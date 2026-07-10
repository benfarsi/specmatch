"""Text normalization for the matching engine.

Source records use heavy trade abbreviations ("CONC RM 50MPA W/ 25% SLAG")
while the catalog is spelled out ("Ready-mix concrete, 50 MPa, 25% slag").
Fuzzy string similarity on the *raw* text fails on these abbreviations, so we
normalize BOTH the source text and the catalog description through the same
pipeline before scoring. Applying identical rules to both sides is the point:
consistency matters more than perfection.

Pipeline: lowercase -> expand "w/" -> drop separator punctuation -> split
numbers from letters ("50mpa" -> "50 mpa") -> expand trade abbreviations.
"""

import re

# Trade abbreviation -> expansion, applied per whitespace token after
# lowercasing. Grouped by where they appear in the fixture data. This map is
# the domain-knowledge core of the engine; extend it as new abbreviations
# show up in the source records.
ABBREVIATIONS = {
    # concrete / masonry
    "conc": "concrete",
    "rm": "ready mix",              # "CONC RM" = ready-mix concrete
    "cmu": "concrete masonry unit",
    "lw": "lightweight",
    # insulation
    "insul": "insulation",
    "mw": "mineral wool",           # "BATT INSUL MW" = mineral wool batt
    # steel / structural
    "stl": "steel",
    "bm": "beam",                   # "STL BM W360X57"
    "chan": "channel",              # "STL CHAN C310X31"
    # gypsum / finishes
    "gyp": "gypsum",
    "bd": "board",                  # "GYP BD" = gypsum board
    "pnt": "paint",
    "int": "interior",             # "PNT INT LTX"
    "ext": "exterior",
    "ltx": "latex",
    # sitework
    "asph": "asphalt",
    "pvg": "paving",                # "ASPH PVG HL-3"
    # generic / misc
    "matl": "material",
    "mtl": "metal",
    "misc": "miscellaneous",
    "reinf": "reinforcing",
    "galv": "galvanized",
    "alum": "aluminum",
}

# Zero-width boundaries between a digit and a letter, both directions, so
# "50mpa" -> "50 mpa" and "r22" -> "r 22". Units and specs stay as separate
# tokens the scorer can match on.
_NUM_THEN_ALPHA = re.compile(r"(?<=\d)(?=[a-z])")
_ALPHA_THEN_NUM = re.compile(r"(?<=[a-z])(?=\d)")


def normalize(text: str) -> str:
    """Normalize one description for matching. Idempotent and pure."""
    text = text.lower()
    text = text.replace("w/", " with ")
    text = re.sub(r'[,"()\-]', " ", text)        # drop separators, split hyphens
    text = _NUM_THEN_ALPHA.sub(" ", text)
    text = _ALPHA_THEN_NUM.sub(" ", text)
    tokens = (ABBREVIATIONS.get(tok, tok) for tok in text.split())
    return " ".join(tokens)
