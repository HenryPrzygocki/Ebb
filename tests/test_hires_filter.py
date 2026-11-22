"""Fork: the "Hi-Res only" filter (ui/hires_filter.py)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui import hires_filter  # noqa: E402


def _track(i, hires):
    return SimpleNamespace(
        id=i,
        media_metadata_tags=["LOSSLESS", "HIRES_LOSSLESS"] if hires else ["LOSSLESS"],
        audio_quality="HI_RES_LOSSLESS" if hires else "LOSSLESS",
    )


MIXED = [_track(i, i % 3 == 0) for i in range(9)]  # ids 0, 3, 6 are Hi-Res
ALL_HIRES = [_track(i, True) for i in range(4)]
NO_HIRES = [_track(i, False) for i in range(4)]


class Chip:
    def __init__(self):
        self.synced = None

    def sync(self, tracks):
        self.synced = list(tracks)


def _app(on, chip=None):
    return SimpleNamespace(hires_only=on, hires_chip=chip)


def test_counts_and_mixed():
    assert hires_filter.count(MIXED) == (3, 9)
    assert hires_filter.mixed(MIXED)
    assert not hires_filter.mixed(ALL_HIRES)
    assert not hires_filter.mixed(NO_HIRES)
    assert not hires_filter.mixed([])


def test_the_filter_keeps_the_hires_tracks_of_a_mixed_list():
    assert [t.id for t in hires_filter.apply(_app(True), MIXED)] == [0, 3, 6]
    assert hires_filter.apply(_app(False), MIXED) == MIXED


def test_a_list_of_one_quality_is_left_alone():
    assert hires_filter.apply(_app(True), NO_HIRES) == NO_HIRES  # it would empty
    assert hires_filter.apply(_app(True), ALL_HIRES) == ALL_HIRES


def test_a_search_within_a_mixed_list_is_filtered_by_the_whole_lists_mix():
    narrowed = [t for t in MIXED if t.id in (3, 4, 5)]
    assert [t.id for t in hires_filter.apply(_app(True), narrowed, scope=MIXED)] == [3]
    assert hires_filter.apply(_app(True), narrowed, scope=NO_HIRES) == narrowed


def test_the_track_page_filters_and_re_renders_keep_the_full_list():
    chip = Chip()
    app = _app(True, chip)
    shown = hires_filter.for_track_page(app, MIXED, album_page=False)
    assert [t.id for t in shown] == [0, 3, 6]
    assert chip.synced == MIXED
    again = hires_filter.for_track_page(app, shown, album_page=False)  # e.g. select mode
    assert [t.id for t in again] == [0, 3, 6]
    app.hires_only = False
    assert hires_filter.for_track_page(app, list(app._hires_source), album_page=False) == MIXED


def test_a_new_list_replaces_the_remembered_one():
    app = _app(True, Chip())
    hires_filter.for_track_page(app, MIXED, album_page=False)
    other = [_track(100 + i, i == 0) for i in range(3)]
    assert [t.id for t in hires_filter.for_track_page(app, other, album_page=False)] == [100]
    assert app._hires_source == other


def test_album_pages_are_never_filtered_and_hide_the_chip():
    chip = Chip()
    app = _app(True, chip)
    assert hires_filter.for_track_page(app, MIXED, album_page=True) == MIXED
    assert chip.synced == []
