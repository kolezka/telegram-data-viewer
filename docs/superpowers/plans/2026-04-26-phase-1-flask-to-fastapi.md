# Phase 1: Flask → FastAPI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Flask web UI backend (`webui.py`, 665 lines, 10 routes) with a FastAPI app that serves the same JSON contract over the same JSON-file-backed data, so the existing `templates/index.html` keeps working unchanged. Exposes auto-generated OpenAPI at `/docs` so Phase 2 (React + Bun) can codegen TypeScript types.

**Architecture:** Restructure the single-file Flask app into a `webui/` Python package with a FastAPI app factory, Pydantic response models, and per-resource routers. Module-level globals become `app.state` set during `lifespan` startup. The existing inline-JS frontend in `templates/index.html` continues to be served as-is via a transitional `pages` router; no frontend changes happen in Phase 1. SQLCipher decryption and Postbox parsing are untouched — they still run via `tg_appstore_decrypt.py` / `postbox_parser.py` and write JSON files into `parsed_data/`.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, uvicorn, pytest, httpx (TestClient).

**Out of scope (deferred to Phase 2):** React frontend, Bun build tooling, OpenAPI → TypeScript codegen, deletion of `templates/index.html`.

---

## File Structure

**Created:**

| Path | Responsibility |
|------|----------------|
| `webui/__init__.py` | Package marker; re-exports `create_app` |
| `webui/__main__.py` | CLI entry: `python -m webui <data_dir> --host --port` |
| `webui/app.py` | `create_app()` factory + `lifespan` that loads data into `app.state` |
| `webui/state.py` | `AppState` dataclass holding `telegram_data`, `export_dir`, `backup_dir` |
| `webui/loader.py` | `load_telegram_data()` and `load_parsed_data()` — extracted verbatim from `webui.py` |
| `webui/mime.py` | `detect_mime()` + `MIME_SIGNATURES` — extracted from `webui.py` |
| `webui/peer.py` | `peer_type()` helper — extracted from `webui.py` |
| `webui/chats_logic.py` | `compute_chats()` — pure function returning the chats list (used by both `/api/chats` and `/api/stats` to avoid Flask's "call my own endpoint" trick) |
| `webui/models.py` | All Pydantic response models (`User`, `UsersPage`, `Database`, `Chat`, `Message`, `MessagesPage`, `MediaItem`, `MediaPage`, `Stats`, `ExportData`) |
| `webui/routers/__init__.py` | Router package marker |
| `webui/routers/pages.py` | `GET /` — serves `templates/index.html` via `HTMLResponse` (transitional) |
| `webui/routers/databases.py` | `GET /api/databases`, `GET /api/database/{db_name}` |
| `webui/routers/messages.py` | `GET /api/messages` |
| `webui/routers/chats.py` | `GET /api/chats` |
| `webui/routers/users.py` | `GET /api/users` |
| `webui/routers/media.py` | `GET /api/media`, `GET /api/media/{account_id}/{filename}` |
| `webui/routers/stats.py` | `GET /api/stats` |
| `webui/routers/export_data.py` | `GET /api/export-data` |
| `tests/__init__.py` | Test package marker |
| `tests/conftest.py` | Pytest fixtures: `flask_client` (current app, used by characterization tests), `fastapi_client` (new app), `mini_data_dir` (path to fixture parsed_data) |
| `tests/fixtures/mini-parsed/summary.json` | Tiny fixture summary |
| `tests/fixtures/mini-parsed/account-1000000001/messages.json` | 3 fake messages |
| `tests/fixtures/mini-parsed/account-1000000001/peers.json` | 2 fake peers |
| `tests/fixtures/mini-parsed/account-1000000001/conversations_index.json` | 1 conversation |
| `tests/fixtures/mini-parsed/account-1000000001/messages_fts.json` | 1 FTS message |
| `tests/fixtures/mini-parsed/account-1000000001/media_catalog.json` | 1 media item |
| `tests/fixtures/mini-parsed/account-1000000001/postbox/media/test.jpg` | 3-byte JPEG (`FF D8 FF`) for MIME detection |
| `tests/test_flask_baseline.py` | Characterization tests against current Flask app — captures behavior before porting |
| `tests/test_fastapi_databases.py` | FastAPI parity tests — same assertions as `test_flask_baseline.py` for `/api/databases*` |
| `tests/test_fastapi_stats.py` | FastAPI parity tests for `/api/stats` |
| `tests/test_fastapi_users.py` | FastAPI parity tests for `/api/users` |
| `tests/test_fastapi_chats.py` | FastAPI parity tests for `/api/chats` |
| `tests/test_fastapi_messages.py` | FastAPI parity tests for `/api/messages` |
| `tests/test_fastapi_media.py` | FastAPI parity tests for `/api/media` (catalog + file) |
| `tests/test_fastapi_export_data.py` | FastAPI parity tests for `/api/export-data` |
| `tests/test_fastapi_pages.py` | FastAPI parity test for `GET /` |

**Modified:**

| Path | Change |
|------|--------|
| `requirements.txt` | Add `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `pydantic>=2.6`. Add test deps `pytest>=8`, `httpx>=0.27`. Remove `flask`, `jinja2` (in final task only). |
| `tg-viewer:212` | Change `python3 "$WEBUI_SCRIPT" "$data_dir" --host "$host" --port "$port"` to `python3 -m webui "$data_dir" --host "$host" --port "$port"` |
| `README.md` | Mention OpenAPI docs at `http://host:port/docs` and ReDoc at `/redoc` |

**Deleted (final task only):**

| Path | Reason |
|------|--------|
| `webui.py` | Replaced by `webui/` package |

---

## Conventions

- **Test runner:** `pytest tests/ -v` from repo root.
- **TDD cycle:** every feature task = write test → run failing → implement → run passing → commit.
- **Commits:** small (one per task), conventional-commit prefixes (`feat`, `refactor`, `test`, `chore`).
- **Pydantic:** v2 idioms — `model_config = ConfigDict(extra='allow')` for flexible message dicts that have unknown shape.
- **No mutation of loaded JSON data** in routers (the current Flask `get_messages` does `msg['_database'] = db` in place, which is a latent bug we fix during the port).
- **Module-level state is forbidden** in the new package — use `app.state` and pass via `Request` or a `Depends` provider.

---

## Task 1: Add test infrastructure and tiny fixture

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/mini-parsed/summary.json`
- Create: `tests/fixtures/mini-parsed/account-1000000001/messages.json`
- Create: `tests/fixtures/mini-parsed/account-1000000001/peers.json`
- Create: `tests/fixtures/mini-parsed/account-1000000001/conversations_index.json`
- Create: `tests/fixtures/mini-parsed/account-1000000001/messages_fts.json`
- Create: `tests/fixtures/mini-parsed/account-1000000001/media_catalog.json`
- Create: `tests/fixtures/mini-parsed/account-1000000001/postbox/media/test.jpg`
- Modify: `requirements.txt`

- [ ] **Step 1: Add pytest and httpx to requirements.txt**

Append to `requirements.txt`:

```
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 2: Install the new deps**

Run: `pip install -r requirements.txt`
Expected: pytest and httpx installed.

- [ ] **Step 3: Create empty test package marker**

Write `tests/__init__.py` as an empty file.

- [ ] **Step 4: Write summary.json fixture**

Write `tests/fixtures/mini-parsed/summary.json`:

```json
{
  "backup_dir": "tests/fixtures/mini-parsed",
  "accounts": ["account-1000000001"]
}
```

- [ ] **Step 5: Write peers fixture**

Write `tests/fixtures/mini-parsed/account-1000000001/peers.json`:

```json
[
  {"id": 111, "first_name": "Alice", "last_name": "Anderson", "username": "alice", "phone": "+15555550111"},
  {"id": 222, "first_name": "Bob", "last_name": "", "username": "bob", "phone": ""}
]
```

- [ ] **Step 6: Write messages fixture**

Write `tests/fixtures/mini-parsed/account-1000000001/messages.json`:

```json
[
  {"peer_id": 111, "text": "hello from alice", "timestamp": 1700000010, "outgoing": false},
  {"peer_id": 111, "text": "reply to alice", "timestamp": 1700000020, "outgoing": true},
  {"peer_id": 222, "text": "msg to bob", "timestamp": 1700000005, "outgoing": true}
]
```

- [ ] **Step 7: Write conversations fixture**

Write `tests/fixtures/mini-parsed/account-1000000001/conversations_index.json`:

```json
[
  {"peer_id": 111, "all_peer_ids": [111], "peer_name": "Alice Anderson", "peer_username": "alice", "message_count": 2, "last_message": 1700000020}
]
```

- [ ] **Step 8: Write FTS fixture**

Write `tests/fixtures/mini-parsed/account-1000000001/messages_fts.json`:

```json
[
  {"peer_ref": "p222", "text": "deleted message to bob", "fts_id": 1, "msg_ref": "x"}
]
```

- [ ] **Step 9: Write media catalog fixture**

Write `tests/fixtures/mini-parsed/account-1000000001/media_catalog.json`:

```json
[
  {"filename": "test.jpg", "mime_type": "image/jpeg", "media_type": "photo", "linked_message": {"peer_name": "Alice Anderson", "timestamp": 1700000010}}
]
```

- [ ] **Step 10: Write a 3-byte JPEG fixture**

Run: `printf '\xff\xd8\xff' > tests/fixtures/mini-parsed/account-1000000001/postbox/media/test.jpg`
(Use `mkdir -p tests/fixtures/mini-parsed/account-1000000001/postbox/media` first if needed.)

- [ ] **Step 11: Write conftest.py with fixtures**

Write `tests/conftest.py`:

```python
"""Pytest fixtures shared across tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "mini-parsed"

# Ensure the repo root is on sys.path so `import webui` and `import webui as old`
# both resolve regardless of pytest's rootdir.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def mini_data_dir() -> Path:
    """Path to the tiny parsed_data fixture used by all parity tests."""
    return FIXTURE_DIR
```

- [ ] **Step 12: Verify pytest discovers the package**

Run: `pytest tests/ -v --collect-only`
Expected: 0 tests collected, no import errors.

- [ ] **Step 13: Commit**

```bash
git add tests/ requirements.txt
git commit -m "test: add pytest infra and mini parsed_data fixture"
```

---

## Task 2: Characterization tests against current Flask app

Before any porting, lock current behavior in tests. These tests run against `webui.py` (the Flask app) using Flask's built-in test client. After we port to FastAPI, we'll mirror these into `test_fastapi_*.py` files and the Flask file becomes a deletion target in the final task.

**Files:**
- Create: `tests/test_flask_baseline.py`

- [ ] **Step 1: Write the Flask baseline test file**

Write `tests/test_flask_baseline.py`:

```python
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
```

- [ ] **Step 2: Run the baseline tests against current Flask**

Run: `pytest tests/test_flask_baseline.py -v`
Expected: all tests PASS (current Flask app works against the fixture).

If any fail, do NOT change `webui.py` — fix the test to reflect actual current behavior. The point is to capture *what is*, not *what should be*.

- [ ] **Step 3: Commit**

```bash
git add tests/test_flask_baseline.py
git commit -m "test: add characterization tests for current Flask webui"
```

---

## Task 3: Create webui package skeleton with state and Pydantic models

**Files:**
- Create: `webui/__init__.py`
- Create: `webui/state.py`
- Create: `webui/models.py`

- [ ] **Step 1: Write the package marker**

Write `webui/__init__.py`:

```python
"""tg-viewer web UI package — FastAPI backend over parsed_data JSON files."""
from webui.app import create_app

__all__ = ["create_app"]
```

- [ ] **Step 2: Write the state container**

Write `webui/state.py`:

```python
"""Application state container — replaces module-level globals from old webui.py."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AppState:
    """Holds loaded telegram data and the directories it was loaded from.

    Stored on the FastAPI app as `app.state.app_state` during lifespan startup.
    """
    telegram_data: dict[str, Any] = field(default_factory=dict)
    export_dir: Path | None = None
    backup_dir: Path | None = None

    @property
    def databases(self) -> dict[str, Any]:
        return self.telegram_data.get("databases", {})
```

- [ ] **Step 3: Write Pydantic response models**

Write `webui/models.py`:

```python
"""Pydantic response models for the webui FastAPI endpoints.

Messages and media-catalog entries are flexible by design — the parser may
emit fields we don't know about. We use `extra='allow'` for those.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class User(BaseModel):
    id: int | str
    name: str
    username: str = ""
    phone: str = ""
    database: str


class UsersPage(BaseModel):
    users: list[User]
    total: int
    page: int
    per_page: int
    total_pages: int


class DatabaseSummary(BaseModel):
    name: str
    decrypted: bool
    message_count: int
    tables: list[str]


class DatabaseDetail(BaseModel):
    model_config = ConfigDict(extra="allow")
    decrypted: bool
    messages: list[dict[str, Any]]
    peers: list[dict[str, Any]]
    conversations: list[dict[str, Any]]
    media_catalog: list[dict[str, Any]]


class Chat(BaseModel):
    id: str
    all_peer_ids: list[str]
    name: str
    username: str = ""
    type: str
    has_fts: bool
    message_count: int
    last_message: int | float | None = None
    databases: list[str]


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")
    text: str = ""
    peer_id: int | str | None = None
    timestamp: int | float | None = None
    outgoing: bool | None = None


class MessagesPage(BaseModel):
    messages: list[Message]
    total: int
    page: int
    per_page: int
    total_pages: int


class MediaItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    filename: str = ""
    mime_type: str = ""
    media_type: str = ""
    account: str = ""
    linked_message: dict[str, Any] | None = None


class MediaPage(BaseModel):
    media: list[MediaItem]
    total: int
    page: int
    per_page: int
    total_pages: int
    counts: dict[str, int]


class StatsDb(BaseModel):
    decrypted: bool
    message_count: int
    tables: int


class Stats(BaseModel):
    total_databases: int
    decrypted_databases: int
    total_messages: int
    total_chats: int
    databases: dict[str, StatsDb]


class ExportData(BaseModel):
    model_config = ConfigDict(extra="allow")
    accounts: list[Any] = []
    databases: dict[str, Any] = {}
    media_files: list[Any] = []
    total_media: int = 0
    backup_size: str = ""
```

- [ ] **Step 4: Verify the package imports cleanly (without app.py yet, this should fail)**

Run: `python -c "from webui.models import Stats; print(Stats)"`
Expected: prints the class.

Run: `python -c "from webui.state import AppState; AppState()"`
Expected: no error.

(The `from webui.app import create_app` in `__init__.py` will fail until Task 6. That's fine — only the leaf modules are imported in this task's verification.)

- [ ] **Step 5: Commit**

```bash
git add webui/__init__.py webui/state.py webui/models.py
git commit -m "feat: add webui package skeleton with state and Pydantic models"
```

---

## Task 4: Extract loader.py from webui.py

**Files:**
- Create: `webui/loader.py`

- [ ] **Step 1: Write the loader module**

Write `webui/loader.py` by lifting `load_parsed_data` and `load_telegram_data` from `webui.py:23-130`, but converted to return an `AppState` instead of mutating globals:

```python
"""Loads parsed_data JSON files into an AppState.

Pulled from the old webui.py with one change: returns an AppState instead of
mutating module-level globals.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webui.state import AppState


def load_parsed_data(data_dir: Path) -> dict[str, Any]:
    databases: dict[str, Any] = {}

    for account_dir in sorted(data_dir.glob("account-*")):
        account_id = account_dir.name

        def _read(name: str) -> Any:
            f = account_dir / name
            if f.exists():
                with open(f) as fh:
                    return json.load(fh)
            return []

        messages = _read("messages.json")
        peers = _read("peers.json")
        conversations = _read("conversations_index.json")
        messages_fts = _read("messages_fts.json")
        media_catalog = _read("media_catalog.json")

        databases[account_id] = {
            "decrypted": True,
            "messages": messages,
            "messages_fts": messages_fts,
            "peers": peers,
            "conversations": conversations,
            "media_catalog": media_catalog,
            "schema": {"tables": ["t2 (peers)", "t7 (messages)"]},
        }

        print(
            f"  {account_id}: {len(messages)} messages, {len(peers)} peers, "
            f"{len(conversations)} conversations, {len(messages_fts)} fts, "
            f"{len(media_catalog)} media"
        )

    return {"databases": databases}


def load_telegram_data(data_dir: str | Path) -> AppState:
    state = AppState()
    state.export_dir = Path(data_dir)

    nested = state.export_dir / "parsed_data"
    if nested.is_dir() and (
        (nested / "summary.json").exists()
        or any(nested.glob("account-*/messages.json"))
    ):
        print(f"Auto-detected parsed_data subdirectory: {nested}")
        state.export_dir = nested

    state.backup_dir = state.export_dir.parent
    summary_file = state.export_dir / "summary.json"
    if summary_file.exists():
        try:
            with open(summary_file) as f:
                summary = json.load(f)
            if "backup_dir" in summary:
                state.backup_dir = Path(summary["backup_dir"])
        except Exception:
            pass

    has_account_dirs = any(state.export_dir.glob("account-*"))

    if summary_file.exists() or has_account_dirs:
        print("Detected parsed_data format (postbox_parser.py)")
        state.telegram_data = load_parsed_data(state.export_dir)
    else:
        master_file = state.export_dir / "telegram_export.json"
        if master_file.exists():
            with open(master_file) as f:
                state.telegram_data = json.load(f)
        else:
            state.telegram_data = {"databases": {}}
            for export_file in state.export_dir.glob("*_export.json"):
                db_name = export_file.stem.replace("_export", "")
                with open(export_file) as f:
                    state.telegram_data["databases"][db_name] = json.load(f)

    db_count = len(state.databases)
    msg_count = sum(len(db.get("messages", [])) for db in state.databases.values())
    print(f"Loaded {db_count} databases with {msg_count} total messages")
    if db_count > 0 and msg_count == 0:
        print()
        print("WARNING: account-* directories were found but contain no messages.json.")
        print(f"  This usually means '{state.export_dir}' is a raw backup root, not parsed_data.")
        print(f"  Try: python3 postbox_parser.py '{state.export_dir}'  (then re-run this command)")

    return state
```

- [ ] **Step 2: Smoke-test the loader against the fixture**

Run:

```bash
python -c "
from webui.loader import load_telegram_data
s = load_telegram_data('tests/fixtures/mini-parsed')
assert 'account-1000000001' in s.databases
assert len(s.databases['account-1000000001']['messages']) == 3
print('OK')
"
```

Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add webui/loader.py
git commit -m "refactor: extract data loader from webui.py into webui/loader.py"
```

---

## Task 5: Extract mime.py and peer.py helpers

**Files:**
- Create: `webui/mime.py`
- Create: `webui/peer.py`

- [ ] **Step 1: Write mime.py**

Write `webui/mime.py` (lifted from `webui.py:132-162`):

```python
"""MIME type detection from file magic bytes."""
from __future__ import annotations

from pathlib import Path

MIME_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
    (b"\x1a\x45\xdf\xa3", "video/webm"),
]


def detect_mime(filepath: Path) -> str:
    try:
        with open(filepath, "rb") as f:
            header = f.read(12)
    except OSError:
        return "application/octet-stream"

    for sig, mime in MIME_SIGNATURES:
        if header.startswith(sig):
            if sig == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
                return "image/webp"
            elif sig == b"RIFF":
                continue
            return mime

    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4"

    return "application/octet-stream"
```

- [ ] **Step 2: Write peer.py**

Write `webui/peer.py` (lifted from `webui.py:193-206`):

```python
"""Peer type derivation from Postbox peer_id high bytes."""
from __future__ import annotations


def peer_type(peer_id: int) -> str:
    """Derive chat type from Postbox peer_id high bytes."""
    hi = (peer_id >> 32) & 0xFFFFFFFF
    if hi == 0:
        return "user"
    elif hi == 1:
        return "group"
    elif hi == 2:
        return "channel"
    elif hi == 3:
        return "secret"
    elif hi == 8:
        return "bot"
    return "other"
```

- [ ] **Step 3: Smoke-test the helpers**

Run:

```bash
python -c "
from webui.peer import peer_type
from webui.mime import detect_mime
from pathlib import Path
assert peer_type(0) == 'user'
assert peer_type(3 << 32) == 'secret'
assert detect_mime(Path('tests/fixtures/mini-parsed/account-1000000001/postbox/media/test.jpg')) == 'image/jpeg'
print('OK')
"
```

Expected: prints `OK`.

- [ ] **Step 4: Commit**

```bash
git add webui/mime.py webui/peer.py
git commit -m "refactor: extract mime and peer helpers from webui.py"
```

---

## Task 6: FastAPI app factory + lifespan

**Files:**
- Create: `webui/app.py`

- [ ] **Step 1: Write a minimal app.py with no routes yet**

Write `webui/app.py`:

```python
"""FastAPI app factory and lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from webui.loader import load_telegram_data
from webui.state import AppState


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    """Build the FastAPI app, loading data_dir into app.state at startup.

    `data_dir` may be None for tests that override state directly via
    `app.state.app_state = AppState(...)` after construction.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if data_dir is not None:
            app.state.app_state = load_telegram_data(data_dir)
        else:
            app.state.app_state = getattr(app.state, "app_state", AppState())
        yield

    app = FastAPI(
        title="tg-viewer",
        description="Telegram cache viewer API",
        version="1.0.0",
        lifespan=lifespan,
    )
    return app
```

- [ ] **Step 2: Add a fastapi_client fixture to conftest.py**

Edit `tests/conftest.py`, append:

```python


@pytest.fixture
def fastapi_client(mini_data_dir: Path):
    """FastAPI TestClient with the mini-parsed fixture loaded."""
    from fastapi.testclient import TestClient

    from webui.app import create_app

    app = create_app(str(mini_data_dir))
    with TestClient(app) as client:
        yield client
```

- [ ] **Step 3: Write a smoke test for the app**

Create `tests/test_fastapi_app.py`:

```python
def test_app_starts_and_serves_openapi(fastapi_client):
    r = fastapi_client.get("/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"] == "tg-viewer"


def test_state_is_loaded(fastapi_client):
    # The TestClient context triggers lifespan startup, so app_state must exist.
    app = fastapi_client.app
    assert app.state.app_state.databases  # non-empty for the fixture
```

- [ ] **Step 4: Add fastapi and uvicorn to requirements**

Edit `requirements.txt`, append:

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
pydantic>=2.6.0
```

Run: `pip install -r requirements.txt`

- [ ] **Step 5: Run the smoke test**

Run: `pytest tests/test_fastapi_app.py -v`
Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/app.py tests/conftest.py tests/test_fastapi_app.py requirements.txt
git commit -m "feat: add FastAPI app factory and lifespan-based state loading"
```

---

## Task 7: Port GET / (pages router serving templates/index.html)

**Files:**
- Create: `webui/routers/__init__.py`
- Create: `webui/routers/pages.py`
- Create: `tests/test_fastapi_pages.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_fastapi_pages.py`:

```python
def test_index_returns_html(fastapi_client):
    r = fastapi_client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<html" in r.text.lower()
```

- [ ] **Step 2: Run the test (expect 404)**

Run: `pytest tests/test_fastapi_pages.py -v`
Expected: FAIL with 404 (no `/` route yet).

- [ ] **Step 3: Create the routers package marker**

Write `webui/routers/__init__.py` as an empty file.

- [ ] **Step 4: Implement the pages router**

Write `webui/routers/pages.py`:

```python
"""Transitional page router — serves the legacy templates/index.html.

This entire router will be removed in Phase 2 once React+Bun owns the frontend.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> HTMLResponse:
    index_html = TEMPLATES_DIR / "index.html"
    if not index_html.is_file():
        raise HTTPException(status_code=500, detail="templates/index.html missing")
    return HTMLResponse(index_html.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Wire the router into the app**

Edit `webui/app.py`. Replace the `return app` at the end of `create_app` with:

```python
    from webui.routers import pages
    app.include_router(pages.router)
    return app
```

- [ ] **Step 6: Run the test (expect pass)**

Run: `pytest tests/test_fastapi_pages.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add webui/routers/__init__.py webui/routers/pages.py webui/app.py tests/test_fastapi_pages.py
git commit -m "feat: port GET / to FastAPI pages router"
```

---

## Task 8: Port /api/databases and /api/database/{db_name}

**Files:**
- Create: `webui/routers/databases.py`
- Create: `tests/test_fastapi_databases.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fastapi_databases.py`:

```python
def test_databases_list(fastapi_client):
    r = fastapi_client.get("/api/databases")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "account-1000000001"
    assert data[0]["decrypted"] is True
    assert data[0]["message_count"] == 3
    assert "t2 (peers)" in data[0]["tables"]


def test_database_detail_404(fastapi_client):
    r = fastapi_client.get("/api/database/account-doesnotexist")
    assert r.status_code == 404


def test_database_detail_payload(fastapi_client):
    r = fastapi_client.get("/api/database/account-1000000001")
    assert r.status_code == 200
    data = r.json()
    assert data["decrypted"] is True
    assert len(data["messages"]) == 3
    assert len(data["peers"]) == 2
```

- [ ] **Step 2: Run the tests (expect fail)**

Run: `pytest tests/test_fastapi_databases.py -v`
Expected: FAIL with 404s.

- [ ] **Step 3: Implement the databases router**

Write `webui/routers/databases.py`:

```python
"""GET /api/databases and GET /api/database/{db_name}."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from webui.models import DatabaseDetail, DatabaseSummary

router = APIRouter(prefix="/api", tags=["databases"])


@router.get("/databases", response_model=list[DatabaseSummary])
def list_databases(request: Request) -> list[DatabaseSummary]:
    state = request.app.state.app_state
    out: list[DatabaseSummary] = []
    for db_name, db_data in state.databases.items():
        out.append(
            DatabaseSummary(
                name=db_name,
                decrypted=db_data.get("decrypted", False),
                message_count=len(db_data.get("messages", [])),
                tables=list(db_data.get("schema", {}).get("tables", [])),
            )
        )
    return out


@router.get("/database/{db_name}", response_model=DatabaseDetail)
def get_database(db_name: str, request: Request) -> DatabaseDetail:
    state = request.app.state.app_state
    db_data = state.databases.get(db_name)
    if db_data is None:
        raise HTTPException(status_code=404, detail="Database not found")
    return DatabaseDetail(**db_data)
```

- [ ] **Step 4: Wire it into the app**

Edit `webui/app.py`. In `create_app`, append after the `pages` router include:

```python
    from webui.routers import databases
    app.include_router(databases.router)
```

- [ ] **Step 5: Run the tests (expect pass)**

Run: `pytest tests/test_fastapi_databases.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/routers/databases.py webui/app.py tests/test_fastapi_databases.py
git commit -m "feat: port /api/databases and /api/database/{db_name} to FastAPI"
```

---

## Task 9: Port /api/users

**Files:**
- Create: `webui/routers/users.py`
- Create: `tests/test_fastapi_users.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fastapi_users.py`:

```python
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
```

- [ ] **Step 2: Run the tests (expect fail)**

Run: `pytest tests/test_fastapi_users.py -v`
Expected: FAIL with 404s.

- [ ] **Step 3: Implement the users router**

Write `webui/routers/users.py`. Logic mirrors `webui.py:209-263` but typed via FastAPI query parameters:

```python
"""GET /api/users — paginated/searchable peers with first_name."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from webui.models import User, UsersPage

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/users", response_model=UsersPage)
def list_users(
    request: Request,
    search: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=1000),
) -> UsersPage:
    state = request.app.state.app_state
    needle = search.lower()

    users: list[User] = []
    seen_ids: set = set()

    for db_name, db_data in state.databases.items():
        for peer in db_data.get("peers", []):
            pid = peer.get("id")
            if pid in seen_ids:
                continue
            first_name = peer.get("first_name", "")
            if not first_name:
                continue
            name = first_name
            if peer.get("last_name"):
                name = f"{name} {peer['last_name']}"
            if not any(c.isalnum() for c in name):
                continue
            seen_ids.add(pid)

            user = User(
                id=pid,
                name=name,
                username=peer.get("username", "") or "",
                phone=peer.get("phone", "") or "",
                database=db_name,
            )

            if needle:
                haystack = f"{name} {user.username} {user.phone}".lower()
                if needle not in haystack:
                    continue

            users.append(user)

    users.sort(key=lambda u: u.name.lower())

    total = len(users)
    start = (page - 1) * per_page
    end = start + per_page
    return UsersPage(
        users=users[start:end],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if per_page else 1,
    )
```

- [ ] **Step 4: Wire the router**

In `webui/app.py`'s `create_app`, append:

```python
    from webui.routers import users
    app.include_router(users.router)
```

- [ ] **Step 5: Run the tests (expect pass)**

Run: `pytest tests/test_fastapi_users.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/routers/users.py webui/app.py tests/test_fastapi_users.py
git commit -m "feat: port /api/users to FastAPI"
```

---

## Task 10: Extract chats logic and port /api/chats

The current Flask code computes chats inside `get_chats()` and then `get_stats()` calls `get_chats()` and reads its `.json` attribute. We extract the logic into a pure `compute_chats(state)` function so both endpoints can share it without inter-route coupling.

**Files:**
- Create: `webui/chats_logic.py`
- Create: `webui/routers/chats.py`
- Create: `tests/test_fastapi_chats.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fastapi_chats.py`:

```python
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
    assert all("alice" in c["name"].lower() or "alice" in (c["username"] or "").lower() for c in data)


def test_chats_type_filter(fastapi_client):
    r = fastapi_client.get("/api/chats?type=secret")
    assert r.status_code == 200
    # No secret chats in fixture, so list is empty (not 404)
    assert r.json() == []
```

- [ ] **Step 2: Run the tests (expect fail)**

Run: `pytest tests/test_fastapi_chats.py -v`
Expected: FAIL with 404s.

- [ ] **Step 3: Write the chats_logic module**

Write `webui/chats_logic.py`. Logic mirrors `webui.py:393-512` but pure (takes state, returns list of dicts that match the `Chat` shape):

```python
"""Pure compute_chats function shared by /api/chats and /api/stats."""
from __future__ import annotations

from typing import Any

from webui.peer import peer_type
from webui.state import AppState


def compute_chats(
    state: AppState,
    *,
    search: str = "",
    type_filter: str = "",
    user_id: str = "",
) -> list[dict[str, Any]]:
    chats: dict[str, dict[str, Any]] = {}

    fts_peer_refs: set = set()
    for db_data in state.databases.values():
        for m in db_data.get("messages_fts", []):
            ref = str(m.get("peer_ref", ""))
            fts_peer_refs.add(ref.lstrip("p"))

    for db_name, db_data in state.databases.items():
        conversations = db_data.get("conversations", [])
        if conversations:
            for conv in conversations:
                chat_id = str(conv.get("peer_id", ""))
                all_ids = [str(x) for x in conv.get("all_peer_ids", [])] or (
                    [chat_id] if chat_id else []
                )
                if chat_id and chat_id not in chats:
                    pid = conv.get("peer_id") or 0
                    has_fts = any(aid in fts_peer_refs for aid in all_ids)
                    chats[chat_id] = {
                        "id": chat_id,
                        "all_peer_ids": all_ids,
                        "name": conv.get("peer_name") or f"Chat {chat_id}",
                        "username": conv.get("peer_username") or "",
                        "type": peer_type(pid),
                        "has_fts": has_fts,
                        "message_count": conv.get("message_count", 0),
                        "last_message": conv.get("last_message"),
                        "databases": [db_name],
                    }
                elif chat_id and chat_id in chats:
                    chats[chat_id]["message_count"] += conv.get("message_count", 0)
                    chats[chat_id]["databases"].append(db_name)
            continue

        # Legacy path (no conversations_index.json)
        for msg in db_data.get("messages", []):
            chat_id = None
            chat_name = None
            for field in ["chat_id", "peer_id", "dialog_id", "from_id", "to_id"]:
                if field in msg and msg[field]:
                    chat_id = str(msg[field])
                    break
            for field in ["chat_title", "peer_name", "from_name", "title"]:
                if field in msg and msg[field]:
                    chat_name = str(msg[field])
                    break
            if not chat_id:
                continue
            if chat_id not in chats:
                pid = msg.get("peer_id") or 0
                chats[chat_id] = {
                    "id": chat_id,
                    "all_peer_ids": [chat_id],
                    "name": chat_name or f"Chat {chat_id}",
                    "username": msg.get("peer_username") or "",
                    "type": peer_type(pid) if isinstance(pid, int) else "other",
                    "has_fts": chat_id in fts_peer_refs,
                    "message_count": 0,
                    "last_message": None,
                    "databases": [db_name],
                }
            chats[chat_id]["message_count"] += 1
            if db_name not in chats[chat_id]["databases"]:
                chats[chat_id]["databases"].append(db_name)
            msg_time = msg.get("timestamp", msg.get("date", 0))
            if not chats[chat_id]["last_message"] or msg_time > chats[chat_id]["last_message"]:
                chats[chat_id]["last_message"] = msg_time

    # Filters
    needle = search.lower()
    if needle:
        chats = {
            cid: c
            for cid, c in chats.items()
            if needle in (c.get("name") or "").lower()
            or needle in (c.get("username") or "").lower()
            or needle in cid
        }

    if type_filter == "secret":
        chats = {cid: c for cid, c in chats.items() if c["type"] == "secret"}
    elif type_filter == "fts":
        chats = {cid: c for cid, c in chats.items() if c["has_fts"]}
    elif type_filter:
        chats = {cid: c for cid, c in chats.items() if c["type"] == type_filter}

    if user_id:
        user_name = None
        for db_data in state.databases.values():
            for peer in db_data.get("peers", []):
                if str(peer.get("id", "")) == user_id:
                    user_name = peer.get("first_name", "")
                    if peer.get("last_name"):
                        user_name = f"{user_name} {peer['last_name']}"
                    break
            if user_name:
                break
        if user_name:
            n = user_name.lower()
            chats = {
                cid: c
                for cid, c in chats.items()
                if n in (c.get("name") or "").lower()
            }

    return sorted(chats.values(), key=lambda x: x.get("message_count", 0), reverse=True)
```

- [ ] **Step 4: Implement the chats router**

Write `webui/routers/chats.py`:

```python
"""GET /api/chats — searchable/filterable chat list."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from webui.chats_logic import compute_chats
from webui.models import Chat

router = APIRouter(prefix="/api", tags=["chats"])


@router.get("/chats", response_model=list[Chat])
def list_chats(
    request: Request,
    search: str = Query(""),
    type: str = Query(""),
    user_id: str = Query(""),
) -> list[Chat]:
    state = request.app.state.app_state
    raw = compute_chats(state, search=search, type_filter=type, user_id=user_id)
    return [Chat(**c) for c in raw]
```

- [ ] **Step 5: Wire the router**

In `webui/app.py`'s `create_app`, append:

```python
    from webui.routers import chats
    app.include_router(chats.router)
```

- [ ] **Step 6: Run the tests (expect pass)**

Run: `pytest tests/test_fastapi_chats.py -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add webui/chats_logic.py webui/routers/chats.py webui/app.py tests/test_fastapi_chats.py
git commit -m "feat: port /api/chats and extract pure compute_chats logic"
```

---

## Task 11: Port /api/messages

**Files:**
- Create: `webui/routers/messages.py`
- Create: `tests/test_fastapi_messages.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fastapi_messages.py`:

```python
def test_messages_default(fastapi_client):
    r = fastapi_client.get("/api/messages?per_page=10")
    assert r.status_code == 200
    data = r.json()
    # 3 t7 + 1 fts (peer 222 'deleted message to bob' has different text vs t7 'msg to bob')
    assert data["total"] == 4
    assert data["messages"][0]["timestamp"] == 1700000020  # newest first


def test_messages_filter_by_peer(fastapi_client):
    r = fastapi_client.get("/api/messages?peer_id=111")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2


def test_messages_filter_by_multiple_peers(fastapi_client):
    r = fastapi_client.get("/api/messages?peer_id=111,222")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 4


def test_messages_search(fastapi_client):
    r = fastapi_client.get("/api/messages?search=alice")
    assert r.status_code == 200
    data = r.json()
    # 'hello from alice' and 'reply to alice' match
    assert data["total"] == 2


def test_messages_does_not_mutate_loaded_data(fastapi_client):
    """Regression: old Flask code added _database/_account in place. Must not leak."""
    fastapi_client.get("/api/messages")
    state = fastapi_client.app.state.app_state
    raw_msgs = state.databases["account-1000000001"]["messages"]
    for m in raw_msgs:
        assert "_database" not in m
        assert "_account" not in m
```

- [ ] **Step 2: Run the tests (expect fail)**

Run: `pytest tests/test_fastapi_messages.py -v`
Expected: FAIL with 404s.

- [ ] **Step 3: Implement the messages router**

Write `webui/routers/messages.py`. Logic mirrors `webui.py:295-391` but **without the in-place mutation** of `msg['_database']` / `msg['_account']` — we shallow-copy each message before annotating:

```python
"""GET /api/messages — paginated/filterable messages with FTS dedup."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from webui.models import Message, MessagesPage

router = APIRouter(prefix="/api", tags=["messages"])


@router.get("/messages", response_model=MessagesPage)
def list_messages(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=1000),
    database: str = Query(""),
    search: str = Query(""),
    peer_id: str = Query(""),
) -> MessagesPage:
    state = request.app.state.app_state
    needle = search.lower()

    peer_id_set: set[str] = set(peer_id.split(",")) if peer_id else set()

    all_messages: list[dict[str, Any]] = []

    db_keys = [database] if database else list(state.databases.keys())

    for db in db_keys:
        db_data = state.databases.get(db, {})
        messages = db_data.get("messages", [])

        t7_keys: set[tuple[str, str]] = set()

        for msg in messages:
            if peer_id_set and str(msg.get("peer_id", "")) not in peer_id_set:
                continue

            # Shallow-copy before annotating to avoid mutating loaded data.
            annotated = {**msg, "_database": db, "_account": db}

            text = msg.get("text", "")
            if text:
                t7_keys.add((str(msg.get("peer_id", "")), text))

            if needle and needle not in str(annotated).lower():
                continue

            all_messages.append(annotated)

        fts_peer_refs = {f"p{pid}" for pid in peer_id_set} if peer_id_set else set()
        for fts_msg in db_data.get("messages_fts", []):
            ref = str(fts_msg.get("peer_ref", ""))
            if fts_peer_refs and ref not in fts_peer_refs:
                continue
            fts_text = fts_msg.get("text", "")
            peer_str = ref.lstrip("p")
            if (peer_str, fts_text) in t7_keys:
                continue
            if needle and needle not in fts_text.lower():
                continue
            all_messages.append(
                {
                    "text": fts_text,
                    "peer_id": peer_str,
                    "source": "fts",
                    "fts_id": fts_msg.get("fts_id"),
                    "msg_ref": fts_msg.get("msg_ref", ""),
                    "timestamp": 0,
                    "outgoing": None,
                    "_database": db,
                    "_account": db,
                }
            )

    try:
        all_messages.sort(
            key=lambda x: x.get("timestamp", x.get("date", 0)) or 0,
            reverse=True,
        )
    except Exception:
        pass

    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_messages[start:end]

    return MessagesPage(
        messages=[Message(**m) for m in paginated],
        total=len(all_messages),
        page=page,
        per_page=per_page,
        total_pages=(len(all_messages) + per_page - 1) // per_page if per_page else 1,
    )
```

- [ ] **Step 4: Wire the router**

In `webui/app.py`'s `create_app`, append:

```python
    from webui.routers import messages
    app.include_router(messages.router)
```

- [ ] **Step 5: Run the tests (expect pass)**

Run: `pytest tests/test_fastapi_messages.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/routers/messages.py webui/app.py tests/test_fastapi_messages.py
git commit -m "feat: port /api/messages and stop mutating loaded data"
```

---

## Task 12: Port /api/media (catalog) and /api/media/{account_id}/{filename}

**Files:**
- Create: `webui/routers/media.py`
- Create: `tests/test_fastapi_media.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fastapi_media.py`:

```python
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
```

- [ ] **Step 2: Run the tests (expect fail)**

Run: `pytest tests/test_fastapi_media.py -v`
Expected: FAIL with 404s.

- [ ] **Step 3: Implement the media router**

Write `webui/routers/media.py`:

```python
"""GET /api/media (catalog) and /api/media/{account_id}/{filename} (file)."""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from webui.mime import detect_mime
from webui.models import MediaItem, MediaPage

router = APIRouter(prefix="/api", tags=["media"])

ACCOUNT_RE = re.compile(r"^account-\d+$")


@router.get("/media", response_model=MediaPage)
def list_media(
    request: Request,
    search: str = Query(""),
    type: str = Query(""),
    account: str = Query(""),
    page: int = Query(1, ge=1),
    per_page: int = Query(60, ge=1, le=1000),
) -> MediaPage:
    state = request.app.state.app_state
    needle = search.lower()

    items: list[dict] = []
    for db_name, db_data in state.databases.items():
        if account and db_name != account:
            continue
        for entry in db_data.get("media_catalog", []):
            if type and entry.get("media_type") != type:
                continue
            if needle:
                hay_parts = [
                    entry.get("filename", ""),
                    entry.get("mime_type", ""),
                    entry.get("media_type", ""),
                ]
                linked = entry.get("linked_message") or {}
                hay_parts.append(linked.get("peer_name") or "")
                if needle not in " ".join(hay_parts).lower():
                    continue
            items.append({**entry, "account": db_name})

    def _sort_key(e: dict) -> int:
        linked = e.get("linked_message") or {}
        return -(linked.get("timestamp") or 0)

    items.sort(key=_sort_key)

    counts: dict[str, int] = {"all": 0}
    for db_data in state.databases.values():
        for entry in db_data.get("media_catalog", []):
            counts["all"] += 1
            mt = entry.get("media_type") or "document"
            counts[mt] = counts.get(mt, 0) + 1

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page

    return MediaPage(
        media=[MediaItem(**i) for i in items[start:end]],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=(total + per_page - 1) // per_page if per_page else 1,
        counts=counts,
    )


@router.get("/media/{account_id}/{filename}")
def serve_media(account_id: str, filename: str, request: Request):
    if not ACCOUNT_RE.match(account_id):
        raise HTTPException(status_code=400, detail="Invalid account ID")
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    state = request.app.state.app_state
    if not state.backup_dir:
        raise HTTPException(status_code=404, detail="No backup directory configured")

    media_dir = state.backup_dir / account_id / "postbox" / "media"
    filepath = media_dir / filename

    try:
        filepath.resolve().relative_to(media_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(str(filepath), media_type=detect_mime(filepath))
```

- [ ] **Step 4: Wire the router**

In `webui/app.py`'s `create_app`, append:

```python
    from webui.routers import media
    app.include_router(media.router)
```

- [ ] **Step 5: Run the tests (expect pass)**

Run: `pytest tests/test_fastapi_media.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/routers/media.py webui/app.py tests/test_fastapi_media.py
git commit -m "feat: port /api/media catalog and file-serving endpoints"
```

---

## Task 13: Port /api/stats

**Files:**
- Create: `webui/routers/stats.py`
- Create: `tests/test_fastapi_stats.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_fastapi_stats.py`:

```python
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
    assert db["tables"] == 1
```

- [ ] **Step 2: Run (expect fail)**

Run: `pytest tests/test_fastapi_stats.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Implement the stats router**

Write `webui/routers/stats.py` — uses `compute_chats` for the chat count instead of calling another endpoint:

```python
"""GET /api/stats — overview counts."""
from __future__ import annotations

from fastapi import APIRouter, Request

from webui.chats_logic import compute_chats
from webui.models import Stats, StatsDb

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=Stats)
def get_stats(request: Request) -> Stats:
    state = request.app.state.app_state

    total_databases = 0
    decrypted_databases = 0
    total_messages = 0
    databases: dict[str, StatsDb] = {}

    for db_name, db_data in state.databases.items():
        total_databases += 1
        if db_data.get("decrypted"):
            decrypted_databases += 1
        msg_count = len(db_data.get("messages", []))
        total_messages += msg_count
        databases[db_name] = StatsDb(
            decrypted=db_data.get("decrypted", False),
            message_count=msg_count,
            tables=len(db_data.get("schema", {}).get("tables", [])),
        )

    total_chats = len(compute_chats(state))

    return Stats(
        total_databases=total_databases,
        decrypted_databases=decrypted_databases,
        total_messages=total_messages,
        total_chats=total_chats,
        databases=databases,
    )
```

- [ ] **Step 4: Wire the router**

In `webui/app.py`'s `create_app`, append:

```python
    from webui.routers import stats
    app.include_router(stats.router)
```

- [ ] **Step 5: Run (expect pass)**

Run: `pytest tests/test_fastapi_stats.py -v`
Expected: 1 PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/routers/stats.py webui/app.py tests/test_fastapi_stats.py
git commit -m "feat: port /api/stats using shared compute_chats"
```

---

## Task 14: Port /api/export-data

**Files:**
- Create: `webui/routers/export_data.py`
- Create: `tests/test_fastapi_export_data.py`
- Modify: `webui/app.py`

- [ ] **Step 1: Write the failing test**

Write `tests/test_fastapi_export_data.py`:

```python
def test_export_data(fastapi_client):
    r = fastapi_client.get("/api/export-data")
    assert r.status_code == 200
    data = r.json()
    assert "databases" in data
    assert "account-1000000001" in data["databases"]
    assert "total_media" in data
```

- [ ] **Step 2: Run (expect fail)**

Run: `pytest tests/test_fastapi_export_data.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Implement**

Write `webui/routers/export_data.py`:

```python
"""GET /api/export-data — bulk dump used by the legacy frontend."""
from __future__ import annotations

from fastapi import APIRouter, Request

from webui.models import ExportData

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/export-data", response_model=ExportData)
def get_export_data(request: Request) -> ExportData:
    state = request.app.state.app_state
    td = state.telegram_data

    total_media = 0
    for media in td.get("media_files", []):
        total_media += media.get("count", 0)

    return ExportData(
        accounts=td.get("accounts", []),
        databases=td.get("databases", {}),
        media_files=td.get("media_files", []),
        total_media=total_media,
        backup_size="15 GB",
    )
```

- [ ] **Step 4: Wire the router**

In `webui/app.py`'s `create_app`, append:

```python
    from webui.routers import export_data
    app.include_router(export_data.router)
```

- [ ] **Step 5: Run (expect pass)**

Run: `pytest tests/test_fastapi_export_data.py -v`
Expected: 1 PASS.

- [ ] **Step 6: Commit**

```bash
git add webui/routers/export_data.py webui/app.py tests/test_fastapi_export_data.py
git commit -m "feat: port /api/export-data to FastAPI"
```

---

## Task 15: CLI entrypoint (`python -m webui ...`)

**Files:**
- Create: `webui/__main__.py`

- [ ] **Step 1: Write the entrypoint**

Write `webui/__main__.py`:

```python
"""CLI entry: `python -m webui <data_dir> --host --port [--reload]`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

from webui.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the tg-viewer web UI")
    parser.add_argument("data_dir", help="Directory containing decrypted parsed_data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev only)")
    args = parser.parse_args()

    if not Path(args.data_dir).exists():
        print(f"ERROR: Data directory not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    print("\n🚀 Starting Telegram Data Web UI (FastAPI)")
    print(f"📂 Data directory: {args.data_dir}")
    print(f"🌐 URL: http://{args.host}:{args.port}")
    print(f"📖 OpenAPI docs: http://{args.host}:{args.port}/docs")
    print("\nPress Ctrl+C to stop\n")

    app = create_app(args.data_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run a smoke test against the fixture**

Run (in one terminal): `python -m webui tests/fixtures/mini-parsed --port 5099`
Then from another shell:

```bash
curl -s http://127.0.0.1:5099/api/stats | python -m json.tool
```

Expected: JSON with `total_databases: 1`, `total_messages: 3`. Then Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add webui/__main__.py
git commit -m "feat: add 'python -m webui' CLI entrypoint with uvicorn"
```

---

## Task 16: Switch tg-viewer to invoke the new entrypoint

**Files:**
- Modify: `tg-viewer:212`

- [ ] **Step 1: Update the run_webui function**

Edit `tg-viewer`. Change line 212 from:

```bash
    python3 "$WEBUI_SCRIPT" "$data_dir" --host "$host" --port "$port"
```

to:

```bash
    python3 -m webui "$data_dir" --host "$host" --port "$port"
```

Also update the `WEBUI_SCRIPT` declaration near line 13 to be a marker rather than a script path — change `WEBUI_SCRIPT="$SCRIPT_DIR/webui.py"` to `WEBUI_SCRIPT_DIR="$SCRIPT_DIR/webui"` and update the existence check at line 200 from `[[ ! -f "$WEBUI_SCRIPT" ]]` to `[[ ! -d "$WEBUI_SCRIPT_DIR" ]]` and adjust the error message.

- [ ] **Step 2: End-to-end smoke test**

Run: `./tg-viewer webui tests/fixtures/mini-parsed --port 5099` (if the CLI accepts those args; check tg-viewer's argument parsing — line 366-369 indicates `webui DIR [PORT]`. Use the right form.)

If the CLI is strict about port, just run: `./tg-viewer webui tests/fixtures/mini-parsed`

Expected: server starts on default port, OpenAPI docs reachable at `/docs`. Ctrl+C to stop.

- [ ] **Step 3: Commit**

```bash
git add tg-viewer
git commit -m "feat: tg-viewer launches FastAPI webui via 'python -m webui'"
```

---

## Task 17: Final cleanup — delete webui.py, drop Flask deps, run all tests

**Files:**
- Delete: `webui.py`
- Delete: `tests/test_flask_baseline.py`
- Modify: `requirements.txt`
- Modify: `README.md`

- [ ] **Step 1: Confirm all FastAPI parity tests pass first**

Run: `pytest tests/ -v --ignore=tests/test_flask_baseline.py`
Expected: all pass (skipping the Flask baseline file we're about to delete).

If anything fails, STOP — do not delete webui.py until parity is green.

- [ ] **Step 2: Delete the old Flask app and its baseline tests**

Run:

```bash
git rm webui.py tests/test_flask_baseline.py
```

- [ ] **Step 3: Drop Flask and Jinja2 from requirements.txt**

Edit `requirements.txt`. Remove these lines:

```
flask>=2.3.0
jinja2>=3.1.2
```

- [ ] **Step 4: Update README**

In `README.md`, find the section that documents the web UI. Add a note:

```markdown
The web UI is built on FastAPI. Once running, interactive API docs are at:

- Swagger UI: http://127.0.0.1:5000/docs
- ReDoc: http://127.0.0.1:5000/redoc
- OpenAPI schema: http://127.0.0.1:5000/openapi.json

The OpenAPI schema is the source of truth for the (Phase 2) React frontend's
TypeScript client types.
```

- [ ] **Step 5: Run the full test suite one more time**

Run: `pytest tests/ -v`
Expected: all FastAPI tests pass; no Flask tests remain.

- [ ] **Step 6: Run the orchestrator end-to-end against the fixture**

Run: `./tg-viewer webui tests/fixtures/mini-parsed`
Verify: browser at the printed URL renders the existing inline-JS UI without errors. (The frontend hits the new FastAPI endpoints transparently — same JSON shapes.)

Stop the server with Ctrl+C.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove Flask app and dependencies; FastAPI is the only backend"
```

---

## Self-Review Checklist (run before handing off to executor)

**1. Spec coverage**

| Spec requirement | Implemented in |
|---|---|
| All 10 Flask routes ported | Tasks 7–14 |
| Pydantic response models | Task 3 |
| OpenAPI auto-generation | Task 6 (FastAPI default) |
| `parsed_data/` JSON loader unchanged | Task 4 |
| MIME detection + path traversal guard preserved | Task 12 |
| `tg-viewer webui` keeps working | Task 16 |
| Flask/Jinja2 deps removed | Task 17 |
| README updated with `/docs` URL | Task 17 |

**2. Placeholder scan:** none — every step has runnable code or commands.

**3. Type consistency:** all router files import response models from `webui.models`; all routers use `request.app.state.app_state` (consistent attribute name); `compute_chats` signature is consistent between Tasks 10 and 13.

---

## Phase 2 Preview (separate plan)

Phase 2 will be drafted as `2026-04-26-phase-2-react-bun-frontend.md` after Phase 1 lands and the OpenAPI schema is concrete. High-level shape:

1. `web/` workspace (`package.json`, `tsconfig.json`, Bun + React)
2. Generate TypeScript client from `/openapi.json` via `openapi-typescript`
3. `Bun.serve()` dev server with HMR + API proxy to FastAPI on a separate port
4. Port the 6 tabs (Stats, Databases, Chats, Messages, Users, Media) and 2 modals (Chat, Media) into React components
5. Production: `bun build` → static bundle → FastAPI mounts via `StaticFiles` → single-process deploy
6. Delete `templates/index.html` and the transitional `pages` router
