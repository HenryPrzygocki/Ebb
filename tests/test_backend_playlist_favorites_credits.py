"""Fork #24: playlist favorites and track credits in the backend (backend/tidal.py)."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from backend.tidal import TidalBackend, parse_credits  # noqa: E402


def test_credits_keep_tidals_order_merge_a_repeated_role_and_drop_blanks():
    payload = [  # the shape TIDAL's v1 tracks/{id}/credits returns
        {"type": "Producer", "contributors": [{"name": "Pink Floyd", "id": 9706}]},
        {"type": "Composer", "contributors": [{"name": "Nick Mason", "id": 41060534}]},
        {"type": "Producer", "contributors": [{"name": "Pink Floyd", "id": 9706}, {"name": "Alan Parsons", "id": 2539}]},
        {"type": "Speaker", "contributors": [{"name": "Clare Torry"}, {"name": ""}]},
        {"type": "", "contributors": [{"name": "Nobody", "id": 1}]},
        {"type": "Empty", "contributors": []},
    ]
    assert parse_credits(payload) == [
        ("Producer", [("Pink Floyd", "9706"), ("Alan Parsons", "2539")]),
        ("Composer", [("Nick Mason", "41060534")]),
        ("Speaker", [("Clare Torry", None)]),
    ]
    assert parse_credits({"status": 404, "userMessage": "not found"}) == []


def test_track_credits_come_from_the_v1_endpoint_and_none_means_the_request_failed():
    be = TidalBackend.__new__(TidalBackend)
    seen = []

    def request(method, path, params=None):
        seen.append((method, path))
        return SimpleNamespace(json=lambda: [{"type": "Producer", "contributors": [{"name": "X", "id": 1}]}])

    be.session = SimpleNamespace(request=SimpleNamespace(request=request))
    be._call_with_session_recovery = lambda fn, context="api": fn()
    assert be.get_track_credits(55) == [("Producer", [("X", "1")])]
    assert seen == [("GET", "tracks/55/credits")]

    def offline(*_a, **_k):
        raise RuntimeError("offline")

    be.session.request.request = offline
    assert be.get_track_credits(55) is None
    assert be.get_track_credits(None) is None


def _backend(favorites):
    be = TidalBackend.__new__(TidalBackend)
    be.user = SimpleNamespace(favorites=favorites)
    be.fav_playlist_ids = set()
    return be


def test_playlist_favorites_go_through_tidalapi_and_keep_the_ids():
    calls = []
    be = _backend(SimpleNamespace(
        add_playlist=lambda pid: calls.append(("add", pid)) or True,
        remove_playlist=lambda pid: calls.append(("remove", pid)) or True,
    ))
    assert be.toggle_playlist_favorite("u1", True) and be.is_playlist_favorite("u1")
    assert be.toggle_playlist_favorite("u1", False) and not be.is_playlist_favorite("u1")
    assert calls == [("add", "u1"), ("remove", "u1")]
    refused = _backend(SimpleNamespace(add_playlist=lambda pid: False))  # tidalapi: request not ok
    assert refused.toggle_playlist_favorite("u2", True) is False and not refused.is_playlist_favorite("u2")
