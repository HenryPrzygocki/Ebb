"""Fork #7: right-click menus for TIDAL items (ui/context_menu.py + the window gesture)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui import builders, context_menu


# Stand-ins for tidalapi classes: classification goes by class name.
class Track(SimpleNamespace):
    pass


class Album(SimpleNamespace):
    pass


class Playlist(SimpleNamespace):
    pass


class MixV2(SimpleNamespace):
    pass


class PageItem(SimpleNamespace):
    pass


class _Widget:
    def __init__(self, parent=None):
        self._parent = parent

    def get_parent(self):
        return self._parent


class _Surface:
    def __init__(self, hit):
        self.hit = hit

    def pick(self, _x, _y, _flags):
        return self.hit


class _Gesture:
    def __init__(self, widget):
        self.widget = widget
        self.state = None

    def get_widget(self):
        return self.widget

    def set_state(self, value):
        self.state = value


class _SyncThread:
    def __init__(self, target=None, daemon=None, name=None):
        self._target = target

    def start(self):
        self._target()


def _track(tid=77):
    band = SimpleNamespace(id=9, name="Band")
    return Track(id=tid, name="Song", artist=band, album=Album(id=5, name="Record", artist=band))


def _app(**extra):
    calls = []

    def rec(name):
        return lambda *a, **k: calls.append((name, a, k))

    app = SimpleNamespace(
        calls=calls,
        notices=[],
        header=_Widget(),
        backend=SimpleNamespace(user=object(), is_track_favorite=lambda _tid: False),
        on_play_next_track_clicked=rec("play_next"),
        on_add_track_to_queue_clicked=rec("queue"),
        on_add_single_track_to_playlist=rec("add_to_playlist"),
        on_go_to_track_radio_clicked=rec("radio"),
        go_to_album_of=rec("go_album"),
        go_to_artist_of=rec("go_artist"),
        set_track_favorite=rec("fav"),
        play_tracks_now=rec("play_now"),
        play_tracks_next=rec("play_tracks_next"),
        add_tracks_to_queue=rec("add_tracks"),
    )
    app.show_output_notice = lambda text, level, _ms: app.notices.append((text, level))
    for key, value in extra.items():
        setattr(app, key, value)
    return app


def _labels(rows):
    return [row[0] if row else "—" for row in rows]


def _run(rows, label):
    dict(row for row in rows if row)[label]()


# ---------------------------------------------------------------- links and items

@pytest.mark.parametrize("kind,obj,url", [
    ("track", Track(id=123), "https://tidal.com/browse/track/123"),
    ("album", Album(id=5), "https://tidal.com/browse/album/5"),
    ("artist", SimpleNamespace(id=9), "https://tidal.com/browse/artist/9"),
    ("playlist", Playlist(id="0f3c-uuid"), "https://tidal.com/browse/playlist/0f3c-uuid"),
    ("mix", MixV2(id="001abc"), "https://tidal.com/browse/mix/001abc"),
    ("video", SimpleNamespace(id=42), "https://tidal.com/browse/video/42"),
])
def test_tidal_url_builds_public_browse_links(kind, obj, url):
    assert context_menu.tidal_url(kind, obj) == url


def test_tidal_url_refuses_unknown_kind_or_missing_id():
    assert context_menu.tidal_url("folder", SimpleNamespace(id=1)) is None
    assert context_menu.tidal_url("track", SimpleNamespace(id=None)) is None
    assert context_menu.tidal_url("track", None) is None


def test_kind_of_prefers_class_name_then_hint():
    assert context_menu.kind_of(Track(id=1)) == "track"
    assert context_menu.kind_of(MixV2(id="x"), "Album") == "mix"
    assert context_menu.kind_of(SimpleNamespace(id=1), "Album") == "album"
    assert context_menu.kind_of(SimpleNamespace(id=1)) is None
    assert context_menu.kind_of(PageItem(), "PageItem") is None


def test_resolve_walks_up_to_the_nearest_tagged_ancestor():
    t = _track()
    row = context_menu.tag(_Widget(), t, "track")
    assert context_menu.resolve(_Widget(parent=_Widget(parent=row))) == ("track", t)
    assert context_menu.resolve(_Widget(parent=_Widget())) is None


def test_resolve_reads_grid_children_data_item():
    alb = Album(id=5)
    child = _Widget()
    child.data_item = {"obj": alb, "type": "Album"}
    assert context_menu.resolve(_Widget(parent=child)) == ("album", alb)


def test_lazy_tag_follows_playback_and_an_empty_one_blocks_outer_tags():
    state = {"track": None}
    outer = context_menu.tag(_Widget(), Album(id=1), "album")
    bar = context_menu.tag(_Widget(parent=outer), lambda: state["track"], "track")
    hit = _Widget(parent=bar)
    assert context_menu.resolve(hit) is None
    state["track"] = _track(5)
    assert context_menu.resolve(hit) == ("track", state["track"])


def test_items_without_an_id_get_no_menu():
    promo = context_menu.tag(_Widget(), PageItem(header="Promo"), "Album")
    assert context_menu.resolve(promo) is None


def test_resolve_unwraps_lazily_resolved_queue_entries():
    real = _track(8)
    entry = SimpleNamespace(resolved_track=real)
    assert context_menu.resolve(context_menu.tag(_Widget(), entry, "track")) == ("track", real)


# ---------------------------------------------------------------- menus

def test_track_menu_has_queue_navigation_favorite_and_link():
    app = _app()
    t = _track()
    rows = context_menu.actions_for(app, "track", t)
    assert _labels(rows) == [
        "Play Next", "Add to Queue", "Add to Playlist…", "Add to Favorites", "—",
        "Go to Album", "Go to Artist", "Go to Track Radio", "—", "Copy TIDAL Link",
    ]
    _run(rows, "Play Next")
    _run(rows, "Go to Album")
    _run(rows, "Add to Favorites")
    assert app.calls[0] == ("play_next", (t,), {})
    assert app.calls[1] == ("go_album", (t,), {})
    name, args, kwargs = app.calls[2]
    assert (name, args) == ("fav", (t, True))
    kwargs["on_done"](True)
    assert app.notices[-1] == ("Added to Favorites", "ok")


def test_track_menu_favorite_entry_follows_state_and_login():
    app = _app()
    app.backend.is_track_favorite = lambda tid: tid == "77"
    assert "Remove from Favorites" in _labels(context_menu.actions_for(app, "track", _track(77)))
    app.backend.user = None
    labels = _labels(context_menu.actions_for(app, "track", _track(77)))
    assert not any("Favorites" in label for label in labels)
    assert labels.count("—") == 2


def test_copy_link_puts_the_tidal_url_on_the_clipboard(monkeypatch):
    app = _app()
    copied = []
    monkeypatch.setattr(context_menu, "copy_text", lambda _app, text: copied.append(text) is None)
    _run(context_menu.actions_for(app, "track", _track(123)), "Copy TIDAL Link")
    assert copied == ["https://tidal.com/browse/track/123"]
    assert app.notices[-1] == ("TIDAL link copied", "ok")


def test_album_menu_fetches_tracks_off_thread_then_queues_or_plays(monkeypatch):
    app = _app()
    tracks = [_track(1), _track(2)]
    app.backend.get_tracks = lambda _obj: tracks
    monkeypatch.setattr(context_menu, "Thread", _SyncThread)
    monkeypatch.setattr(context_menu.GLib, "idle_add", lambda fn, *a: fn(*a))
    alb = Album(id=5, name="Record", artist=SimpleNamespace(id=9, name="Band"))
    rows = context_menu.actions_for(app, "album", alb)
    assert _labels(rows) == [
        "Play", "Shuffle", "Play Next", "Add to Queue", "—", "Go to Artist", "—", "Copy TIDAL Link",
    ]
    _run(rows, "Add to Queue")
    _run(rows, "Shuffle")
    assert app.calls[0] == ("add_tracks", (tracks,), {})
    name, args, kwargs = app.calls[1]
    assert (name, args, kwargs["shuffle"]) == ("play_now", (tracks,), True)
    assert kwargs["source"] == {"type": "album", "name": "Record", "obj": alb}


def test_collection_without_tracks_warns_instead_of_acting(monkeypatch):
    app = _app()
    app.backend.get_tracks = lambda _obj: []
    monkeypatch.setattr(context_menu, "Thread", _SyncThread)
    monkeypatch.setattr(context_menu.GLib, "idle_add", lambda fn, *a: fn(*a))
    _run(context_menu.actions_for(app, "playlist", Playlist(id="u", name="P")), "Play Next")
    assert app.calls == []
    assert app.notices[-1] == ("No playable tracks found", "warn")


def test_artist_menu_is_the_link():
    assert _labels(context_menu.actions_for(_app(), "artist", SimpleNamespace(id=9))) == ["Copy TIDAL Link"]


# ---------------------------------------------------------------- the window gesture

def test_secondary_click_on_an_item_claims_and_opens_its_menu(monkeypatch):
    hit = _Widget(parent=context_menu.tag(_Widget(), _track(), "track"))
    surface = _Surface(hit)
    gesture = _Gesture(surface)
    shown = []
    monkeypatch.setattr(builders, "_clear_search_focus", lambda _app: None)
    monkeypatch.setattr(context_menu, "popup",
                        lambda _app, parent, x, y, rows, on_closed=None: shown.append((parent, x, y, _labels(rows))))
    builders._on_global_context_menu_pressed(_app(), gesture, 12, 34)
    assert gesture.state == builders.Gtk.EventSequenceState.CLAIMED
    assert shown[0][:3] == (surface, 12, 34)
    assert "Copy TIDAL Link" in shown[0][3]


def test_secondary_click_on_empty_space_is_left_to_gtk(monkeypatch):
    gesture = _Gesture(_Surface(_Widget(parent=_Widget())))
    shown = []
    monkeypatch.setattr(context_menu, "popup", lambda *a, **k: shown.append(a))
    builders._on_global_context_menu_pressed(_app(), gesture, 1, 1)
    assert gesture.state is None
    assert shown == []


def test_secondary_click_in_the_header_is_left_to_gtk(monkeypatch):
    app = _app()
    gesture = _Gesture(_Surface(context_menu.tag(_Widget(parent=app.header), _track(), "track")))
    shown = []
    monkeypatch.setattr(context_menu, "popup", lambda *a, **k: shown.append(a))
    builders._on_global_context_menu_pressed(app, gesture, 1, 1)
    assert gesture.state is None
    assert shown == []
