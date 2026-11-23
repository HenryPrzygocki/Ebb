"""Fork: the layout follows the window's real size, not only notify::default-width.

GTK keeps the default size current only for a floating window. A tiled one (niri with
prefer-no-csd tiles every window) is resized without that notify, so nothing hung on it ran:
Now Playing kept the layout of the width it was opened at, clipped by the narrower window."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import ui_actions  # noqa: E402
from app import app_bootstrap, app_ui_loop  # noqa: E402
from ui import config as ui_config  # noqa: E402


class _Area:
    def __init__(self, **kw):
        self.kw, self.handlers = kw, {}

    def connect(self, name, fn):
        self.handlers[name] = fn


class _Overlay:
    def __init__(self):
        self.overlays = []

    def add_overlay(self, widget):
        self.overlays.append(widget)


def test_the_probe_reports_every_real_size_change_once(monkeypatch):
    idle, updates = [], []
    monkeypatch.setattr(app_bootstrap, "Gtk", SimpleNamespace(DrawingArea=_Area))
    monkeypatch.setattr(app_bootstrap.GLib, "idle_add", lambda fn: idle.append(fn) or len(idle))
    app = SimpleNamespace(body_overlay=_Overlay(), update_layout_proportions=lambda w, p: updates.append((w, p)))

    app_bootstrap._watch_content_size(app)

    [probe] = app.body_overlay.overlays
    assert probe.kw["can_target"] is False  # clicks pass through it
    resized = probe.handlers["resize"]
    resized(probe, 1912, 980)
    resized(probe, 1337, 980)  # again before the idle ran: still one update
    assert len(idle) == 1
    assert idle.pop()() is False and updates == [(None, None)]
    resized(probe, 1337, 980)  # the same size
    assert idle == []
    resized(probe, 571, 980)
    idle.pop()()
    assert updates == [(None, None), (None, None)]


def test_no_body_overlay_is_not_an_error():
    app_bootstrap._watch_content_size(SimpleNamespace())


def _layout_app(moved, resynced):
    return SimpleNamespace(
        login_prompt_box=None,
        win=SimpleNamespace(get_width=lambda: 1912, get_height=lambda: 1030),
        paned=SimpleNamespace(set_position=moved.append),
        body_overlay=SimpleNamespace(get_height=lambda: 980),
        queue_anchor=None,
        _schedule_now_playing_surface_resync=lambda: resynced.append("now-playing"),
        _history_grid_layout_refresh=lambda: False,
        _schedule_viz_handle_realign=lambda animate=False: None,
    )


def test_a_size_change_resyncs_the_layout_but_leaves_the_sidebar(monkeypatch):
    idle, moved, resynced = [], [], []
    monkeypatch.setattr(app_ui_loop.GLib, "idle_add", lambda fn, *a: idle.append(fn) or 1)
    app = _layout_app(moved, resynced)

    app_ui_loop.update_layout_proportions(app, None, None)  # from the content-size watch

    assert resynced == ["now-playing"]
    assert app._history_grid_layout_refresh in idle
    assert moved == []  # in a tile the sidebar has always kept its width


def test_the_windows_own_resize_still_scales_the_sidebar(monkeypatch):
    moved, resynced = [], []
    monkeypatch.setattr(app_ui_loop.GLib, "idle_add", lambda fn, *a: 1)
    app = _layout_app(moved, resynced)

    app_ui_loop.update_layout_proportions(app, object(), None)  # notify::default-width

    assert moved == [int(1912 * ui_config.SIDEBAR_RATIO)] and resynced == ["now-playing"]


def _win(allocated, default, state):
    surface = SimpleNamespace(get_state=lambda: state)
    return SimpleNamespace(
        get_width=lambda: allocated, get_default_size=lambda: (default, 800), get_surface=lambda: surface
    )


def test_a_tiled_window_is_laid_out_for_its_real_width():
    Gdk = ui_actions.Gdk
    # A niri column: 571 px wide, while the default size still says 1280.
    assert ui_actions._window_layout_width(_win(571, 1280, Gdk.ToplevelState.TILED)) == 571
    assert ui_actions._window_layout_width(_win(1912, 1280, Gdk.ToplevelState.MAXIMIZED)) == 1912
    assert ui_actions._window_layout_width(_win(1912, 1280, Gdk.ToplevelState.FULLSCREEN)) == 1912


def test_a_floating_window_is_laid_out_for_its_intended_width():
    Gdk = ui_actions.Gdk
    # Leaving mini mode: the default size is already 1280 while the allocation still says 390.
    assert ui_actions._window_layout_width(_win(390, 1280, Gdk.ToplevelState(0))) == 1280
    assert ui_actions._window_layout_width(_win(900, 0, Gdk.ToplevelState(0))) == 900  # no default yet
    assert ui_actions._window_layout_width(SimpleNamespace(get_width=lambda: 900)) == 900  # a bare fake
