"""Fork: window translucency (ui/glass.py), the Back/Escape layer rules (actions/layers.py) and
where Now Playing puts the cover (app_now_playing._now_playing_cover_box)."""
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import layers  # noqa: E402
from app import app_now_playing as np  # noqa: E402
from ui import glass  # noqa: E402


# --- glass -------------------------------------------------------------------------------

def _selectors(css):
    for block in re.findall(r"([^{}]+)\{", css):
        for selector in block.split(","):
            if selector.strip():
                yield selector.strip()


def test_no_transparency_means_no_stylesheet():
    assert glass.css(0, dark=True) == ""
    assert glass.css(0.0, dark=False) == ""


def test_every_rule_is_scoped_to_the_main_window():
    for dark in (True, False):
        selectors = list(_selectors(glass.css(0.3, dark)))
        assert selectors
        assert all(s.startswith(f"window.{glass.CSS_CLASS}") for s in selectors), selectors


def test_light_mode_is_less_transparent_than_dark():
    assert glass.opacity(0.25, dark=True) == pytest.approx(0.75)
    assert glass.opacity(0.25, dark=False) == pytest.approx(1 - 0.25 * glass.LIGHT_SHARE)
    assert "alpha(@window_bg_color, 0.750)" in glass.css(0.25, dark=True)
    assert "alpha(@window_bg_color, 0.850)" in glass.css(0.25, dark=False)


def test_what_floats_over_the_content_stays_opaque():
    css = glass.css(glass.MAX, dark=True)
    for opaque in ("sidebar-floating", "queue-drawer", "queue-handle", "now-playing", "popover", "dialog"):
        assert opaque not in css


def test_the_setting_is_clamped_and_defaults_sanely():
    assert glass.amount({}) == glass.DEFAULT
    assert glass.amount(None) == glass.DEFAULT
    assert glass.amount({glass.SETTING: "nonsense"}) == glass.DEFAULT
    assert glass.amount({glass.SETTING: 5}) == glass.MAX
    assert glass.amount({glass.SETTING: -1}) == 0.0
    assert glass.amount({glass.SETTING: 0.4}) == pytest.approx(0.4)


# --- layers ------------------------------------------------------------------------------

class Revealer:
    def __init__(self, revealed=False):
        self.revealed = revealed

    def get_reveal_child(self):
        return self.revealed


class Stack:
    def __init__(self, visible, names=("grid_view", "tracks", "settings", "search_view")):
        self.visible, self.names = visible, set(names)

    def get_visible_child_name(self):
        return self.visible

    def set_visible_child_name(self, name):
        self.visible = name

    def get_child_by_name(self, name):
        return object() if name in self.names else None


class Btn:
    def __init__(self, page_back):
        self.page_back = page_back

    def get_sensitive(self):
        return self.page_back


def _app(view="grid_view", page_back=False, **revealed):
    calls = []
    app = SimpleNamespace(
        right_stack=Stack(view),
        back_btn=Btn(page_back),
        now_playing_revealer=Revealer(revealed.get("now_playing", False)),
        queue_revealer=Revealer(revealed.get("queue", False)),
        viz_revealer=Revealer(revealed.get("workspace", False)),
        settings={"viz_expanded": True},
        calls=calls,
    )
    app._hide_sidebar_overlay = lambda: revealed.get("sidebar", False) and (calls.append("sidebar") or True)
    app.hide_now_playing_overlay = lambda: calls.append("now_playing")
    app.close_queue_drawer = lambda: calls.append("queue")
    app._set_visualizer_expanded = lambda value: calls.append(("workspace", value))
    app.schedule_save_settings = lambda: calls.append("save")
    app.on_back_clicked = lambda btn: calls.append("page_back")
    return app


def test_back_closes_the_top_layer_first():
    app = _app(page_back=True, sidebar=True, now_playing=True, queue=True)
    assert layers.step_back(app)
    assert app.calls == ["sidebar"]
    app = _app(page_back=True, now_playing=True, queue=True)
    assert layers.step_back(app)
    assert app.calls == ["now_playing"]
    app = _app(page_back=True, queue=True)
    assert layers.step_back(app)
    assert app.calls == ["queue"]


def test_back_leaves_the_workspace_open_but_escape_folds_it():
    app = _app(page_back=True, workspace=True)
    assert layers.step_back(app)
    assert app.calls == ["page_back"]
    app = _app(page_back=True, workspace=True)
    assert layers.step_back(app, escape=True)
    assert app.calls == [("workspace", False), "save"]
    assert app.settings["viz_expanded"] is False


def test_settings_returns_to_the_page_it_was_opened_from():
    app = _app(view="tracks", page_back=True)
    layers.open_settings(app)
    assert app.right_stack.visible == "settings"
    assert layers.layer_open(app)
    layers.open_settings(app)  # again: still returns to the tracks, not to Settings
    assert layers.step_back(app)
    assert app.right_stack.visible == "tracks"
    assert app.calls == []  # the page history was not touched
    assert not layers.layer_open(app)


def test_settings_falls_back_to_the_grid_when_its_page_is_gone():
    app = _app(view="tracks")
    layers.open_settings(app)
    app.right_stack.names.discard("tracks")
    layers.step_back(app)
    assert app.right_stack.visible == "grid_view"


def test_the_mini_player_only_closes_its_queue():
    app = _app(view="settings", page_back=True, now_playing=True)
    app.is_mini_mode = True
    app.mini_queue_revealer = Revealer(True)
    app.close_mini_queue = lambda: app.calls.append("mini_queue")
    assert layers.step_back(app, escape=True)
    assert app.calls == ["mini_queue"]
    app.mini_queue_revealer.revealed = False
    assert not layers.step_back(app, escape=True)
    assert app.right_stack.visible == "settings"


def test_nothing_to_step_out_of():
    app = _app(page_back=False)
    assert not layers.step_back(app)
    assert not layers.step_back(app, escape=True)
    assert app.calls == []


def test_the_back_button_keeps_the_page_state_apart_from_the_layers():
    from gi.repository import Gdk, Gtk

    if not (os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY")):
        pytest.skip("no display: GTK widgets crash without one")
    Gtk.init_check()
    if Gdk.Display.get_default() is None:
        pytest.skip("no display")
    btn = layers.BackButton(icon_name="go-previous-symbolic", sensitive=False)
    assert not btn.get_sensitive()
    btn.set_layer_open(True)
    assert btn.get_sensitive() and not btn.page_back
    btn.set_sensitive(False)  # page code, while Now Playing is open
    assert btn.get_sensitive()
    btn.set_layer_open(False)
    assert not btn.get_sensitive()
    btn.set_sensitive(True)
    assert btn.get_sensitive() and btn.page_back


# --- Now Playing cover -------------------------------------------------------------------

def test_a_tall_panel_puts_the_cover_above_the_track_info():
    box = np._now_playing_cover_box(534, 873, 330)
    assert box is not None
    x, y, size = box
    assert x >= 0 and x + size <= 534
    assert y >= np._NOW_PLAYING_TOP_BAR_H
    assert y + size <= 873 - 330  # never under the info
    assert size >= np._NOW_PLAYING_STACKED_MIN_SHARE * 534


def test_a_square_or_wide_panel_lets_the_cover_fill_it():
    assert np._now_playing_cover_box(693, 691, 330) is None
    assert np._now_playing_cover_box(613, 611, 330) is None


def test_no_cover_box_before_the_info_is_measured():
    assert np._now_playing_cover_box(534, 873, 0) is None
    assert np._now_playing_cover_box(0, 873, 330) is None
