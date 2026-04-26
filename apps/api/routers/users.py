"""GET /api/users — paginated/searchable peers with first_name."""
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from api.models import User, UsersPage

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
