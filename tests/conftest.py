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
