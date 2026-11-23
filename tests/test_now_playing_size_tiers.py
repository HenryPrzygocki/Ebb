"""Fork: Now Playing's lyrics, rows and track info grow with the room their panels get."""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_now_playing as np  # noqa: E402
from ui import config as ui_config  # noqa: E402


def _tiers_for_surface(w, h):
    left_w, right_w = np._now_playing_split_widths(w, h)
    return np._now_playing_size_tiers(left_w, right_w, h)


def test_the_default_window_keeps_the_base_sizes():
    # 1280 x 1040: the cover takes the height, the right panel its 340 px minimum.
    assert _tiers_for_surface(1230, 880) == ("", "")


def test_a_full_width_window_on_a_1080p_screen_gets_the_large_tier_on_both_sides():
    # Henry's outputs are both 1920 x 1080 at scale 1: a full-width column leaves the surface
    # about 1830-1870 px wide and 930-1010 px tall.
    assert _tiers_for_surface(1870, 930) == ("np-right-l", "np-left-l")
    assert _tiers_for_surface(1830, 1010) == ("np-right-l", "np-left-l")


def test_a_1440p_window_gets_the_largest_sizes_on_both_sides():
    assert _tiers_for_surface(2510, 1290) == ("np-right-xl", "np-left-xl")


def test_a_wide_but_short_window_is_held_back_by_its_height():
    right, left = _tiers_for_surface(2000, 600)
    assert right == "np-right-m" and left == ""


class _Surface:
    def __init__(self):
        self.classes = {"now-playing-surface"}

    def has_css_class(self, name):
        return name in self.classes

    def add_css_class(self, name):
        self.classes.add(name)

    def remove_css_class(self, name):
        self.classes.discard(name)


def test_tier_classes_follow_resizes_and_report_changes():
    from types import SimpleNamespace

    app = SimpleNamespace(now_playing_surface=_Surface())
    assert np._apply_now_playing_size_tiers(app, 1290, 1200, 1290) is True
    assert {"np-right-xl", "np-left-xl"} <= app.now_playing_surface.classes
    assert np._apply_now_playing_size_tiers(app, 1290, 1200, 1290) is False  # nothing to redo
    assert np._apply_now_playing_size_tiers(app, 868, 340, 880) is True
    assert app.now_playing_surface.classes == {"now-playing-surface"}
    # Fakes without CSS-class methods (older tests) are left alone.
    assert np._apply_now_playing_size_tiers(SimpleNamespace(now_playing_surface=object()), 1290, 1200, 1290) is False


def _px(selector):
    m = re.search(re.escape(selector) + r"\s*\{[^}]*font-size:\s*([\d.]+)(px|em)", ui_config.CSS_DATA)
    assert m, f"no font-size rule for {selector}"
    return float(m.group(1))


def test_every_tier_is_styled_and_each_step_is_bigger():
    lyric = [_px(f".{t} .now-playing-lyrics-box .lyric-line") for t in ("np-right-m", "np-right-l", "np-right-xl")]
    active = [_px(f".{t} .now-playing-lyrics-box .lyric-line.active") for t in ("np-right-m", "np-right-l", "np-right-xl")]
    rows = [_px(f".{t} .now-playing-track-row") for t in ("np-right-m", "np-right-l", "np-right-xl")]
    titles = [_px(f".{t} .now-playing-title") for t in ("np-left-l", "np-left-xl")]
    assert 16 < lyric[0] < lyric[1] < lyric[2]  # base .lyric-line is 16px
    assert 20 < active[0] < active[1] < active[2]  # base active line is 20px
    assert 1.0 < rows[0] < rows[1] < rows[2]
    assert 30 < titles[0] < titles[1]  # base .now-playing-title is 30px
    for name in np._NOW_PLAYING_TIER_CLASSES:
        assert f".{name} " in ui_config.CSS_DATA


def test_the_album_column_widens_in_steps_with_the_panel():
    assert np._now_playing_album_chars_for(480) == 14  # the width every panel had
    assert np._now_playing_album_chars_for(600) == 18
    assert np._now_playing_album_chars_for(865) == 22  # 1920 x 1080
    assert np._now_playing_album_chars_for(1145) == 30  # 2560 x 1440
    assert np._now_playing_album_chars_for(3000) == 30


class _Node:
    def __init__(self, classes=(), children=()):
        self.classes, self.children = set(classes), list(children)
        self.visible, self.chars, self.max_chars, self.parent_next = True, 14, 14, None

    def has_css_class(self, name):
        return name in self.classes

    def get_first_child(self):
        return self.children[0] if self.children else None

    def get_next_sibling(self):
        return self.parent_next

    def set_visible(self, v):
        self.visible = v

    def set_width_chars(self, n):
        self.chars = n

    def set_max_width_chars(self, n):
        self.max_chars = n


def _tree(*children):
    root = _Node(children=children)
    for a, b in zip(children, children[1:]):
        a.parent_next = b
    return root


def test_rows_already_built_take_the_new_album_width(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(np, "_now_playing_album_column", True)
    monkeypatch.setattr(np, "_now_playing_album_chars", 14)
    album_a, album_b = _Node({"now-playing-track-album"}), _Node({"now-playing-track-album"})
    title = _Node({"track-title"})
    app = SimpleNamespace(now_playing_queue_list=_tree(_tree(title, album_a)), now_playing_track_list=_tree(album_b))

    np._set_now_playing_album_column(app, True, 30)
    assert (album_a.chars, album_a.max_chars, album_b.chars) == (30, 30, 30)
    assert title.chars == 14  # only the album cells
    np._set_now_playing_album_column(app, False)  # keeps the width, hides the column
    assert not album_a.visible and album_a.chars == 30 and np._now_playing_album_chars == 30
