def test_export_data(fastapi_client):
    r = fastapi_client.get("/api/export-data")
    assert r.status_code == 200
    data = r.json()
    assert "databases" in data
    assert "account-1000000001" in data["databases"]
    assert "total_media" in data
    assert data["backup_size"] == "15 GB"  # pinned Flask quirk; FastAPI port keeps for parity
