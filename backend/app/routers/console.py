"""Server-rendered review console (Jinja2)."""

from pathlib import Path

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from fastapi.templating import Jinja2Templates

from app.core.db import get_conn
from app.models.schemas import ReviewAction, ReviewRequest, Tier
from app.services import matches as matches_repo

router = APIRouter()

templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/", response_class=HTMLResponse)
def record_table(request: Request, category: str | None = Query(default=None)):
    category = category or None  # "" (the All option) means no filter, same as absent
    conn = get_conn()
    try:
        categories = [
            row["category"]
            for row in conn.execute(
                "SELECT DISTINCT category FROM records"
                " WHERE category IS NOT NULL AND category != '' ORDER BY category"
            ).fetchall()
        ]
        if category is not None:
            rows = conn.execute(
                "SELECT record_id, raw_text, category, unit, quantity FROM records"
                " WHERE category = ? ORDER BY id",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT record_id, raw_text, category, unit, quantity FROM records"
                " ORDER BY id"
            ).fetchall()
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "records.html",
        {
            "records": rows,
            "categories": categories,
            "selected_category": category,
        },
    )


@router.get("/review", response_class=HTMLResponse)
def review_panel(request: Request):
    conn = get_conn()
    try:
        counts = matches_repo.tier_counts(conn)
        _, yellow = matches_repo.list_matches(conn, Tier.yellow, limit=500, offset=0)
        _, red = matches_repo.list_matches(conn, Tier.red, limit=500, offset=0)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "counts": counts,
            # Ordered queues rendered as grouped sections in the template.
            "queues": [("yellow", yellow), ("red", red)],
        },
    )


@router.post("/review/{record_id}")
def submit_review(
    record_id: str,
    action: str = Form(...),
    catalog_id: str | None = Form(default=None),
    note: str | None = Form(default=None),
):
    conn = get_conn()
    try:
        request = ReviewRequest(
            action=ReviewAction(action),
            catalog_id=catalog_id or None,
            note=note or None,
        )
        matches_repo.apply_review(conn, record_id, request)
    except (LookupError, ValueError):
        # Invalid action/target from a hand-crafted request: no-op, fall
        # through to re-render. DependencyError still propagates.
        pass
    finally:
        conn.close()
    # POST-Redirect-GET so a refresh doesn't re-submit the review.
    return RedirectResponse("/review", status_code=303)
