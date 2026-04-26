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
