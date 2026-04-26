def test_app_starts_and_serves_openapi(fastapi_client):
    r = fastapi_client.get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "tg-viewer"


def test_state_is_loaded(fastapi_client):
    # The TestClient context triggers lifespan startup, so app_state must exist.
    app = fastapi_client.app
    assert app.state.app_state.databases  # non-empty for the fixture
