"""Peer type derivation from Postbox peer_id high bytes."""
from __future__ import annotations


def peer_type(peer_id: int) -> str:
    """Derive chat type from Postbox peer_id high bytes.

    Note: bot vs user cannot be distinguished from peer_id — Telegram
    represents bots as users in the same namespace. `hi=0` holds legacy
    32-bit user/bot IDs, `hi=8` holds modern 64-bit user/bot IDs. The
    bot/user split lives in the t2 record's `bot_info` tag and is parsed
    by postbox_parser into `is_bot`; chats_logic applies the override.
    """
    hi = (peer_id >> 32) & 0xFFFFFFFF
    if hi in (0, 8):
        return "user"
    elif hi == 1:
        return "group"
    elif hi == 2:
        return "channel"
    elif hi == 3:
        return "secret"
    return "other"
