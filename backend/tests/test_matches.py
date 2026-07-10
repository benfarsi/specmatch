"""Contract tests for the /matches endpoints (replaces test_matches_stub)."""

MATCH_KEYS = {
    "record_id",
    "source_text",
    "tier",
    "candidates",
    "selected_catalog_id",
    "review",
    "matched_at",
}


def test_list_matches_shape(client):
    resp = client.get("/matches")
    assert resp.status_code == 200
    body = resp.json()
    # total covers every matched record; default limit caps the page.
    assert body["total"] == client.get("/health").json()["matched"]
    assert len(body["items"]) <= 50
    item = body["items"][0]
    assert MATCH_KEYS <= set(item)
    assert MATCH_KEYS - {"selected_catalog_id", "review"} <= {k for k, v in item.items()}


def test_list_matches_tier_filter(client):
    red_count = client.get("/health").json()["tiers"]["red"]
    body = client.get("/matches", params={"tier": "red", "limit": 500}).json()
    assert body["total"] == red_count
    assert all(item["tier"] == "red" for item in body["items"])


def test_list_matches_pagination_is_disjoint(client):
    page1 = client.get("/matches", params={"limit": 5, "offset": 0}).json()
    page2 = client.get("/matches", params={"limit": 5, "offset": 5}).json()
    assert len(page1["items"]) == 5
    assert len(page2["items"]) == 5
    ids1 = {item["record_id"] for item in page1["items"]}
    ids2 = {item["record_id"] for item in page2["items"]}
    assert ids1.isdisjoint(ids2)


def test_review_accept_persists_and_selects_top(client):
    target = client.get("/matches", params={"tier": "yellow", "limit": 1}).json()["items"][0]
    record_id = target["record_id"]
    top_id = target["candidates"][0]["catalog_id"]

    resp = client.post(f"/matches/{record_id}/review", json={"action": "accept"})
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["review"]["action"] == "accept"
    assert updated["review"]["reviewed_at"] is not None
    assert updated["selected_catalog_id"] == top_id

    # Persisted: re-fetch and confirm the review stuck.
    all_yellow = client.get("/matches", params={"tier": "yellow", "limit": 500}).json()["items"]
    persisted = next(m for m in all_yellow if m["record_id"] == record_id)
    assert persisted["review"]["action"] == "accept"
    assert persisted["selected_catalog_id"] == top_id


def test_review_override_rejects_unlisted_candidate(client):
    target = client.get("/matches", params={"tier": "yellow", "limit": 1}).json()["items"][0]
    resp = client.post(
        f"/matches/{target['record_id']}/review",
        json={"action": "override", "catalog_id": "CAT-DOES-NOT-EXIST"},
    )
    assert resp.status_code == 400


def test_review_unknown_record_returns_404(client):
    resp = client.post("/matches/NO-SUCH-RECORD/review", json={"action": "reject"})
    assert resp.status_code == 404
