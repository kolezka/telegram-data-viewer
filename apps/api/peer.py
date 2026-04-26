"""Peer type derivation from Postbox peer_id high bytes."""
from __future__ import annotations


def peer_type(peer_id: int) -> str:
    """Derive chat type from Postbox peer_id high bytes."""
    hi = (peer_id >> 32) & 0xFFFFFFFF
    if hi == 0:
        return "user"
    elif hi == 1:
        return "group"
    elif hi == 2:
        return "channel"
    elif hi == 3:
        return "secret"
    elif hi == 8:
        return "bot"
    return "other"
