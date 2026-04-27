"""Unit tests for the peer_type helper.

Note: bot vs user is NOT distinguishable from peer_id. Modern (post-2021)
user/bot IDs land in hi=8, legacy ones in hi=0; both map to "user". The
bot/user split lives on the parsed peer record (`is_bot`) and is applied
by chats_logic.
"""
from api.peer import peer_type


def test_peer_type_user_legacy_id():
    assert peer_type(0) == "user"


def test_peer_type_user_modern_id():
    # 64-bit user IDs (post-2021) land in hi=8; still "user", not "bot".
    assert peer_type(8 << 32) == "user"


def test_peer_type_group():
    assert peer_type(1 << 32) == "group"


def test_peer_type_channel():
    assert peer_type(2 << 32) == "channel"


def test_peer_type_secret():
    assert peer_type(3 << 32) == "secret"


def test_peer_type_other():
    assert peer_type(9 << 32) == "other"
