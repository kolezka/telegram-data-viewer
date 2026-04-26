def test_stats_endpoint(fastapi_client):
    r = fastapi_client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_databases"] == 1
    assert data["decrypted_databases"] == 1
    assert data["total_messages"] == 3
    assert data["total_chats"] == 1
    assert "account-1000000001" in data["databases"]
    db = data["databases"]["account-1000000001"]
    assert db["decrypted"] is True
    assert db["message_count"] == 3
    assert db["tables"] == 2
