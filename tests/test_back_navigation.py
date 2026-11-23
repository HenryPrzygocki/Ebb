"""Fork: Back returns to the page you came from, scrolled to where you were."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import ui_actions, ui_navigation  # noqa: E402


class _Signals:
    def __init__(self):
        self.handlers, self._next = {}, 0

    def connect(self, signal, fn):
        self._next += 1
        self.handlers[self._next] = (signal, fn)
        return self._next

    def disconnect(self, handler_id):
        del self.handlers[handler_id]

    def emit(self, signal, *args):
        for sig, fn in list(self.handlers.values()):
            if sig == signal:
                fn(self, *args)

    def connected(self, signal):
        return [fn for sig, fn in self.handlers.values() if sig == signal]


class _Adj(_Signals):
    def __init__(self, upper=5243.0, page=678.0):
        super().__init__()
        self.value, self.upper, self.page = 0.0, upper, page

    def get_value(self):
        return self.value

    def get_upper(self):
        return self.upper

    def get_page_size(self):
        return self.page

    def set_value(self, value):
        self.value = max(0.0, min(float(value), max(0.0, self.upper - self.page)))
        self.emit("value-changed")

    def resize(self, upper):
        """New content height, clamping the position like GTK does."""
        self.upper = upper
        self.set_value(self.value)
        self.emit("notify::upper", None)


class _Stack:
    def __init__(self):
        self.name = "grid_view"

    def get_visible_child_name(self):
        return self.name

    def set_visible_child_name(self, name):
        self.name = name


class _Label:
    def __init__(self, text):
        self.text = text

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text


class _Controller(_Signals):
    def __init__(self, **_kw):
        super().__init__()

    def set_propagation_phase(self, _phase):
        pass


@pytest.fixture
def loop(monkeypatch):
    """GLib and Gtk stand-ins: idle callbacks run when asked, timeouts are kept for inspection."""
    fake = SimpleNamespace(idle=[], timeouts=[])
    fake.idle_add = lambda fn, *a: fake.idle.append((fn, a)) or 1
    fake.timeout_add = lambda ms, fn, *a: fake.timeouts.append((ms, fn, a)) or 2

    def run_idle():
        while fake.idle:
            fn, a = fake.idle.pop(0)
            fn(*a)

    fake.run_idle = run_idle
    gtk = SimpleNamespace(
        EventControllerScroll=_Controller,
        EventControllerScrollFlags=SimpleNamespace(VERTICAL=1),
        PropagationPhase=SimpleNamespace(CAPTURE=1),
    )
    monkeypatch.setattr(ui_navigation, "GLib", fake)
    monkeypatch.setattr(ui_navigation, "Gtk", gtk)
    return fake


def _app():
    adj, nav = _Adj(), SimpleNamespace(row=SimpleNamespace(nav_id="home"))
    nav.get_selected_row = lambda: nav.row
    controllers = []
    app = SimpleNamespace(
        adj=adj,
        nav_list=nav,
        right_stack=_Stack(),
        grid_title_label=_Label("Home"),
        alb_scroll=SimpleNamespace(get_vadjustment=lambda: adj, add_controller=controllers.append),
        controllers=controllers,
    )
    ui_navigation.install_scroll_memory(app)
    return app


def _rerender(app, nav_id, title, upper):
    """What Back does to a top-level page: title first, then the content is rebuilt from the top."""
    app.right_stack.set_visible_child_name("grid_view")
    app.nav_list.row = SimpleNamespace(nav_id=nav_id)
    app.grid_title_label.set_text(title)
    app.adj.resize(upper)
    app.adj.set_value(0)


def _back(app, fn):
    return ui_navigation._restores_grid_scroll(fn)(app, None)


def test_back_from_an_album_puts_home_where_it_was_once_its_content_reloads(loop):
    app = _app()
    app.adj.set_value(1400)
    app.right_stack.set_visible_child_name("tracks")  # open an album
    _back(app, lambda a, _b: _rerender(a, "home", "Home", 678.0))
    loop.run_idle()
    assert app.adj.value == 0  # nothing to scroll to yet
    app.adj.resize(5243.0)
    assert app.adj.value == 1400
    assert not app.adj.connected("notify::upper")  # done following the content


def test_back_from_an_artist_page_restores_home_too(loop):
    app = _app()
    app.adj.set_value(900)
    app.grid_title_label.set_text("Simon & Garfunkel")  # an artist page reuses the grid
    app.adj.set_value(300)
    _back(app, lambda a, _b: _rerender(a, "home", "Home", 5243.0))
    loop.run_idle()
    assert app.adj.value == 900


def test_each_page_keeps_its_own_position(loop):
    app = _app()
    app.adj.set_value(1400)
    app.right_stack.set_visible_child_name("tracks")  # Home -> album
    app.right_stack.set_visible_child_name("grid_view")
    app.grid_title_label.set_text("Simon & Garfunkel")  # album -> artist page
    app.adj.set_value(250)
    app.right_stack.set_visible_child_name("tracks")  # artist page -> another album
    _back(app, lambda a, _b: a.right_stack.set_visible_child_name("grid_view"))  # to the artist page
    loop.run_idle()
    assert app.adj.value == 250
    app.right_stack.set_visible_child_name("tracks")
    _back(app, lambda a, _b: _rerender(a, "home", "Home", 5243.0))  # and back to Home
    loop.run_idle()
    assert app.adj.value == 1400


def test_back_never_scrolls_a_different_page(loop):
    app = _app()
    app.adj.set_value(1400)
    app.right_stack.set_visible_child_name("tracks")
    _back(app, lambda a, _b: _rerender(a, "mixes", "Mixes & Radio", 5243.0))
    loop.run_idle()
    assert app.adj.value == 0


def test_scrolling_yourself_or_leaving_stops_the_restore(loop):
    app = _app()
    app.adj.set_value(1400)
    app.right_stack.set_visible_child_name("tracks")
    _back(app, lambda a, _b: _rerender(a, "home", "Home", 678.0))
    loop.run_idle()
    wheel = app.controllers[0]
    wheel.emit("scroll", 0.0, -1.0)  # the content is still loading and you scroll up
    app.adj.resize(5243.0)
    assert app.adj.value == 0

    app.adj.set_value(800)
    app.right_stack.set_visible_child_name("tracks")
    _back(app, lambda a, _b: _rerender(a, "home", "Home", 678.0))
    loop.run_idle()
    app.right_stack.set_visible_child_name("search_view")  # you search before Home finishes
    app.adj.resize(5243.0)
    assert app.adj.value == 0
    assert not app.adj.connected("notify::upper")


def test_back_to_search_results_leaves_the_grid_alone(loop):
    app = _app()
    app.adj.set_value(700)
    app.right_stack.set_visible_child_name("tracks")
    _back(app, lambda a, _b: a.right_stack.set_visible_child_name("search_view"))
    loop.run_idle()
    assert not app.adj.connected("notify::upper")
    assert loop.timeouts == []


class Mix:
    """Named like tidalapi's Mix: show_album_details treats any *Mix* type as a mix."""

    def __init__(self):
        self.id, self.name, self.title, self.artist = "mix-1", "My Mix 1", "My Mix 1", None


def test_opening_a_mix_leaves_the_sidebar_on_the_page_it_was_opened_from(monkeypatch):
    selected = []

    class _Thread:
        def __init__(self, target=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

    btn = SimpleNamespace(set_sensitive=lambda *_a: None, set_visible=lambda *_a: None)
    label = SimpleNamespace(set_text=lambda *_a: None, set_tooltip_text=lambda *_a: None,
                            set_visible=lambda *_a: None, remove_css_class=lambda *_a: None)
    app = SimpleNamespace(
        right_stack=_Stack(), nav_history=[], current_album=None, back_btn=btn,
        header_title=label, header_artist=label, header_meta=label, header_kicker=label, header_art=object(),
        backend=SimpleNamespace(is_favorite=lambda _i: False, is_mix_favorite=lambda _i: False,
                                get_tracks=lambda _a: []),
        cache_dir="/tmp", fav_btn=None, add_playlist_btn=None, remote_playlist_edit_btn=None,
        remote_playlist_visibility_btn=None, remote_playlist_more_btn=None,
        track_list=SimpleNamespace(get_first_child=lambda: None, get_row_at_index=lambda _i: None),
        album_sort_field=None, album_sort_asc=True, album_track_source=[], playing_track=None,
        _update_fav_icon=lambda *_a: None, load_album_tracks=lambda _t: None,
        _select_sidebar_nav_row=selected.append,
    )
    monkeypatch.setattr(ui_actions, "_ensure_play_shuffle_btns", lambda _app: None)
    monkeypatch.setattr(ui_actions.utils, "load_img", lambda *_a, **_k: None)
    monkeypatch.setattr(ui_actions, "Thread", _Thread)

    ui_actions.show_album_details(app, Mix())

    assert selected == []
    assert app.nav_history == ["grid_view"]  # so Back re-renders the page it came from
