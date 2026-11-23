import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import ui_actions


@pytest.fixture(autouse=True)
def _fake_card_grid(monkeypatch):
    # Fork #17: grid covers come from ui/card_grid.py, which builds real widgets; these tests
    # swap ui_actions.Gtk for fakes, so the covers become placeholders too.
    monkeypatch.setattr(
        ui_actions, "card_grid", SimpleNamespace(cover=lambda *_a, **_k: object(), fit_labels=lambda _card: None)
    )

    # Fork #27: so does ui/shelf.py (Shelf is a real Gtk.FlowBox): a fake shelf is the test's
    # own fake FlowBox, and a heading is a fake Box with no button.
    def _fake_shelf(button=None):
        flow = ui_actions.Gtk.FlowBox()
        for name in ("reset", "add_css_class"):
            if not hasattr(flow, name):
                setattr(flow, name, lambda *_a, **_k: None)
        if not hasattr(flow, "get_root"):
            flow.get_root = lambda: object()
        return flow

    monkeypatch.setattr(ui_actions, "shelf", SimpleNamespace(
        Shelf=_fake_shelf, MAX_PER_LINE=16, heading=lambda _title: (ui_actions.Gtk.Box(), None)))


def test_home_section_header_uses_context_kicker_as_small_line():
    result = ui_actions._home_section_header_lines(
        {
            "title": "Because you liked",
            "subtitle": "",
            "section_type": "HORIZONTAL_LIST_WITH_CONTEXT",
            "context_header": {"name": "初次嚐到寂寞"},
        }
    )

    assert result == {
        "title": "初次嚐到寂寞",
        "kicker": "Because you liked",
        "secondary": "",
    }


def test_home_section_header_keeps_full_context_sentence_as_secondary():
    result = ui_actions._home_section_header_lines(
        {"title": "Recommended Tracks", "subtitle": "Because you liked Hello", "section_type": "HORIZONTAL_LIST"}
    )

    assert result == {
        "title": "Recommended Tracks",
        "kicker": "",
        "secondary": "Because you liked Hello",
    }


def test_home_card_subtitle_text_preserves_blank_row_for_missing_subtitle():
    assert ui_actions._home_card_subtitle_text("Dominique Fils-Aime") == "Dominique Fils-Aime"
    assert ui_actions._home_card_subtitle_text("") == " "
    assert ui_actions._home_card_subtitle_text(None) == " "


def test_home_card_layout_uses_fixed_media_slot_plus_card_padding():
    album_layout = ui_actions._home_card_layout({"type": "Album", "name": "Deadline"}, 170)
    track_layout = ui_actions._home_card_layout({"type": "Track", "name": "Song"}, 170)
    radio_layout = ui_actions._home_card_layout({"type": "Playlist", "name": "Personal Radio"}, 170)

    assert album_layout["img_size"] == 170
    assert album_layout["card_width"] == 170
    assert album_layout["img_cls"] == "album-cover-img"
    assert "home-feed-card" in album_layout["card_classes"]
    assert album_layout["text_width_chars"] == 16

    assert track_layout["img_size"] == 88
    assert track_layout["card_width"] == 88
    assert "home-track-card" in track_layout["card_classes"]
    assert track_layout["text_width_chars"] == 10

    assert radio_layout["img_size"] == 150
    assert radio_layout["card_width"] == 150
    assert radio_layout["img_cls"] == "circular-avatar"
    assert radio_layout["text_width_chars"] == 14


def test_home_feed_layout_marks_cards_for_feed_specific_hover_styling():
    layout = ui_actions._home_card_layout({"type": "Album", "name": "Deadline"}, 170)

    assert "home-feed-card" in layout["card_classes"]


def test_feed_card_classes_keeps_common_and_extra_classes():
    classes = ui_actions._feed_card_classes("history-card")

    assert classes == ["card", "home-card", "home-feed-card", "history-card"]


def test_feed_tint_classes_keeps_base_and_shape_classes():
    classes = ui_actions._feed_tint_classes("album-cover-img", "playlist-folder-shape")

    assert classes == ["home-feed-tint", "album-cover-img", "playlist-folder-shape"]


def test_dashboard_track_row_button_classes_keep_flat_row_hover_and_playing_state():
    assert ui_actions._dashboard_track_row_button_classes(False) == [
        "flat",
        "history-card-btn",
        "dashboard-track-row-btn",
    ]
    assert ui_actions._dashboard_track_row_button_classes(True) == [
        "flat",
        "history-card-btn",
        "dashboard-track-row-btn",
        "track-row-playing",
    ]


def test_artist_card_classes_keep_media_only_hover_override():
    classes = ui_actions._artist_card_classes()

    assert classes == ["card", "home-card", "home-feed-card", "artist-feed-card"]


def test_render_history_dashboard_omits_section_titles_and_count_labels(monkeypatch):
    class _FakeWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.label = str(kwargs.get("label", ""))
            self.css_classes = list(kwargs.get("css_classes", []))
            self.hexpand = bool(kwargs.get("hexpand", False))
            self.visible_child_name = ""

        def append(self, child):
            self.children.append(child)

        def connect(self, *_args, **_kwargs):
            return None

        def set_hhomogeneous(self, *_args, **_kwargs):
            return None

        def set_vhomogeneous(self, *_args, **_kwargs):
            return None

        def set_halign(self, *_args, **_kwargs):
            return None

        def set_hexpand(self, value):
            self.hexpand = bool(value)

        def set_visible_child_name(self, value):
            self.visible_child_name = str(value)

        def get_visible_child_name(self):
            return self.visible_child_name

        def add_titled(self, child, *_args, **_kwargs):
            self.children.append(child)

        def attach(self, child, *_args, **_kwargs):
            self.children.append(child)

        def set_child(self, child):
            self.children.append(child)

    class _FakeFlowBoxChild:
        def __init__(self):
            self.child = None

        def set_child(self, child):
            self.child = child

    fake_gtk = SimpleNamespace(
        Box=_FakeWidget,
        Stack=_FakeWidget,
        StackSwitcher=_FakeWidget,
        Label=_FakeWidget,
        Grid=_FakeWidget,
        FlowBox=_FakeWidget,
        FlowBoxChild=_FakeFlowBoxChild,
        ScrolledWindow=_FakeWidget,  # fork: the tab strip scrolls (_scrolling_tabs)
        PolicyType=SimpleNamespace(AUTOMATIC="automatic", NEVER="never"),
        StackTransitionType=SimpleNamespace(CROSSFADE="crossfade"),
        Align=SimpleNamespace(START="start", CENTER="center", END="end", FILL="fill"),
        SelectionMode=SimpleNamespace(NONE="none"),
        Orientation=SimpleNamespace(VERTICAL="vertical", HORIZONTAL="horizontal"),
    )
    monkeypatch.setattr(ui_actions, "Gtk", fake_gtk)
    monkeypatch.setattr(ui_actions, "_clear_container", lambda container: container.children.clear())

    app = SimpleNamespace(
        collection_content_box=_FakeWidget(),
        history_mgr=SimpleNamespace(
            get_albums=lambda: [SimpleNamespace(name="Album One", artist=SimpleNamespace(name="Artist"))],
            get_top_tracks=lambda limit=20: [],
            get_recent_tracks=lambda limit=100: [],
        ),
    )

    ui_actions.render_history_dashboard(app)

    tabs_box = app.collection_content_box.children[0]
    history_stack = tabs_box.children[1]
    sections = history_stack.children  # Top 100, Recent Tracks, Recent Albums
    assert len(sections) == 3
    for section in sections:
        classes = {c for child in section.children for c in getattr(child, "css_classes", [])}
        assert not classes & {"home-section-title", "home-section-count"}
    # Fork: an empty tab says what will show up there (here, both track tabs).
    hints = [child.label for section in sections[:2] for child in section.children if "dim-label" in child.css_classes]
    assert hints == ["Your most played tracks show up here.", "Tracks you play show up here."]
    assert not [child for child in sections[2].children if "dim-label" in child.css_classes]


def test_render_history_dashboard_says_nothing_played_yet_instead_of_empty_tabs(monkeypatch):
    labels = []
    monkeypatch.setattr(ui_actions, "_clear_container", lambda _container: None)
    monkeypatch.setattr(ui_actions.Gtk, "Label", lambda **kw: labels.append(kw.get("label")) or kw)
    box = SimpleNamespace(appended=[], append=lambda w: box.appended.append(w))
    empty = SimpleNamespace(get_albums=lambda: [], get_top_tracks=lambda limit=20: [], get_recent_tracks=lambda limit=100: [])
    ui_actions.render_history_dashboard(SimpleNamespace(collection_content_box=box, history_mgr=empty))
    assert len(box.appended) == 1 and labels[0].startswith("Nothing played yet.")


def test_render_hires_dashboard_omits_redundant_hires_tab(monkeypatch):
    class _FakeWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.label = str(kwargs.get("label", ""))
            self.css_classes = list(kwargs.get("css_classes", []))
            self.hexpand = bool(kwargs.get("hexpand", False))
            self.visible_child_name = ""
            self.titled_children = []

        def set_child(self, child):
            self.append(child)

        def append(self, child):
            self.children.append(child)

        def remove(self, child):
            self.children.remove(child)

        def get_first_child(self):
            return self.children[0] if self.children else None

        def connect(self, *_args, **_kwargs):
            return None

        def set_hhomogeneous(self, *_args, **_kwargs):
            return None

        def set_vhomogeneous(self, *_args, **_kwargs):
            return None

        def set_halign(self, *_args, **_kwargs):
            return None

        def set_valign(self, *_args, **_kwargs):
            return None

        def set_hexpand(self, value):
            self.hexpand = bool(value)

        def set_vexpand(self, *_args, **_kwargs):
            return None

        def set_visible_child_name(self, value):
            self.visible_child_name = str(value)

        def get_visible_child_name(self):
            return self.visible_child_name

        def add_titled(self, child, name, title):
            self.titled_children.append({"child": child, "name": str(name), "title": str(title)})
            self.children.append(child)

        def attach(self, child, *_args, **_kwargs):
            self.children.append(child)

    class _FakeFlowBoxChild:
        def __init__(self):
            self.child = None

        def set_child(self, child):
            self.child = child

    fake_gtk = SimpleNamespace(
        Box=_FakeWidget,
        Stack=_FakeWidget,
        StackSwitcher=_FakeWidget,
        ScrolledWindow=_FakeWidget,
        PolicyType=SimpleNamespace(AUTOMATIC="automatic", NEVER="never"),
        Label=_FakeWidget,
        FlowBox=_FakeWidget,
        FlowBoxChild=_FakeFlowBoxChild,
        StackTransitionType=SimpleNamespace(CROSSFADE="crossfade"),
        Align=SimpleNamespace(START="start"),
        SelectionMode=SimpleNamespace(NONE="none"),
        Orientation=SimpleNamespace(VERTICAL="vertical"),
    )
    monkeypatch.setattr(ui_actions, "Gtk", fake_gtk)
    monkeypatch.setattr(ui_actions.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.setattr(
        ui_actions,
        "_build_feed_item_button",
        lambda *_args, **_kwargs: _FakeWidget(label="item"),
    )

    app = SimpleNamespace(
        collection_content_box=_FakeWidget(),
        _hires_sections_cache=[
            {"title": "Hi-Res", "items": [{"name": "Placeholder"}]},
            {"title": "Headphone Classics", "items": [{"name": "Album One"}]},
            {"title": "Classic Albums", "items": [{"name": "Album Two"}]},
        ],
        _hires_sections_cache_time=ui_actions.time.monotonic(),
        _hires_selected_tab="",
    )

    ui_actions.render_hires_dashboard(app)

    tabs_box = app.collection_content_box.children[0]
    hires_stack = tabs_box.children[1]

    assert [tab["title"] for tab in hires_stack.titled_children] == [
        "Headphone Classics",
        "Classic Albums",
    ]


def test_render_decades_dashboard_uses_decade_labels_for_tabs(monkeypatch):
    class _FakeWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.label = str(kwargs.get("label", ""))
            self.css_classes = list(kwargs.get("css_classes", []))
            self.hexpand = bool(kwargs.get("hexpand", False))
            self.visible_child_name = ""
            self.titled_children = []
            self._parent = None

        def set_child(self, child):
            self.append(child)

        def append(self, child):
            if hasattr(child, "_parent"):
                child._parent = self
            self.children.append(child)

        def remove(self, child):
            self.children.remove(child)
            if hasattr(child, "_parent"):
                child._parent = None

        def get_first_child(self):
            return self.children[0] if self.children else None

        def get_next_sibling(self):
            parent = getattr(self, "_parent", None)
            if parent is None:
                return None
            try:
                idx = parent.children.index(self)
            except ValueError:
                return None
            next_idx = idx + 1
            return parent.children[next_idx] if next_idx < len(parent.children) else None

        def connect(self, *_args, **_kwargs):
            return None

        def set_hhomogeneous(self, *_args, **_kwargs):
            return None

        def set_vhomogeneous(self, *_args, **_kwargs):
            return None

        def set_halign(self, *_args, **_kwargs):
            return None

        def set_valign(self, *_args, **_kwargs):
            return None

        def set_hexpand(self, value):
            self.hexpand = bool(value)

        def set_vexpand(self, *_args, **_kwargs):
            return None

        def set_margin_top(self, *_args, **_kwargs):
            return None

        def start(self):
            return None

        def set_visible_child_name(self, value):
            self.visible_child_name = str(value)

        def get_visible_child_name(self):
            return self.visible_child_name

        def add_titled(self, child, name, title):
            self.titled_children.append({"child": child, "name": str(name), "title": str(title)})
            self.append(child)

        def attach(self, child, *_args, **_kwargs):
            self.append(child)

    class _FakeFlowBoxChild:
        def __init__(self):
            self.child = None
            self._parent = None

        def set_child(self, child):
            self.child = child

        def get_next_sibling(self):
            return None

    fake_gtk = SimpleNamespace(
        Box=_FakeWidget,
        Stack=_FakeWidget,
        StackSwitcher=_FakeWidget,
        ScrolledWindow=_FakeWidget,
        PolicyType=SimpleNamespace(AUTOMATIC="automatic", NEVER="never"),
        Label=_FakeWidget,
        FlowBox=_FakeWidget,
        FlowBoxChild=_FakeFlowBoxChild,
        Spinner=_FakeWidget,
        StackTransitionType=SimpleNamespace(CROSSFADE="crossfade"),
        Align=SimpleNamespace(START="start", CENTER="center"),
        SelectionMode=SimpleNamespace(NONE="none"),
        Orientation=SimpleNamespace(VERTICAL="vertical"),
    )
    monkeypatch.setattr(ui_actions, "Gtk", fake_gtk)
    monkeypatch.setattr(ui_actions.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.setattr(
        ui_actions,
        "_build_feed_item_button",
        lambda *_args, **_kwargs: _FakeWidget(label="item"),
    )

    app = SimpleNamespace(
        collection_content_box=_FakeWidget(),
        _decades_definitions=[("1950s", "pages/m_1950s"), ("1960s", "pages/m_1960s")],
        _decades_tab_cache={
            "1950s": {
                "title": "1950s",
                "categories": [{"title": "Classics", "items": [{"name": "Album One"}]}],
            }
        },
        _decades_cache_time=ui_actions.time.monotonic(),
        _decades_selected_tab="",
    )

    ui_actions.render_decades_dashboard(app)

    tabs_box = app.collection_content_box.children[0]
    decades_stack = tabs_box.children[1]

    assert [tab["title"] for tab in decades_stack.titled_children] == ["1950s", "1960s"]
    assert "Decades" not in [tab["title"] for tab in decades_stack.titled_children]


def test_render_genres_dashboard_prefetches_the_next_tab_and_serves_it_from_cache(monkeypatch):
    class _RunThread:
        def __init__(self, target=None, daemon=None):
            self._target = target
            self.daemon = bool(daemon)

        def start(self):
            if self._target is not None:
                self._target()

    class _FakeAdjustment:
        def __init__(self, lower=0.0, upper=1000.0, page_size=240.0, value=0.0):
            self.lower = float(lower)
            self.upper = float(upper)
            self.page_size = float(page_size)
            self.value = float(value)

        def connect(self, *_args, **_kwargs):
            return None

        def get_lower(self):
            return self.lower

        def get_upper(self):
            return self.upper

        def get_page_size(self):
            return self.page_size

        def get_value(self):
            return self.value

        def set_value(self, value):
            self.value = float(value)

    class _FakeWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.label = str(kwargs.get("label", ""))
            self.css_classes = list(kwargs.get("css_classes", []))
            self.hexpand = bool(kwargs.get("hexpand", False))
            self.visible_child_name = ""
            self.titled_children = []
            self.handlers = {}
            self._parent = None
            self.visible = True
            self._width = int(kwargs.get("width", 0) or 0)
            self.sensitive = True
            self._hadjustment = _FakeAdjustment()

        def append(self, child):
            if hasattr(child, "_parent"):
                child._parent = self
            self.children.append(child)

        def remove(self, child):
            self.children.remove(child)
            if hasattr(child, "_parent"):
                child._parent = None

        def get_first_child(self):
            return self.children[0] if self.children else None

        def get_next_sibling(self):
            parent = getattr(self, "_parent", None)
            if parent is None:
                return None
            try:
                idx = parent.children.index(self)
            except ValueError:
                return None
            next_idx = idx + 1
            return parent.children[next_idx] if next_idx < len(parent.children) else None

        def connect(self, signal_name, callback):
            self.handlers[str(signal_name)] = callback
            return None

        def set_hhomogeneous(self, *_args, **_kwargs):
            return None

        def set_vhomogeneous(self, *_args, **_kwargs):
            return None

        def set_halign(self, *_args, **_kwargs):
            return None

        def set_valign(self, *_args, **_kwargs):
            return None

        def set_hexpand(self, value):
            self.hexpand = bool(value)

        def set_vexpand(self, *_args, **_kwargs):
            return None

        def set_visible(self, value):
            self.visible = bool(value)

        def set_sensitive(self, value):
            self.sensitive = bool(value)

        def set_tooltip_text(self, _value):
            return None

        def set_margin_top(self, *_args, **_kwargs):
            return None

        def set_policy(self, *_args, **_kwargs):
            return None

        def set_propagate_natural_height(self, *_args, **_kwargs):
            return None

        def get_width(self):
            return self._width

        def get_hadjustment(self):
            return self._hadjustment

        def set_child(self, child):
            self.append(child)

        def start(self):
            return None

        def set_visible_child_name(self, value):
            self.visible_child_name = str(value)

        def get_visible_child_name(self):
            return self.visible_child_name

        def add_titled(self, child, name, title):
            self.titled_children.append({"child": child, "name": str(name), "title": str(title)})
            self.append(child)

        def attach(self, child, *_args, **_kwargs):
            self.append(child)

    class _FakeFlowBoxChild:
        def __init__(self):
            self.child = None
            self._parent = None

        def set_child(self, child):
            self.child = child

    fake_gtk = SimpleNamespace(
        Box=_FakeWidget,
        Button=_FakeWidget,
        Stack=_FakeWidget,
        StackSwitcher=_FakeWidget,
        ScrolledWindow=_FakeWidget,
        Label=_FakeWidget,
        FlowBox=_FakeWidget,
        FlowBoxChild=_FakeFlowBoxChild,
        Spinner=_FakeWidget,
        StackTransitionType=SimpleNamespace(CROSSFADE="crossfade"),
        Align=SimpleNamespace(START="start", CENTER="center", END="end", FILL="fill"),
        SelectionMode=SimpleNamespace(NONE="none"),
        Orientation=SimpleNamespace(VERTICAL="vertical", HORIZONTAL="horizontal"),
        PolicyType=SimpleNamespace(AUTOMATIC="automatic", NEVER="never"),
    )
    monkeypatch.setattr(ui_actions, "Gtk", fake_gtk)
    monkeypatch.setattr(ui_actions, "Thread", _RunThread)
    monkeypatch.setattr(ui_actions.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.setattr(
        ui_actions,
        "_build_feed_item_button",
        lambda *_args, **_kwargs: _FakeWidget(label="item"),
    )

    fetch_calls = []

    def _fetch_genre(label, path):
        fetch_calls.append((label, path))
        return {
            "title": label,
            "categories": [{
                "title": f"{label} Picks",
                "items": [{"name": f"{label} Album {idx}"} for idx in range(1, 6)],
            }],
        }

    app = SimpleNamespace(
        collection_content_box=_FakeWidget(width=240),
        # get_genres_page: read when the page opens; the cache here is fresh, so not called.
        backend=SimpleNamespace(get_genre_section=_fetch_genre, get_genres_page=lambda: ([], [])),
        _genres_definitions=[("Blues", "pages/genre/blues"), ("Jazz", "pages/genre/jazz")],
        _genres_tab_cache={},
        _genres_cache_time=ui_actions.time.monotonic(),
        _genres_selected_tab="",
    )

    ui_actions.render_genres_dashboard(app)

    # Upstream pre-loads the next two tabs once a tab is shown.
    assert fetch_calls == [("Blues", "pages/genre/blues"), ("Jazz", "pages/genre/jazz")]

    tabs_box = app.collection_content_box.children[0]
    genres_tabs_row = tabs_box.children[0]
    genres_tabs_scroll = genres_tabs_row.children[1]
    genres_stack = tabs_box.children[1]
    blues_placeholder = genres_stack.children[0]
    blues_tab = blues_placeholder.children[0]
    blues_cat_box = blues_tab.children[1]
    blues_flow = blues_cat_box.children[0]

    assert genres_tabs_row.children[0].visible is True
    assert genres_tabs_row.children[2].visible is True
    assert genres_tabs_row.children[0].sensitive is False
    assert genres_tabs_row.children[2].sensitive is True

    genres_tabs_row.children[2].handlers["clicked"](genres_tabs_row.children[2])

    assert genres_tabs_scroll.get_hadjustment().get_value() > 0.0
    # Fork #27: a shelf builds a row's worth (up to 16) at once; "Show all" sits in the heading.
    assert len(blues_flow.children) == 5  # all five: under a row's worth (16), so built at once

    genres_stack.set_visible_child_name("Jazz")
    genres_stack.handlers["notify::visible-child-name"](genres_stack, None)

    assert fetch_calls == [  # Jazz comes from the pre-load, not a second fetch
        ("Blues", "pages/genre/blues"),
        ("Jazz", "pages/genre/jazz"),
    ]


def test_render_genres_dashboard_keeps_tracks_category_to_two_rows(monkeypatch):
    class _RunThread:
        def __init__(self, target=None, daemon=None):
            self._target = target
            self.daemon = bool(daemon)

        def start(self):
            if self._target is not None:
                self._target()

    class _FakeAdjustment:
        def __init__(self, lower=0.0, upper=1000.0, page_size=240.0, value=0.0):
            self.lower = float(lower)
            self.upper = float(upper)
            self.page_size = float(page_size)
            self.value = float(value)

        def connect(self, *_args, **_kwargs):
            return None

        def get_lower(self):
            return self.lower

        def get_upper(self):
            return self.upper

        def get_page_size(self):
            return self.page_size

        def get_value(self):
            return self.value

        def set_value(self, value):
            self.value = float(value)

    class _FakeWidget:
        def __init__(self, *args, **kwargs):
            self.children = []
            self.label = str(kwargs.get("label", ""))
            self.css_classes = list(kwargs.get("css_classes", []))
            self.hexpand = bool(kwargs.get("hexpand", False))
            self.visible_child_name = ""
            self.titled_children = []
            self.handlers = {}
            self._parent = None
            self.visible = True
            self._width = int(kwargs.get("width", 0) or 0)
            self.sensitive = True
            self._hadjustment = _FakeAdjustment()

        def append(self, child):
            if hasattr(child, "_parent"):
                child._parent = self
            self.children.append(child)

        def remove(self, child):
            self.children.remove(child)
            if hasattr(child, "_parent"):
                child._parent = None

        def get_first_child(self):
            return self.children[0] if self.children else None

        def get_next_sibling(self):
            parent = getattr(self, "_parent", None)
            if parent is None:
                return None
            try:
                idx = parent.children.index(self)
            except ValueError:
                return None
            next_idx = idx + 1
            return parent.children[next_idx] if next_idx < len(parent.children) else None

        def connect(self, signal_name, callback):
            self.handlers[str(signal_name)] = callback
            return None

        def set_hhomogeneous(self, *_args, **_kwargs):
            return None

        def set_vhomogeneous(self, *_args, **_kwargs):
            return None

        def set_halign(self, *_args, **_kwargs):
            return None

        def set_valign(self, *_args, **_kwargs):
            return None

        def set_hexpand(self, value):
            self.hexpand = bool(value)

        def set_vexpand(self, *_args, **_kwargs):
            return None

        def set_visible(self, value):
            self.visible = bool(value)

        def set_sensitive(self, value):
            self.sensitive = bool(value)

        def set_tooltip_text(self, _value):
            return None

        def set_margin_top(self, *_args, **_kwargs):
            return None

        def set_policy(self, *_args, **_kwargs):
            return None

        def set_propagate_natural_height(self, *_args, **_kwargs):
            return None

        def get_width(self):
            return self._width

        def get_hadjustment(self):
            return self._hadjustment

        def set_child(self, child):
            self.append(child)

        def start(self):
            return None

        def set_visible_child_name(self, value):
            self.visible_child_name = str(value)

        def get_visible_child_name(self):
            return self.visible_child_name

        def add_titled(self, child, name, title):
            self.titled_children.append({"child": child, "name": str(name), "title": str(title)})
            self.append(child)

        def attach(self, child, *_args, **_kwargs):
            self.append(child)

    class _FakeFlowBoxChild:
        def __init__(self):
            self.child = None
            self._parent = None

        def set_child(self, child):
            self.child = child

    fake_gtk = SimpleNamespace(
        Box=_FakeWidget,
        Button=_FakeWidget,
        Stack=_FakeWidget,
        StackSwitcher=_FakeWidget,
        ScrolledWindow=_FakeWidget,
        Label=_FakeWidget,
        FlowBox=_FakeWidget,
        FlowBoxChild=_FakeFlowBoxChild,
        Spinner=_FakeWidget,
        StackTransitionType=SimpleNamespace(CROSSFADE="crossfade"),
        Align=SimpleNamespace(START="start", CENTER="center", END="end", FILL="fill"),
        SelectionMode=SimpleNamespace(NONE="none"),
        Orientation=SimpleNamespace(VERTICAL="vertical", HORIZONTAL="horizontal"),
        PolicyType=SimpleNamespace(AUTOMATIC="automatic", NEVER="never"),
    )
    monkeypatch.setattr(ui_actions, "Gtk", fake_gtk)
    monkeypatch.setattr(ui_actions, "Thread", _RunThread)
    monkeypatch.setattr(ui_actions.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.setattr(
        ui_actions,
        "_build_feed_item_button",
        lambda *_args, **_kwargs: _FakeWidget(label="item"),
    )

    track_items = [
        {"type": "Track", "name": f"Track {idx}", "sub_title": f"Artist {idx}"}
        for idx in range(1, 31)
    ]

    app = SimpleNamespace(
        collection_content_box=_FakeWidget(width=1060),
        backend=SimpleNamespace(get_genres_page=lambda: ([], [])),  # read when the page opens
        _genres_definitions=[("Blues", "pages/genre/blues")],
        _genres_tab_cache={
            "Blues": {"title": "Blues", "categories": [{"title": "New Tracks", "items": track_items}]}
        },
        _genres_cache_time=ui_actions.time.monotonic(),
        _genres_selected_tab="",
    )

    ui_actions.render_genres_dashboard(app)

    tabs_box = app.collection_content_box.children[0]
    genres_stack = tabs_box.children[1]
    blues_placeholder = genres_stack.children[0]
    blues_tab = blues_placeholder.children[0]
    blues_cat_box = blues_tab.children[1]
    blues_flow = blues_cat_box.children[0]

    assert len(blues_flow.children) == 16
