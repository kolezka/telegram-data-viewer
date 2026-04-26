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
