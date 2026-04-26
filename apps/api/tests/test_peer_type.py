"""Unit tests for the peer_type helper. All six branches must remain covered."""
from api.peer import peer_type


def test_peer_type_user():
    assert peer_type(0) == "user"


def test_peer_type_group():
    assert peer_type(1 << 32) == "group"


def test_peer_type_channel():
    assert peer_type(2 << 32) == "channel"


def test_peer_type_secret():
    assert peer_type(3 << 32) == "secret"


def test_peer_type_bot():
    assert peer_type(8 << 32) == "bot"


def test_peer_type_other():
    assert peer_type(9 << 32) == "other"
