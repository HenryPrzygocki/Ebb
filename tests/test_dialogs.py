"""Fork: the small dialogs (ui/dialogs.py) and the call sites that moved onto them.

They were hand-built Gtk.Dialog windows titled only in a title bar, which a compositor without
title bars (niri) showed as untitled boxes with a plain Delete button."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_playlist  # noqa: E402
from ui import dialogs  # noqa: E402


class _Alert:
    def __init__(self, heading="", body=""):
        self.heading, self.body = heading, body
        self.responses, self.appearance, self.handlers = [], {}, []
        self.default = self.close = self.extra = self.focus = self.parent = None

    def add_response(self, response_id, label):
        self.responses.append((response_id, label))

    def set_response_appearance(self, response_id, appearance):
        self.appearance[response_id] = appearance

    def set_default_response(self, response_id):
        self.default = response_id

    def set_close_response(self, response_id):
        self.close = response_id

    def set_extra_child(self, widget):
        self.extra = widget

    def set_focus(self, widget):
        self.focus = widget

    def connect(self, _signal, handler):
        self.handlers.append(handler)

    def present(self, parent):
        self.parent = parent

    def respond(self, response_id):
        for handler in self.handlers:
            handler(self, response_id)


class _Widget:
    def __init__(self, **kw):
        self.kw, self.children, self.selected = kw, [], 0
        self.text = kw.get("text", "")

    def append(self, child):
        self.children.append(child)

    def get_text(self):
        return self.text

    def get_selected(self):
        return self.selected

    def set_selected(self, index):
        self.selected = index

    def set_enable_search(self, on):
        self.search = on

    def get_active(self):
        return self.kw.get("active", False)

    def __getattr__(self, name):
        if name.startswith("set_"):
            return lambda *_a, **_k: None
        raise AttributeError(name)


@pytest.fixture
def toolkit(monkeypatch):
    appearance = SimpleNamespace(DESTRUCTIVE="destructive", SUGGESTED="suggested")
    monkeypatch.setattr(dialogs, "Adw", SimpleNamespace(AlertDialog=_Alert, ResponseAppearance=appearance))
    monkeypatch.setattr(
        dialogs,
        "Gtk",
        SimpleNamespace(
            Entry=_Widget,
            DropDown=_Widget,
            Box=_Widget,
            StringList=SimpleNamespace(new=list),
            StringObject=object,
            PropertyExpression=SimpleNamespace(new=lambda *_a: "expression"),
            Orientation=SimpleNamespace(VERTICAL="vertical"),
        ),
    )
    return SimpleNamespace(win="the window")


def test_a_destructive_confirmation_takes_a_deliberate_click(toolkit):
    done = []
    dialog = dialogs.confirm(toolkit, "Delete Playlist?", "It will be gone.", "Delete", lambda: done.append(1), destructive=True)
    assert dialog.heading == "Delete Playlist?" and dialog.parent == "the window"  # titled, inside the window
    assert dialog.responses == [("cancel", "Cancel"), ("confirm", "Delete")]
    assert dialog.appearance == {"confirm": "destructive"}
    assert dialog.default == "cancel" and dialog.close == "cancel"  # Enter and Escape both keep it
    dialog.respond("cancel")
    assert done == []
    dialog.respond("confirm")
    assert done == [1]


def test_an_ordinary_confirmation_defaults_to_yes(toolkit):
    dialog = dialogs.confirm(toolkit, "Move?", "", "Move", lambda: None)
    assert dialog.default == "confirm" and dialog.close == "cancel" and dialog.appearance == {"confirm": "suggested"}


def test_a_message_runs_its_callback_however_it_is_dismissed(toolkit):
    closed = []
    dialog = dialogs.message(toolkit, "Pro-Audio Mode", "It will be switched.", on_close=lambda: closed.append(1))
    assert dialog.responses == [("confirm", "OK")] and dialog.default == dialog.close == "confirm"
    dialog.respond("confirm")
    assert closed == [1]


def test_a_text_prompt_submits_on_enter_and_hands_over_even_an_empty_name(toolkit):
    got = []
    dialog = dialogs.prompt_text(toolkit, "New Folder", "Organize playlists.", "  Name  ", got.append, save_label="Create")
    entry = dialog.extra
    assert entry.kw["activates_default"] is True and dialog.default == "confirm" and dialog.focus is entry
    assert dialog.responses == [("cancel", "Cancel"), ("confirm", "Create")]
    dialog.respond("cancel")
    assert got == []
    dialog.respond("confirm")
    entry.text = "   "
    dialog.respond("confirm")
    assert got == ["Name", ""]  # the callers decide what an empty name means


def test_a_picker_reports_the_chosen_index_and_its_extra_buttons(toolkit):
    chosen, extra = [], []
    check = _Widget(active=True)
    dialog = dialogs.choose(
        toolkit, "Add to Playlist", "", ["One", "Two", "Three"], "Add", chosen.append,
        extra_child=check, extra_responses=(("New Playlist", lambda: extra.append("new")),),
    )
    dropdown, also = dialog.extra.children
    assert also is check and dropdown.kw["model"] == ["One", "Two", "Three"]
    assert dropdown.search is False  # a short list needs no filter
    assert dialog.responses == [("cancel", "Cancel"), ("extra-0", "New Playlist"), ("confirm", "Add")]
    dropdown.selected = 2
    dialog.respond("confirm")
    dialog.respond("extra-0")
    dialog.respond("cancel")
    assert chosen == [2] and extra == ["new"]
    long = dialogs.choose(toolkit, "Add to Playlist", "", [str(i) for i in range(20)], "Add", chosen.append)
    assert long.extra.children[0].search is True  # type to filter a long one


# --- call sites --------------------------------------------------------------------------------

@pytest.fixture
def inline(monkeypatch):
    """Run the daemon tasks and idle callbacks at once."""
    monkeypatch.setattr(app_playlist, "submit_daemon", lambda fn: fn())
    monkeypatch.setattr(app_playlist.GLib, "idle_add", lambda fn, *a: fn(*a))
    shown = []
    for name in ("confirm", "choose", "prompt_text", "message"):
        monkeypatch.setattr(app_playlist.dialogs, name, lambda *a, _n=name, **k: shown.append((_n, a, k)))
    return shown


def _app(**backend):
    notices = []
    return SimpleNamespace(
        backend=SimpleNamespace(user=object(), **backend),
        show_output_notice=lambda *a: notices.append(a[0]),
        render_playlists_home=lambda: notices.append("render"),
        current_remote_playlist=None,
        notices=notices,
    )


def test_deleting_a_tidal_playlist_asks_first_and_names_it(inline):
    deleted = []
    app = _app(delete_cloud_playlist=lambda pl: deleted.append(pl) or {"ok": True})
    playlist = SimpleNamespace(id="p1", name="Road Trip")

    app_playlist.on_remote_playlist_delete_clicked(app, playlist)

    [(kind, args, kwargs)] = inline
    assert kind == "confirm" and kwargs == {"destructive": True}
    _self, heading, body, label, on_confirm = args
    assert heading == "Delete Playlist?" and "Road Trip" in body and label == "Delete"
    assert deleted == []  # nothing until the answer
    on_confirm()
    assert deleted == [playlist] and "Playlist deleted." in app.notices


def test_deleting_a_local_playlist_asks_first(inline):
    removed = []
    app = SimpleNamespace(
        playlist_mgr=SimpleNamespace(delete_playlist=removed.append), render_playlists_home=lambda: None
    )
    app_playlist.on_playlist_delete_clicked(app, "local-1")
    [(kind, args, kwargs)] = inline
    assert kind == "confirm" and kwargs == {"destructive": True} and removed == []
    args[-1]()
    assert removed == ["local-1"] and app.current_playlist_id is None


def test_moving_a_playlist_lists_the_folders_off_the_main_thread(inline, monkeypatch):
    order = []
    monkeypatch.setattr(app_playlist, "submit_daemon", lambda fn: (order.append("thread"), fn())[1])
    moved = []
    app = _app(
        get_all_playlist_folders=lambda limit=1000: order.append("request") or [{"id": "f2", "path": "Rock / Live"}],
        move_cloud_playlist_to_folder=lambda pl, target_folder_id: moved.append(target_folder_id) or {"ok": True},
    )
    app_playlist.on_remote_playlist_move_to_folder_clicked(app, SimpleNamespace(id="p1"))
    assert order[:2] == ["thread", "request"]  # it ran on the main thread before the dialog
    [(kind, args, _kwargs)] = inline
    assert kind == "choose" and args[1] == "Move to Folder" and args[3] == ["Root", "Rock / Live"] and args[4] == "Move"
    args[5](1)
    assert moved == ["f2"]


def test_add_to_playlist_offers_the_playlists_a_new_one_and_the_duplicate_check(inline, monkeypatch):
    monkeypatch.setattr(app_playlist, "Gtk", SimpleNamespace(CheckButton=_Widget))  # no display here
    playlists = [SimpleNamespace(name="One"), SimpleNamespace(name=None)]
    picked = []
    app = _app(get_user_playlists=lambda limit=1000: playlists)
    app._show_simple_dialog = lambda *a: None

    app_playlist._prompt_playlist_pick(app, lambda pl, dedupe: picked.append((pl, dedupe)))

    [(kind, args, kwargs)] = inline
    assert kind == "choose" and args[1] == "Add to Playlist" and args[3] == ["One", "Untitled Playlist"]
    assert [label for label, _cb in kwargs["extra_responses"]] == ["New Playlist"]
    args[5](0)
    assert picked == [(playlists[0], kwargs["extra_child"].get_active())]


def test_the_name_prompt_and_the_message_dialog_use_the_shared_look(inline, monkeypatch):
    from app import app_builders

    got = []
    app = SimpleNamespace(win=None)
    app_playlist._prompt_playlist_name(
        app, "New Folder", "New Folder", got.append, subtitle="Why", placeholder="Folder name", save_label="Create",
        dialog_size=(480, 220),
    )
    [(kind, args, kwargs)] = inline
    assert kind == "prompt_text" and args[1:4] == ("New Folder", "Why", "New Folder") and args[4] == got.append
    assert kwargs == {"placeholder": "Folder name", "save_label": "Create"}

    shown = []
    monkeypatch.setattr(app_builders.dialogs, "message", lambda *a, **k: shown.append(a))
    app_builders._show_simple_dialog(app, "Playback blocked", "Why it is blocked.")
    assert shown == [(app, "Playback blocked", "Why it is blocked.")]


def test_a_dialog_from_the_mini_player_brings_the_full_window_back_first(toolkit):
    # The mini strip is far smaller than any dialog, and these now open inside the window.
    order = []
    toolkit.is_mini_mode = True
    toolkit.toggle_mini_mode = lambda _btn: order.append("leave mini")
    dialog = dialogs.message(toolkit, "Playback blocked", "Not available in your region.")
    assert order == ["leave mini"] and dialog.parent == "the window"
    toolkit.is_mini_mode = False
    dialogs.confirm(toolkit, "Delete?", "", "Delete", lambda: None, destructive=True)
    assert order == ["leave mini"]  # the full window is left alone


def _preset_app(names, selected=0):
    from gi.repository import Gtk

    saved, deleted, refreshed = [], [], []
    mgr = SimpleNamespace(
        list_presets=lambda: list(names),
        save_preset=lambda name, _settings: saved.append(name) or len(names) < 20,
        delete_preset=deleted.append,
    )
    dd = SimpleNamespace(
        get_selected_item=lambda: Gtk.StringObject.new(names[selected]) if names else None,
        set_selected=lambda _i: None,
    )
    app = SimpleNamespace(win="the window", dsp_preset_mgr=mgr, dsp_preset_dd=dd, settings={})
    return app, saved, deleted, refreshed


def test_dsp_preset_dialogs_go_through_the_helpers(monkeypatch):
    from actions import dsp_preset_actions

    shown = {}
    monkeypatch.setattr(dsp_preset_actions.dialogs, "confirm",
                        lambda app, heading, body, label, on_confirm, **kw: shown.update(confirm=(heading, body, label, on_confirm, kw)))
    monkeypatch.setattr(dsp_preset_actions.dialogs, "prompt_text",
                        lambda app, heading, body, initial, on_submit, **kw: shown.update(prompt=(heading, initial, on_submit)))
    monkeypatch.setattr(dsp_preset_actions.dialogs, "message", lambda app, heading, body: shown.update(message=(heading, body)))
    refreshed = []
    monkeypatch.setattr(dsp_preset_actions, "refresh_dsp_preset_list", lambda a: refreshed.append(a))

    app, saved, deleted, _ = _preset_app(["Warm", "Late night"], selected=1)
    dsp_preset_actions.on_dsp_preset_delete_clicked(app, None)
    heading, body, label, on_confirm, kw = shown["confirm"]
    assert heading == "Delete Preset?" and "“Late night”" in body and label == "Delete"
    assert kw == {"destructive": True}  # styled as destructive, and Enter cancels
    assert deleted == []
    on_confirm()
    assert deleted == ["Late night"] and refreshed == [app]

    dsp_preset_actions.on_dsp_preset_save_clicked(app, None)
    heading, initial, on_submit = shown["prompt"]
    assert heading == "Save DSP Preset" and initial.startswith("My Preset")
    on_submit("")  # a cleared entry keeps the suggested name
    on_submit("Bright")
    assert saved == [initial, "Bright"] and "message" not in shown

    full, saved_full, _, _ = _preset_app([f"P{i}" for i in range(20)])
    dsp_preset_actions.on_dsp_preset_save_clicked(full, None)
    shown["prompt"][2]("One more")
    assert shown["message"] == ("Cannot Save Preset", "Preset limit reached (max 20).")


def test_the_usb_access_question_has_a_heading_and_each_answer_does_its_job(toolkit, monkeypatch):
    from actions import audio_settings_actions as aud

    appearance = SimpleNamespace(DESTRUCTIVE="destructive", SUGGESTED="suggested")
    monkeypatch.setattr(aud, "Adw", SimpleNamespace(AlertDialog=_Alert, ResponseAppearance=appearance))
    did = []
    monkeypatch.setattr(aud, "on_usb_fix_permissions_clicked", lambda app, device_id=None: did.append(("grant", device_id)))
    monkeypatch.setattr(aud, "_show_usb_manual_setup_dialog", lambda app, device_id, intro=None: did.append(("manual", device_id)))
    dialog = aud._show_usb_permission_dialog(toolkit, "Test DAC", "1234:5678")
    assert dialog.heading == "USB Access Required" and "Test DAC" in dialog.body
    assert dialog.parent == "the window"  # in the window, not a title-bar-only toplevel
    assert [r for r, _ in dialog.responses] == ["cancel", "manual", "confirm"]
    assert dialog.default == "confirm" and dialog.close == "cancel"
    dialog.respond("cancel")
    assert did == []
    dialog.respond("manual")
    dialog.respond("confirm")
    assert did == [("manual", "1234:5678"), ("grant", "1234:5678")]
