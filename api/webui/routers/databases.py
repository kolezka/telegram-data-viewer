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
