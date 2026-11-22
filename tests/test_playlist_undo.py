"""Fork: removing a track from a playlist can be undone; the notice chip carries the Undo."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_diagnostics  # noqa: E402
from app import app_playlist  # noqa: E402
from models.playlist import PlaylistManager  # noqa: E402
from ui import track_table  # noqa: E402


class _Widget:
    def __init__(self, visible=True):
        self.visible = visible
        self.text = None
        self.label = None
        self.revealed = False

    def set_visible(self, value):
        self.visible = bool(value)

    def get_visible(self):
        return self.visible

    def set_text(self, value):
        self.text = value

    def set_label(self, value):
        self.label = value

    def set_reveal_child(self, value):
        self.revealed = bool(value)

    def get_child(self):
        return None

    def set_from_icon_name(self, _name):
        pass


class _Row(_Widget):
    def __init__(self, track_id):
        super().__init__()
        self.track_id = track_id
        self.track_number_label = _Widget()


class _List:
    def __init__(self, ids):
        self.rows = [_Row(i) for i in ids]

    def get_row_at_index(self, i):
        return self.rows[i] if i < len(self.rows) else None


class _Loop:
    """Stands in for GLib timeouts/idles and the worker pool: run things when told to."""

    def __init__(self, monkeypatch):
        self.timers = {}
        self.next_id = 1
        monkeypatch.setattr(app_playlist.GLib, "timeout_add", self.timeout_add)
        monkeypatch.setattr(app_playlist.GLib, "source_remove", self.source_remove)
        monkeypatch.setattr(app_playlist.GLib, "idle_add", lambda fn, *a: fn(*a))
        monkeypatch.setattr(app_playlist, "submit_daemon", lambda fn: fn())

    def timeout_add(self, _ms, fn, *args):
        sid = self.next_id
        self.next_id += 1
        self.timers[sid] = (fn, args)
        return sid

    def source_remove(self, sid):
        self.timers.pop(sid, None)

    def fire_all(self):
        for sid, (fn, args) in list(self.timers.items()):
            self.timers.pop(sid, None)
            fn(*args)


def _notice_app():
    app = SimpleNamespace(
        output_notice_revealer=_Widget(),
        output_notice_icon=_Widget(),
        output_notice_label=_Widget(),
        output_notice_action_btn=_Widget(visible=False),
        _output_notice_source=0,
    )
    app.show_output_notice = lambda text, state="idle", ms=2600: app_diagnostics.show_output_notice(app, text, state, ms)
    return app


def test_undo_notice_runs_its_action_once(monkeypatch):
    monkeypatch.setattr(app_diagnostics.GLib, "timeout_add", lambda _ms, _fn: 7)
    monkeypatch.setattr(app_diagnostics.GLib, "source_remove", lambda _sid: None)
    app = _notice_app()
    calls = []
    app_diagnostics.show_undo_notice(app, "Removed it", lambda: calls.append("undo"))
    assert app.output_notice_action_btn.visible and app.output_notice_action_btn.label == "Undo"
    app_diagnostics.on_output_notice_action(app)
    app_diagnostics.on_output_notice_action(app)
    assert calls == ["undo"]
    assert not app.output_notice_revealer.revealed


def test_a_plain_notice_drops_the_previous_undo(monkeypatch):
    monkeypatch.setattr(app_diagnostics.GLib, "timeout_add", lambda _ms, _fn: 7)
    monkeypatch.setattr(app_diagnostics.GLib, "source_remove", lambda _sid: None)
    app = _notice_app()
    calls = []
    app_diagnostics.show_undo_notice(app, "Removed it", lambda: calls.append("undo"))
    app_diagnostics.show_output_notice(app, "Output switched", "ok", 2000)
    assert not app.output_notice_action_btn.visible
    app_diagnostics.on_output_notice_action(app)
    assert calls == []


def test_an_expired_undo_does_nothing(monkeypatch):
    hide = {}
    monkeypatch.setattr(app_diagnostics.GLib, "timeout_add", lambda _ms, fn: hide.setdefault("fn", fn) and 7)
    app = _notice_app()
    calls = []
    app_diagnostics.show_undo_notice(app, "Removed it", lambda: calls.append("undo"))
    hide["fn"]()
    app_diagnostics.on_output_notice_action(app)
    assert calls == []


def _remote_app(ids, result=True):
    pl = SimpleNamespace(id="pl-1", num_tracks=len(ids))
    sent, dropped, notices, undo = [], [], [], {}
    app = SimpleNamespace(
        current_remote_playlist=pl,
        track_list=_List(ids),
        backend=SimpleNamespace(
            remove_tracks_from_cloud_playlist=lambda p, tracks: sent.append([t.id for t in tracks]) or {"ok": result}
        ),
        show_output_notice=lambda text, state="idle", ms=0: notices.append((state, text)),
        show_undo_notice=lambda text, on_undo, ms=0: undo.update(text=text, fn=on_undo),
        _remote_pl_view={"pl": pl, "drop": dropped.append},
    )
    return app, pl, sent, dropped, notices, undo


def _track(tid, name="Song"):
    return SimpleNamespace(id=tid, name=name)


def _visible(app):
    return [r.track_id for r in app.track_list.rows if r.visible]


def test_remove_hides_now_and_sends_nothing_until_the_undo_window_ends(monkeypatch):
    loop = _Loop(monkeypatch)
    app, pl, sent, dropped, _notices, undo = _remote_app([1, 2, 3])
    app_playlist.on_remove_single_track_from_remote_playlist(app, _track(2, "Creep"))
    assert _visible(app) == [1, 3] and sent == []
    assert [r.track_number_label.text for r in app.track_list.rows if r.visible] == ["1", "2"]
    assert undo["text"] == "Removed “Creep”"
    loop.fire_all()
    assert sent == [[2]] and dropped == [2] and pl.num_tracks == 2


def test_undo_restores_the_row_and_never_contacts_the_server(monkeypatch):
    loop = _Loop(monkeypatch)
    app, _pl, sent, _dropped, _notices, undo = _remote_app([1, 2, 3])
    app_playlist.on_remove_single_track_from_remote_playlist(app, _track(2))
    undo["fn"]()
    loop.fire_all()
    assert _visible(app) == [1, 2, 3] and sent == []
    assert [r.track_number_label.text for r in app.track_list.rows] == ["1", "2", "3"]


def test_a_second_removal_sends_the_first_at_once(monkeypatch):
    loop = _Loop(monkeypatch)
    app, _pl, sent, _dropped, _notices, undo = _remote_app([1, 2, 3])
    app_playlist.on_remove_single_track_from_remote_playlist(app, _track(1))
    first_undo = undo["fn"]
    app_playlist.on_remove_single_track_from_remote_playlist(app, _track(3))
    assert sent == [[1]]
    first_undo()  # too late: already sent
    assert _visible(app) == [2]
    loop.fire_all()
    assert sent == [[1], [3]]


def test_a_failed_removal_brings_the_row_back(monkeypatch):
    loop = _Loop(monkeypatch)
    app, pl, sent, dropped, notices, _undo = _remote_app([1, 2], result=False)
    app_playlist.on_remove_single_track_from_remote_playlist(app, _track(2, "Creep"))
    loop.fire_all()
    assert sent == [[2]] and dropped == [] and pl.num_tracks == 2
    assert _visible(app) == [1, 2]
    assert notices[-1][0] == "warn" and "Creep" in notices[-1][1]


def test_quitting_sends_a_pending_removal_synchronously(monkeypatch):
    _Loop(monkeypatch)
    app, _pl, sent, _dropped, _notices, _undo = _remote_app([1, 2])
    app_playlist.on_remove_single_track_from_remote_playlist(app, _track(2))
    assert sent == []
    monkeypatch.setattr(app_playlist, "submit_daemon", lambda _fn: pytest.fail("must not use the worker at shutdown"))
    app_playlist._flush_pending_playlist_removal(app, wait=True)
    assert sent == [[2]]
    assert getattr(app, "_pending_playlist_removal", None) is None


def test_local_playlist_removal_can_be_undone(tmp_path):
    mgr = PlaylistManager(base_dir=str(tmp_path))
    pid = mgr.create_playlist("Mine")["id"]
    for i, title in enumerate(["A", "B", "C"]):
        mgr.insert_track_entry(pid, i, {"id": i, "title": title})
    undo, renders = {}, []
    app = SimpleNamespace(
        playlist_mgr=mgr,
        current_playlist_id=pid,
        render_playlist_detail=renders.append,
        show_undo_notice=lambda text, on_undo, ms=0: undo.update(text=text, fn=on_undo),
    )
    app_playlist.on_playlist_remove_track_clicked(app, pid, 1)
    assert [t["title"] for t in mgr.get_playlist(pid)["tracks"]] == ["A", "C"]
    assert undo["text"] == "Removed “B”"
    undo["fn"]()
    assert [t["title"] for t in mgr.get_playlist(pid)["tracks"]] == ["A", "B", "C"]
    assert renders == [pid, pid]


def test_hidden_rows_keep_their_index_and_the_rest_renumber():
    lst = _List([10, 20, 10, 30])
    track_table.set_track_rows_hidden(lst, 10, True)
    assert [r.visible for r in lst.rows] == [False, True, False, True]
    assert [r.track_number_label.text for r in lst.rows if r.visible] == ["1", "2"]
    track_table.set_track_rows_hidden(lst, 10, False)
    assert [r.track_number_label.text for r in lst.rows] == ["1", "2", "3", "4"]
