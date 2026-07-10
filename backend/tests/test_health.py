def test_health_shape(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["records"] == 150
    # Matching runs at startup, so every record is matched into a tier.
    assert body["matched"] == 150
    tiers = body["tiers"]
    assert set(tiers) == {"green", "yellow", "red"}
    assert all(isinstance(v, int) and v >= 0 for v in tiers.values())
    assert sum(tiers.values()) == body["matched"]
