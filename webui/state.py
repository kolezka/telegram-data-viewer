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
