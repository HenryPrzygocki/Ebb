"""Fork: Space is play/pause wherever focus is, except in text fields; Ctrl+arrows skip tracks."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_builders as ab  # noqa: E402

Gdk = ab.Gdk
CTRL = int(Gdk.ModifierType.CONTROL_MASK)
SHIFT = int(Gdk.ModifierType.SHIFT_MASK)


class _Node:
    def __init__(self, parent=None):
        self.parent = parent

    def get_parent(self):
        return self.parent


class _Text(_Node):
    """Stands in for Gtk.Editable / Gtk.TextView."""


class _Row(_Node):
    """Stands in for a focused list row, button or grid tile."""


@pytest.fixture(autouse=True)
def _text_types(monkeypatch):
    monkeypatch.setattr(ab, "_TEXT_INPUT_TYPES", (_Text,))


def _app(focus):
    calls = []
    app = SimpleNamespace(calls=calls, play_btn=object(), win=SimpleNamespace(get_focus=lambda: focus))
    app.on_play_pause = lambda _btn: calls.append("play_pause")
    app.on_next_track = lambda: calls.append("next")
    app.on_prev_track = lambda: calls.append("prev")
    return app


def _press(app, keyval, state=0):
    return ab.on_global_key_pressed(app, None, keyval, 0, state)


def _release(app, keyval):
    ab.on_global_key_released(app, None, keyval, 0, 0)


def test_space_on_a_focused_row_toggles_playback_and_never_reaches_the_row():
    app = _app(_Row(parent=_Node()))
    assert _press(app, Gdk.KEY_space) is True
    assert app.calls == ["play_pause"]


def test_space_with_nothing_focused_toggles_playback():
    app = _app(None)
    assert _press(app, Gdk.KEY_space) is True
    assert app.calls == ["play_pause"]


def test_space_in_a_text_field_types_a_space():
    app = _app(_Text(parent=_Node()))
    assert _press(app, Gdk.KEY_space) is False
    assert app.calls == []


def test_focus_inside_a_text_widget_counts_as_typing():
    app = _app(_Node(parent=_Text()))
    assert _press(app, Gdk.KEY_space) is False


def test_held_space_toggles_once_until_released():
    app = _app(_Row())
    for _ in range(5):
        assert _press(app, Gdk.KEY_space) is True
    assert app.calls == ["play_pause"]
    _release(app, Gdk.KEY_space)
    _press(app, Gdk.KEY_space)
    assert app.calls == ["play_pause", "play_pause"]


def test_keypad_space_and_shift_space_toggle_too():
    app = _app(_Row())
    _press(app, Gdk.KEY_KP_Space)
    _release(app, Gdk.KEY_KP_Space)
    _press(app, Gdk.KEY_space, SHIFT)
    assert app.calls == ["play_pause", "play_pause"]


def test_ctrl_space_is_left_to_the_focused_widget():
    app = _app(_Row())
    assert _press(app, Gdk.KEY_space, CTRL) is False
    assert app.calls == []


def test_ctrl_arrows_skip_tracks_even_over_a_focused_grid():
    app = _app(_Row())
    assert _press(app, Gdk.KEY_Right, CTRL) is True
    assert _press(app, Gdk.KEY_Left, CTRL) is True
    assert app.calls == ["next", "prev"]


def test_ctrl_arrows_in_a_text_field_move_by_word():
    app = _app(_Text())
    assert _press(app, Gdk.KEY_Right, CTRL) is False
    assert _press(app, Gdk.KEY_Left, CTRL) is False
    assert app.calls == []


def test_plain_arrows_and_letters_are_not_captured():
    app = _app(_Row())
    assert _press(app, Gdk.KEY_Right) is False
    assert _press(app, Gdk.KEY_q) is False
    assert app.calls == []


def test_escape_in_a_text_field_reaches_the_field_then_drops_focus(monkeypatch):
    idle = []
    monkeypatch.setattr(ab.GLib, "idle_add", lambda fn, *a: idle.append((fn, a)))
    focus = {"w": _Text(parent=_Node())}
    app = _app(None)
    app.win = SimpleNamespace(get_focus=lambda: focus["w"], set_focus=lambda w: focus.__setitem__("w", w))
    assert _press(app, Gdk.KEY_Escape) is False  # the entry still clears itself
    assert len(idle) == 1
    fn, args = idle[0]
    fn(*args)
    assert focus["w"] is None
    assert _press(app, Gdk.KEY_space) is True and app.calls == ["play_pause"]


def test_escape_outside_text_fields_is_left_to_the_panels():
    app = _app(_Row())
    assert _press(app, Gdk.KEY_Escape) is False
    assert app.calls == []
