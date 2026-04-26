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
    filename: str = ""
    mime_type: str = ""
    media_type: str = ""
    account: str = ""
    linked_message: dict[str, Any] | None = None
    thumbnail: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None


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
    accounts: list[Any] = []
    databases: dict[str, Any] = {}
    media_files: list[Any] = []
    total_media: int = 0
    backup_size: str = ""
