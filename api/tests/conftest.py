"""Pytest fixtures shared across tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


# api/tests/conftest.py → parents: api/tests/, api/, <repo root>
API_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = API_DIR.parent
FIXTURE_DIR = API_DIR / "tests" / "fixtures" / "mini-parsed"

# Make `webui` importable from api/, and `extract` importable from repo root.
for path in (str(API_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture
def mini_data_dir() -> Path:
    """Path to the tiny parsed_data fixture used by all parity tests."""
    return FIXTURE_DIR


@pytest.fixture
def fastapi_client(mini_data_dir: Path):
    """FastAPI TestClient with the mini-parsed fixture loaded."""
    from fastapi.testclient import TestClient

    from webui.app import create_app

    app = create_app(str(mini_data_dir))
    with TestClient(app) as client:
        # Same Task 1 follow-up applies here: summary.json's relative backup_dir
        # would point outside the fixture; pin it absolute so /api/media works
        # regardless of pytest's CWD. The lifespan has already run by the time
        # we enter the `with` block.
        client.app.state.app_state.backup_dir = mini_data_dir
        yield client
