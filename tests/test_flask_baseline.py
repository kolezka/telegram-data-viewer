"""Characterization tests for the current Flask webui.py.

These pin down the current behavior so we can verify FastAPI parity.
Deleted in the final task once the Flask app is removed.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def flask_client(mini_data_dir: Path):
    """Flask test client with mini-parsed loaded into module globals."""
    import webui as flask_app_module

    flask_app_module.load_telegram_data(str(mini_data_dir))
    # The fixture's summary.json carries a relative backup_dir; force it absolute
    # so /api/media/... works regardless of where pytest is invoked from.
    flask_app_module.backup_dir = mini_data_dir
    flask_app_module.app.config["TESTING"] = True
    with flask_app_module.app.test_client() as client:
        yield client


def test_index_returns_html(flask_client):
    r = flask_client.get("/")
    assert r.status_code == 200
    assert b"<html" in r.data.lower()


def test_databases_endpoint_lists_one_account(flask_client):
    r = flask_client.get("/api/databases")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "account-1000000001"
    assert data[0]["decrypted"] is True
    assert data[0]["message_count"] == 3


def test_database_detail_404_for_unknown(flask_client):
    r = flask_client.get("/api/database/account-doesnotexist")
    assert r.status_code == 404


def test_database_detail_returns_payload(flask_client):
    r = flask_client.get("/api/database/account-1000000001")
    assert r.status_code == 200
    data = r.get_json()
    assert data["decrypted"] is True
    assert len(data["messages"]) == 3


def test_stats_endpoint(flask_client):
    r = flask_client.get("/api/stats")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total_databases"] == 1
    assert data["decrypted_databases"] == 1
    assert data["total_messages"] == 3
    assert "account-1000000001" in data["databases"]


def test_users_endpoint(flask_client):
    r = flask_client.get("/api/users")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    names = [u["name"] for u in data["users"]]
    assert "Alice Anderson" in names
    assert "Bob" in names


def test_users_search(flask_client):
    r = flask_client.get("/api/users?search=alice")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["users"][0]["name"] == "Alice Anderson"


def test_chats_endpoint(flask_client):
    r = flask_client.get("/api/chats")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
    chat_111 = next(c for c in data if c["id"] == "111")
    assert chat_111["name"] == "Alice Anderson"
    assert chat_111["message_count"] == 2


def test_messages_endpoint(flask_client):
    r = flask_client.get("/api/messages?per_page=10")
    assert r.status_code == 200
    data = r.get_json()
    # 3 t7 messages + 1 fts (peer 222 has both, but text differs so no dedup)
    assert data["total"] == 4
    # Sorted desc by timestamp; first should be 1700000020
    assert data["messages"][0]["timestamp"] == 1700000020


def test_messages_filter_by_peer(flask_client):
    r = flask_client.get("/api/messages?peer_id=111&per_page=10")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2


def test_media_catalog(flask_client):
    r = flask_client.get("/api/media")
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 1
    assert data["counts"]["all"] == 1
    assert data["counts"]["photo"] == 1
    assert data["media"][0]["filename"] == "test.jpg"
    assert data["media"][0]["account"] == "account-1000000001"


def test_media_file_serves_jpeg(flask_client):
    r = flask_client.get("/api/media/account-1000000001/test.jpg")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("image/jpeg")
    assert r.data == b"\xff\xd8\xff"


def test_media_file_rejects_traversal(flask_client):
    r = flask_client.get("/api/media/account-1000000001/..%2Fevil")
    assert r.status_code in (400, 404)


def test_media_file_rejects_bad_account(flask_client):
    r = flask_client.get("/api/media/notanaccount/test.jpg")
    assert r.status_code == 400


def test_export_data_endpoint(flask_client):
    r = flask_client.get("/api/export-data")
    assert r.status_code == 200
    data = r.get_json()
    assert "databases" in data
    assert "account-1000000001" in data["databases"]
