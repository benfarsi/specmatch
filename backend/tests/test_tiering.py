from app.config import TierThresholds
from app.models.schemas import Tier
from app.services.matching.tiering import assign_tier

THRESHOLDS = TierThresholds(accept_min=0.85, review_min=0.60)


def test_high_score_is_green():
    assert assign_tier(0.95, THRESHOLDS) is Tier.green


def test_mid_score_is_yellow():
    assert assign_tier(0.70, THRESHOLDS) is Tier.yellow


def test_low_score_is_red():
    assert assign_tier(0.30, THRESHOLDS) is Tier.red


def test_score_exactly_at_accept_min_is_green():
    # Issue #2: both thresholds are inclusive lower bounds (see
    # config/settings.yaml), so a score exactly equal to accept_min must be
    # green, not yellow.
    assert assign_tier(0.85, THRESHOLDS) is Tier.green


def test_score_exactly_at_review_min_is_yellow():
    # The symmetric boundary: a score exactly equal to review_min must be
    # yellow, not red. Guards against fixing the accept_min boundary by
    # flipping the wrong operator.
    assert assign_tier(0.60, THRESHOLDS) is Tier.yellow
