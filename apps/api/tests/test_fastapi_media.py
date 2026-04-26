def test_media_catalog(fastapi_client):
    r = fastapi_client.get("/api/media")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["counts"]["all"] == 1
    assert data["counts"]["photo"] == 1
    assert data["media"][0]["filename"] == "test.jpg"
    assert data["media"][0]["account"] == "account-1000000001"


def test_media_catalog_type_filter(fastapi_client):
    r = fastapi_client.get("/api/media?type=video")
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_media_file_serves_jpeg(fastapi_client):
    r = fastapi_client.get("/api/media/account-1000000001/test.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/jpeg")
    assert r.content == b"\xff\xd8\xff"


def test_media_file_rejects_bad_account(fastapi_client):
    r = fastapi_client.get("/api/media/notanaccount/test.jpg")
    assert r.status_code == 400


def test_media_file_rejects_traversal(fastapi_client):
    r = fastapi_client.get("/api/media/account-1000000001/..%2Fevil")
    assert r.status_code in (400, 404)


def test_media_file_404_when_missing(fastapi_client):
    r = fastapi_client.get("/api/media/account-1000000001/missing.jpg")
    assert r.status_code == 404
