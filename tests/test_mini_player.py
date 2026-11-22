"""Fork: the mini player's two layouts, a strip and a cover (ui/mini_player.py, #18)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from core.settings import normalize_settings  # noqa: E402
from ui import mini_player  # noqa: E402


def test_settings_keep_a_known_layout_and_a_usable_cover_size():
    assert normalize_settings({})["mini_layout"] == "strip"
    assert normalize_settings({"mini_layout": "cover"})["mini_layout"] == "cover"
    assert normalize_settings({"mini_layout": "huge"})["mini_layout"] == "strip"
    kept = normalize_settings({"mini_cover_width": 460, "mini_cover_height": 700})
    assert (kept["mini_cover_width"], kept["mini_cover_height"]) == (460, 700)
    small = normalize_settings({"mini_cover_width": 10, "mini_cover_height": 10})
    assert small["mini_cover_width"] >= mini_player.COVER_MIN[0]
    assert small["mini_cover_height"] >= mini_player.COVER_MIN[1]


def test_the_cover_asks_tidal_for_640_px():
    def tidal_url(ref, width=320, height=320):
        return f"https://resources.tidal.com/images/{ref.replace('-', '/')}/{width}x{height}.jpg"

    app = SimpleNamespace(_get_tidal_image_url=tidal_url)
    assert mini_player.cover_url(app, "ab-cd") == "https://resources.tidal.com/images/ab/cd/640x640.jpg"
    assert mini_player.cover_url(app, tidal_url("ab-cd")) == "https://resources.tidal.com/images/ab/cd/640x640.jpg"
    assert mini_player.cover_url(app, "/home/me/cover.jpg") == "/home/me/cover.jpg"
    assert mini_player.cover_url(app, None) is None


def test_the_layout_button_switches_and_keeps_the_choice():
    saved = []
    app = SimpleNamespace(settings={"mini_layout": "strip"}, is_mini_mode=False,
                          schedule_save_settings=lambda: saved.append(True))
    mini_player.toggle(app)
    assert mini_player.layout(app) == mini_player.COVER and app.settings["mini_layout"] == "cover"
    mini_player.toggle(app)
    assert mini_player.layout(app) == mini_player.STRIP
    assert len(saved) == 2


def test_the_cover_window_comes_back_at_the_size_it_had():
    # The default size, which follows resizing and is what set_default_size takes; the
    # allocation differs from it by the window frame, and the window shrank by that every time.
    saved = []
    win = SimpleNamespace(get_default_size=lambda: (460, 700), get_width=lambda: 450, get_height=lambda: 690)
    app = SimpleNamespace(win=win, settings={}, schedule_save_settings=lambda: saved.append(True))
    mini_player._remember_cover_size(app)
    assert mini_player.cover_size(app) == (460, 700) and saved
    # Nothing usable to remember: the default size stands.
    app = SimpleNamespace(win=SimpleNamespace(get_default_size=lambda: (0, 0), get_width=lambda: 0, get_height=lambda: 0),
                          settings={}, schedule_save_settings=lambda: saved.append(True))
    mini_player._remember_cover_size(app)
    assert mini_player.cover_size(app) == mini_player.COVER_DEFAULT
