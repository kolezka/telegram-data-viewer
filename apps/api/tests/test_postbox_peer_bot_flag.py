"""Bot/user detection from t2 records — see postbox_parser.parse_peer_from_t2.

The signal is the `bi` (bot_info) tag in the User struct: type 0x05 means
the BotInfo struct is present (bot), 0x0b means nil (user). Channels and
groups omit the field entirely. Verified across a 84k-peer live snapshot
with zero contradictions; this test pins the format-level guarantees.
"""
from __future__ import annotations

import struct

from tool.postbox_parser import parse_peer_from_t2


def _peer_blob(*, bot: bool | None, username: str = "user") -> bytes:
    """Synthesise a minimal t2 value carrying a username and bot_info tag."""
    uname = username.encode("utf-8")
    out = b"\x02un\x04" + struct.pack("<I", len(uname)) + uname
    if bot is True:
        # Real bot records have a struct payload after `02 bi 05`; the
        # presence of `02 62 69 05` is the actual signal.
        out += b"\x02\x62\x69\x05" + b"\x00" * 4
    elif bot is False:
        out += b"\x02\x62\x69\x0b"
    return out


def test_is_bot_true_when_bot_info_struct_present():
    peer = parse_peer_from_t2(429000, _peer_blob(bot=True, username="Stickers"))
    assert peer is not None
    assert peer["is_bot"] is True
    assert peer["username"] == "Stickers"


def test_is_bot_false_when_bot_info_nil():
    peer = parse_peer_from_t2(1733941788, _peer_blob(bot=False, username="Klaudiusz"))
    assert peer is not None
    assert peer["is_bot"] is False


def test_is_bot_absent_when_no_bot_info_tag():
    """Channels/groups have no bot_info field — leave is_bot off the record."""
    peer = parse_peer_from_t2(2 << 32, _peer_blob(bot=None, username="some_channel"))
    assert peer is not None
    assert "is_bot" not in peer


def test_username_suffix_does_not_decide_bot():
    """A user with a bot-suffixed handle must NOT be tagged is_bot."""
    peer = parse_peer_from_t2(1, _peer_blob(bot=False, username="user949929_bot"))
    assert peer["is_bot"] is False


def test_bot_without_bot_username_still_flagged():
    """A bot whose handle doesn't end in 'bot' (e.g. @stickers, @gif, @gamee)
    must still be flagged via the bot_info tag."""
    peer = parse_peer_from_t2(429000, _peer_blob(bot=True, username="stickers"))
    assert peer["is_bot"] is True
