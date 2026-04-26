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
