def test_index_returns_html(fastapi_client):
    r = fastapi_client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()
