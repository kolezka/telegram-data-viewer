"""GET /api/chats — searchable/filterable chat list."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.chats_logic import compute_chats
from api.models import Chat

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
