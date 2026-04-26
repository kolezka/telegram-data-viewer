def test_chats_list(fastapi_client):
    r = fastapi_client.get("/api/chats")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    chat_111 = next(c for c in data if c["id"] == "111")
    assert chat_111["name"] == "Alice Anderson"
    assert chat_111["message_count"] == 2
    assert chat_111["type"] == "user"


def test_chats_search(fastapi_client):
    r = fastapi_client.get("/api/chats?search=alice")
    assert r.status_code == 200
    data = r.json()
    assert all(
        "alice" in c["name"].lower() or "alice" in (c["username"] or "").lower()
        for c in data
    )


def test_chats_type_filter(fastapi_client):
    r = fastapi_client.get("/api/chats?type=secret")
    assert r.status_code == 200
    # No secret chats in fixture, so list is empty (not 404)
    assert r.json() == []


def test_chats_user_id_filter(fastapi_client):
    r = fastapi_client.get("/api/chats?user_id=111")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "111"


def test_chats_databases_field_is_list(fastapi_client):
    # The Flask compute uses a set internally; output must be JSON-serializable list.
    r = fastapi_client.get("/api/chats")
    assert r.status_code == 200
    chat = next(c for c in r.json() if c["id"] == "111")
    assert isinstance(chat["databases"], list)
