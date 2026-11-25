"""Fork: the artist page through a resize: the hero's side images and Top Tracks' columns.

Every layout pass (two per size change, more while a docking sidebar settles) reloaded both,
blanking them first, and the loads ran on an 8-worker pool where an earlier size could land last."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from utils import helpers  # noqa: E402


class _Picture:
    def __init__(self):
        self.paintables, self.size = [], None

    def set_paintable(self, paintable):
        self.paintables.append(paintable)

    def set_size_request(self, width, height):
        self.size = (width, height)


@pytest.fixture
def image(tmp_path):
    from gi.repository import GdkPixbuf

    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 64, 64)
    pixbuf.fill(0x336699FF)
    path = tmp_path / "artist.png"
    pixbuf.savev(str(path), "png", [], [])
    return str(path)


@pytest.fixture
def queues(monkeypatch):
    jobs, idles = [], []
    monkeypatch.setattr(helpers, "_IMG_EXECUTOR", SimpleNamespace(submit=jobs.append))
    monkeypatch.setattr(helpers.GLib, "idle_add", lambda fn, *a: idles.append(lambda: fn(*a)) or len(idles))
    return jobs, idles


def _load(picture, image, size, **kw):
    helpers.load_picture_cover_crop(picture, image, "/unused", target_width=size, target_height=size, **kw)


def test_an_earlier_size_finishing_last_does_not_land(image, queues):
    jobs, idles = queues
    picture = _Picture()
    _load(picture, image, 378)
    _load(picture, image, 321, keep_current=True)  # the layout settled on a smaller size
    for job in reversed(jobs):  # the later request's crop is ready first
        job()
    for apply in idles:
        apply()
    assert picture.size == (321, 321)
    assert [p.get_width() for p in picture.paintables if p is not None] == [321]


def test_a_new_size_keeps_the_image_up_until_its_crop_lands(image, queues):
    jobs, idles = queues
    picture = _Picture()
    _load(picture, image, 300)
    assert picture.paintables == [None]  # a first load has nothing to keep
    jobs.pop()()
    idles.pop()()
    shown = picture.paintables[-1]
    _load(picture, image, 321, keep_current=True)
    assert picture.paintables[-1] is shown  # no blank while the new crop is made
    jobs.pop()()
    idles.pop()()
    assert picture.paintables[-1].get_width() == 321 and picture.size == (321, 321)


def test_top_tracks_take_one_column_below_an_820_px_page():
    from actions import ui_actions

    # The page at Henry's tiles (sandbox, the docked sidebar 166-290 px by resize history):
    # 571 -> 561 (collapsed), 763 -> 596, 954 -> 664-788, 1145 -> 855-979, 1912 -> 1616.
    pages = (561, 596, 664, 745, 788, 855, 886, 979, 1616)
    assert [ui_actions._artist_top_tracks_cols(w) for w in pages] == [1, 1, 1, 1, 1, 2, 2, 2, 2]
    assert ui_actions._artist_top_tracks_cols(0) == 1
