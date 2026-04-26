def test_users_default_page(fastapi_client):
    r = fastapi_client.get("/api/users")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    names = sorted(u["name"] for u in data["users"])
    assert names == ["Alice Anderson", "Bob"]


def test_users_search_alice(fastapi_client):
    r = fastapi_client.get("/api/users?search=alice")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["users"][0]["name"] == "Alice Anderson"


def test_users_pagination(fastapi_client):
    r = fastapi_client.get("/api/users?per_page=1&page=2")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2
    assert data["page"] == 2
    assert len(data["users"]) == 1
