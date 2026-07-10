import re


def test_record_table_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "SRC-" in resp.text


def test_category_filter_narrows_results(client):
    resp = client.get("/", params={"category": "Concrete"})
    assert resp.status_code == 200
    assert "CONC" in resp.text
    assert "GYP BD" not in resp.text


def test_all_categories_shows_all_records(client):
    # Issue #3: selecting "All categories" must show every record, not empty
    # the table. Read the value that option actually submits and post it
    # back, mimicking the dropdown round-trip.
    home = client.get("/")
    total = len(re.findall(r"SRC-\d+", home.text))  # all records, unfiltered
    assert total > 0
    match = re.search(r'<option value="([^"]*)"[^>]*>\s*All categories', home.text)
    assert match is not None, "All categories option not found"
    resp = client.get("/", params={"category": match.group(1)})
    assert len(re.findall(r"SRC-\d+", resp.text)) == total


def test_review_page_shows_counts_and_queues(client):
    resp = client.get("/review")
    assert resp.status_code == 200
    body = resp.text
    assert "Green" in body and "Yellow" in body and "Red" in body
    assert "queue" in body  # the grouped tier sections


def test_review_filters_by_tier_and_has_links(client):
    body = client.get("/review").text
    # the pills are real filter links now, not inert spans
    assert 'href="/review?tier=green"' in body
    assert 'href="/review?tier=yellow"' in body
    assert 'href="/review?tier=red"' in body


def test_review_green_tab_is_read_only(client):
    body = client.get("/review", params={"tier": "green"}).text
    assert "green queue" in body
    assert "Auto-accepted" in body
    # green is already auto-accepted: no action buttons
    assert 'value="accept"' not in body
    assert 'value="reject"' not in body


def test_review_yellow_tab_keeps_action_buttons(client):
    body = client.get("/review", params={"tier": "yellow"}).text
    assert "yellow queue" in body
    assert 'value="accept"' in body
    assert 'value="reject"' in body


def test_review_action_persists_via_console(client):
    yellow = client.get("/matches", params={"tier": "yellow", "limit": 1}).json()["items"][0]
    record_id = yellow["record_id"]
    resp = client.post(
        f"/review/{record_id}", data={"action": "accept"}, follow_redirects=False
    )
    assert resp.status_code == 303  # POST-Redirect-GET
    persisted = next(
        m
        for m in client.get("/matches", params={"tier": "yellow", "limit": 500}).json()["items"]
        if m["record_id"] == record_id
    )
    assert persisted["review"]["action"] == "accept"
