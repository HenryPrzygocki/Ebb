"""Fork: an album's own page drops the artist cell when every track is by the album's artist."""
import os
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui.track_table import one_artist_album  # noqa: E402

FLOYD = NS(id=1, name="Pink Floyd")


def _t(artist):
    return NS(artist=artist)


def test_an_album_by_one_artist_needs_no_artist_cell():
    album = NS(artist=FLOYD)
    assert one_artist_album(album, [_t(NS(id=1, name="Pink Floyd")) for _ in range(3)])


def test_a_compilation_or_a_guest_main_artist_keeps_it():
    album = NS(artist=NS(id=99, name="Various Artists"))
    assert not one_artist_album(album, [_t(FLOYD), _t(NS(id=2, name="Bowie"))])
    album = NS(artist=FLOYD)
    assert not one_artist_album(album, [_t(FLOYD), _t(NS(id=2, name="Bowie"))])


def test_names_decide_when_ids_are_missing_and_nothing_is_not_one_artist():
    album = NS(artist=NS(id=None, name="Pink Floyd"))
    assert one_artist_album(album, [_t(NS(id=None, name="pink floyd"))])
    assert not one_artist_album(album, [])
    assert not one_artist_album(NS(artist=None), [_t(FLOYD)])
