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


# --- bubble-phase panel keys (on_key_pressed) ---

class _Revealer:
    def __init__(self, open_=False):
        self.open = open_

    def get_reveal_child(self):
        return self.open


def _panel_app(focus, workspace_open=False):
    calls = []
    app = SimpleNamespace(
        calls=calls,
        win=SimpleNamespace(get_focus=lambda: focus),
        viz_btn=object(),
        viz_revealer=_Revealer(workspace_open),
        queue_revealer=_Revealer(True),
        now_playing_revealer=_Revealer(True),
        settings={"viz_expanded": workspace_open},
    )
    app.toggle_queue_drawer = lambda *_a: calls.append("queue")
    app.toggle_now_playing_overlay = lambda *_a: calls.append("now-playing")
    app.toggle_visualizer = lambda _btn: calls.append("workspace")
    app._set_visualizer_expanded = lambda on: calls.append(f"expanded={on}")
    app.schedule_save_settings = lambda: calls.append("save")
    app._quit_from_tray = lambda: calls.append("quit")
    return app


def _key(app, keyval, state=0):
    return ab.on_key_pressed(app, None, keyval, 0, state)


def test_e_toggles_the_workspace_and_tab_is_left_to_focus_navigation():
    app = _panel_app(_Row())
    assert _key(app, Gdk.KEY_e) is True
    assert _key(app, Gdk.KEY_Tab) is False
    assert _key(app, Gdk.KEY_ISO_Left_Tab, SHIFT) is False
    assert app.calls == ["workspace"]


def test_panel_letters_are_typed_into_a_text_field_even_with_their_panel_open():
    app = _panel_app(_Text())
    for keyval in (Gdk.KEY_q, Gdk.KEY_w, Gdk.KEY_e):
        assert _key(app, keyval) is False
    assert app.calls == []


def test_ctrl_q_quits_and_ctrl_w_does_not_toggle_a_panel():
    app = _panel_app(_Row())
    assert _key(app, Gdk.KEY_q, CTRL) is True
    assert _key(app, Gdk.KEY_w, CTRL) is False
    assert app.calls == ["quit"]


def test_escape_folds_the_workspace_and_remembers_it():
    app = _panel_app(None, workspace_open=True)
    app.queue_revealer.open = app.now_playing_revealer.open = False
    app.hide_now_playing_overlay = app.close_queue_drawer = lambda: app.calls.append("wrong panel")
    assert _key(app, Gdk.KEY_Escape) is True
    assert app.calls == ["expanded=False", "save"]
    assert app.settings["viz_expanded"] is False


ALT = int(Gdk.ModifierType.ALT_MASK)


class _BackButton:
    def __init__(self, sensitive):
        self.sensitive = sensitive

    def get_sensitive(self):
        return self.sensitive


def _back_app(focus, sensitive=True):
    app = _app(focus)
    app.back_btn = _BackButton(sensitive)
    app.on_back_clicked = lambda btn: app.calls.append(("back", btn))
    return app


def test_alt_left_and_the_back_key_go_back_like_the_header_button():
    app = _back_app(_Row())
    assert _press(app, Gdk.KEY_Left, ALT) is True
    assert _press(app, Gdk.KEY_Back) is True
    assert ab._go_back(app) is True  # what the mouse's back button calls
    assert app.calls == [("back", app.back_btn)] * 3


def test_alt_left_does_nothing_when_there_is_nowhere_to_go_back_to():
    app = _back_app(_Row(), sensitive=False)
    assert _press(app, Gdk.KEY_Left, ALT) is False
    assert app.calls == []


def test_alt_left_in_a_text_field_is_left_to_the_field():
    app = _back_app(_Text())
    assert _press(app, Gdk.KEY_Left, ALT) is False
    assert app.calls == []



# --- Fork: Shift+Left/Right seek, Ctrl+Up/Down volume -------------------------------------------

class _Player:
    def __init__(self, pos=60.0, dur=200.0, hw_volume=False):
        self.pos, self.dur, self.seeks, self.hw = pos, dur, [], hw_volume

    def get_position(self):
        return self.pos, self.dur

    def seek(self, target):
        self.seeks.append(target)

    def usb_hw_volume_supported(self):
        return self.hw


@pytest.fixture
def timers(monkeypatch):
    """Collects GLib timeouts instead of running a main loop."""
    pending = []
    monkeypatch.setattr(ab.GLib, "timeout_add", lambda ms, fn, *a: pending.append((fn, a)) or len(pending))
    monkeypatch.setattr(ab.GLib, "source_remove", lambda _sid: None)
    return pending


def _player_app(focus=None, **player):
    app = _app(focus if focus is not None else _Row(parent=_Node()))
    app.player = _Player(**player)
    app.playing_track = object()
    app.lbl_current_time = SimpleNamespace(text="", set_text=lambda t: setattr(app.lbl_current_time, "text", t))
    app._mpris_emit_seeked = lambda t: app.calls.append(("seeked", t))
    app._mpris_sync_position = lambda force=False: app.calls.append(("sync", force))
    return app


def test_shift_arrows_seek_ten_seconds_once_the_held_key_settles(timers):
    app = _player_app()
    for _ in range(3):  # key repeat while held
        assert _press(app, Gdk.KEY_Right, SHIFT) is True
    assert app.player.seeks == [] and app.lbl_current_time.text == "1:30"
    fn, args = timers[-1]
    fn(*args)
    assert app.player.seeks == [90.0]
    assert ("seeked", 90.0) in app.calls and ("sync", True) in app.calls
    _press(app, Gdk.KEY_Left, SHIFT)
    timers[-1][0](*timers[-1][1])
    assert app.player.seeks[-1] == 50.0  # from the real position (60 s in this fake)


def test_seeking_stops_short_of_the_end_and_at_zero(timers):
    app = _player_app(pos=195.0, dur=200.0)
    _press(app, Gdk.KEY_Right, SHIFT)
    timers[-1][0](*timers[-1][1])
    app.player.pos = 4.0
    _press(app, Gdk.KEY_Left, SHIFT)
    timers[-1][0](*timers[-1][1])
    assert app.player.seeks == [199.0, 0.0]


def test_shift_arrows_still_select_text_and_do_nothing_without_a_track(timers):
    app = _player_app(focus=_Text())
    assert _press(app, Gdk.KEY_Right, SHIFT) is False
    app = _player_app()
    app.playing_track = None
    assert _press(app, Gdk.KEY_Right, SHIFT) is False and timers == []


def _volume_app(value=50.0, bit_perfect=False, hw_volume=False, focus=None):
    app = _player_app(focus=focus, hw_volume=hw_volume)
    app.settings = {"bit_perfect": bit_perfect}
    app.vol_scale = SimpleNamespace(value=value, get_value=lambda: app.vol_scale.value,
                                    set_value=lambda v: setattr(app.vol_scale, "value", v))
    app.show_output_notice = lambda text, state="idle", ms=0, icon=None: app.calls.append((text, icon))
    return app


def test_ctrl_up_down_change_the_volume_in_fives_and_say_so():
    app = _volume_app(value=50.0)
    assert _press(app, Gdk.KEY_Up, CTRL) is True
    assert app.vol_scale.value == 55 and app.calls[-1] == ("Volume 55 %", "hiresti-volume-medium-symbolic")
    app.vol_scale.value = 2.0
    _press(app, Gdk.KEY_Down, CTRL)
    assert app.vol_scale.value == 0 and app.calls[-1] == ("Volume 0 %", "hiresti-volume-muted-symbolic")


def test_bit_perfect_volume_stays_put_unless_the_dac_has_hardware_volume():
    app = _volume_app(value=100.0, bit_perfect=True)
    _press(app, Gdk.KEY_Down, CTRL)
    assert app.vol_scale.value == 100.0 and "bit-perfect" in app.calls[-1][0]
    app = _volume_app(value=100.0, bit_perfect=True, hw_volume=True)
    _press(app, Gdk.KEY_Down, CTRL)
    assert app.vol_scale.value == 95


def test_ctrl_up_down_are_left_to_text_fields():
    app = _volume_app(focus=_Text())
    assert _press(app, Gdk.KEY_Up, CTRL) is False and app.vol_scale.value == 50.0
