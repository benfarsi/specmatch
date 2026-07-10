import os
import tempfile
from collections import Counter

import pytest

from app.core.db import get_conn
from app.models.schemas import ReviewAction, ReviewRequest, Tier
from app.services import matches as matches_repo
from app.services.ingest import run_ingest
from app.services.matching.engine import LexicalMatchingEngine


@pytest.fixture(scope="module")
def matches():
    """Ingest + match against an isolated DB; return results by record_id.

    Restores DATA_DIR afterwards so the session-scoped `client` fixture keeps
    pointing at its own database.
    """
    previous = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = tempfile.mkdtemp()
    try:
        run_ingest()
        results = LexicalMatchingEngine().match_all()
    finally:
        if previous is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = previous
    return {result.record_id: result for result in results}


def test_every_record_is_matched(matches):
    assert len(matches) == 150


def test_distribution_is_meaningful(matches):
    dist = Counter(m.tier.value for m in matches.values())
    assert sum(dist.values()) == 150
    # Not everything dumped into one bucket -- all three tiers are populated.
    assert dist["green"] > 0
    assert dist["yellow"] > 0
    assert dist["red"] > 0
    # Green is the plurality, per the README's reported distribution.
    assert dist["green"] == max(dist.values())


def test_confident_insulation_match_is_green(matches):
    m = matches["SRC-0001"]  # "BATT INSUL MW R-22"
    assert m.tier is Tier.green
    assert m.candidates[0].catalog_id == "CAT-0186"


def test_gypsum_imperial_thickness_matches_metric_and_is_green(matches):
    m = matches["SRC-0006"]  # "GYP BD 5/8in TYPE X" -> 15.9 mm
    assert m.tier is Tier.green
    assert "15.9 mm" in m.candidates[0].description


def test_vague_record_lands_in_red(matches):
    # Deliberate red: "MATL PER DWG S-501" has no honest catalog match.
    assert matches["SRC-0002"].tier is Tier.red


def test_candidate_has_full_signal_breakdown(matches):
    top = matches["SRC-0001"].candidates[0]
    assert set(top.signals) == {
        "string_similarity",
        "category_agreement",
        "unit_compatibility",
    }
    assert 0.0 <= top.score <= 1.0


def test_green_record_auto_selects_top_candidate(matches):
    m = matches["SRC-0001"]
    assert m.selected_catalog_id == m.candidates[0].catalog_id


def test_persists_at_most_top_k_candidates(matches):
    # config/settings.yaml sets top_k = 5.
    assert all(len(m.candidates) <= 5 for m in matches.values())


def test_rematch_preserves_persisted_reviews():
    # Every startup re-runs match_all (see main.lifespan), so a container
    # restart must not discard a persisted human review: the reviewer's
    # decision is authoritative and survives re-matching.
    previous = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = tempfile.mkdtemp()
    try:
        run_ingest()
        engine = LexicalMatchingEngine()
        engine.match_all()
        conn = get_conn()
        try:
            matches_repo.apply_review(
                conn,
                "SRC-0001",
                ReviewRequest(action=ReviewAction.accept, note="confirmed by reviewer"),
            )
        finally:
            conn.close()

        engine.match_all()  # what a restart does

        conn = get_conn()
        try:
            match = matches_repo.get_match(conn, "SRC-0001")
        finally:
            conn.close()
    finally:
        if previous is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = previous
    assert match.review is not None
    assert match.review.action is ReviewAction.accept
    assert match.review.note == "confirmed by reviewer"
