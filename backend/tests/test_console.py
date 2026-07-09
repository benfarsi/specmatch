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
