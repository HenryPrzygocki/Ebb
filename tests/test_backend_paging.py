"""Fork: an artist list whose first page is short is one request; longer lists page on
until an empty page, since TIDAL returns short pages mid-list."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("gi")

from test_tidal_session_recovery import _make_backend  # noqa: E402


class _Artist:
    def __init__(self, total, cap=None):
        self.id, self.total, self.cap, self.calls = 7, total, cap, []

    def get_albums(self, limit, offset):
        self.calls.append((limit, offset))
        n = min(limit, self.cap or limit)
        return [SimpleNamespace(id=i) for i in range(offset, min(offset + n, self.total))]


def _albums(artist):
    backend = _make_backend()
    return backend._get_artist_album_collection(artist, "get_albums", limit=2000, page_size=100)


def test_a_short_first_page_is_the_only_request():
    a = _Artist(15)
    assert len(_albums(a)) == 15 and a.calls == [(100, 0)]


def test_full_pages_keep_paging():
    a = _Artist(230)
    assert len(_albums(a)) == 230 and a.calls == [(100, 0), (100, 100), (100, 200), (100, 230)]


def test_a_server_capping_pages_at_50_still_gets_everything():
    a = _Artist(120, cap=50)
    assert len(_albums(a)) == 120 and [o for _, o in a.calls] == [0, 50, 100, 120]


def test_a_short_page_mid_list_does_not_end_it():
    class _Gappy(_Artist):  # TIDAL: 100, 97, 100, … (filtered items), as seen on Bach
        def get_albums(self, limit, offset):
            page = super().get_albums(limit, offset)
            return page[:97] if offset == 100 else page
    a = _Gappy(260)
    assert len(_albums(a)) == 260  # nothing lost: the next page starts where the short one ended
