"""Match endpoints, completed to the frozen contracts in models/schemas.py."""

from fastapi import APIRouter, HTTPException, Query

from app.core.db import get_conn
from app.models.schemas import MatchesResponse, MatchResult, ReviewRequest, Tier
from app.services import matches as matches_repo

router = APIRouter()


@router.get("/matches", response_model=MatchesResponse)
def list_matches(
    tier: Tier | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> MatchesResponse:
    conn = get_conn()
    try:
        total, items = matches_repo.list_matches(conn, tier, limit, offset)
    finally:
        conn.close()
    return MatchesResponse(total=total, items=items)


@router.post("/matches/{record_id}/review", response_model=MatchResult)
def review_match(record_id: str, body: ReviewRequest) -> MatchResult:
    conn = get_conn()
    try:
        return matches_repo.apply_review(conn, record_id, body)
    except LookupError:
        raise HTTPException(status_code=404, detail=f"no match for record {record_id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        conn.close()
