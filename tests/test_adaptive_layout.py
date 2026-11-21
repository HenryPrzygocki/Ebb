"""Fork: window-width tiers, the floating sidebar, and the content-width track columns."""
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from gi.repository import GObject  # noqa: E402

from app import app_builders as ab  # noqa: E402
from ui import builders  # noqa: E402
from ui import track_table  # noqa: E402

Gdk = ab.Gdk


class _W:
    """Records the widget calls the layout code makes."""

    def __init__(self, visible=True):
        self.visible = visible
        self.size = None
        self.css = set()
        self.halign = None
        self.start_child = "unset"
        self.overlays = []

    def set_visible(self, value):
        self.visible = bool(value)

    def get_visible(self):
        return self.visible

    def set_size_request(self, w, h):
        self.size = (w, h)

    def add_css_class(self, name):
        self.css.add(name)

    def remove_css_class(self, name):
        self.css.discard(name)

    def set_halign(self, value):
        self.halign = value

    # Gtk.Paned
    def set_start_child(self, child):
        self.start_child = child

    def set_shrink_start_child(self, _value):
        pass

    # Gtk.Overlay
    def add_overlay(self, child):
        self.overlays.append(child)

    def remove_overlay(self, child):
        self.overlays.remove(child)


def _app(mini=False):
    sidebar = _W()
    return SimpleNamespace(
        is_mini_mode=mini,
        timeline_box=_W(),
        vol_box=_W(),
        tech_box=_W(),
        lbl_album=_W(),
        art_img=_W(),
        player_text_box=_W(),
        sidebar_box=sidebar,
        paned=_W(),
        body_overlay=_W(),
        sidebar_toggle_btn=_W(visible=False),
        _sidebar_backdrop=_W(visible=False),
    )


def _ranges():
    """(tier, low, high) for every breakpoint condition, plus the implicit full tier."""
    out = [("full", 1080, 10**6)]
    for tier, cond in builders._TIER_CONDITIONS:
        hi = re.search(r"max-width: (\d+)px", cond)
        lo = re.search(r"min-width: (\d+)px", cond)
        out.append((tier, int(lo.group(1)) if lo else 0, int(hi.group(1))))
    return sorted(out, key=lambda r: r[1])


def test_tier_conditions_cover_every_width_exactly_once():
    ranges = _ranges()
    assert ranges[0][1] == 0
    for (_t1, _lo1, hi1), (_t2, lo2, _hi2) in zip(ranges, ranges[1:]):
        assert lo2 == hi1 + 1
    assert {t for t, *_ in ranges} == set(builders._LAYOUT_TIERS)


def test_the_window_minimum_is_inside_the_smallest_tier():
    assert builders.MAIN_MIN_SIZE[0] <= _ranges()[0][2]


def test_narrow_tier_shrinks_the_bar_and_floats_the_sidebar():
    app = _app()
    builders.apply_layout_tier(app, "narrow")
    assert app._layout_tier == "narrow"
    assert app.timeline_box.size == (220, -1)
    assert not app.vol_box.visible and not app.tech_box.visible
    assert app.lbl_album.visible
    assert app._sidebar_collapsed is True
    assert app.paned.start_child is None
    assert app.body_overlay.overlays == [app._sidebar_backdrop, app.sidebar_box]
    assert "sidebar-floating" in app.sidebar_box.css
    assert not app.sidebar_box.visible  # collapsed means hidden until toggled
    assert app.sidebar_toggle_btn.visible


def test_widening_docks_the_sidebar_again(monkeypatch):
    idle = []
    monkeypatch.setattr(builders.GLib, "idle_add", lambda fn, *a: idle.append(fn))
    app = _app()
    app._restore_paned_position_after_layout = lambda: False
    builders.apply_layout_tier(app, "tiny")
    builders.apply_layout_tier(app, "full")
    assert app._sidebar_collapsed is False
    assert app.paned.start_child is app.sidebar_box
    assert app.body_overlay.overlays == []
    assert "sidebar-floating" not in app.sidebar_box.css
    assert app.sidebar_box.visible and app.sidebar_box.size == (-1, -1)
    assert not app.sidebar_toggle_btn.visible
    assert idle == [app._restore_paned_position_after_layout]
    assert app.timeline_box.size == (560, -1) and app.vol_box.visible


def test_mini_mode_keeps_its_bar_layout():
    app = _app(mini=True)
    builders.apply_layout_tier(app, "tiny")
    assert app.timeline_box.size is None and app.vol_box.visible
    assert app._layout_tier == "tiny"  # reapplied when mini mode exits


def test_unknown_tier_falls_back_to_full():
    app = _app()
    builders.apply_layout_tier(app, "bogus")
    assert app._layout_tier == "full"


def test_reconcile_maps_the_current_breakpoint_to_its_tier():
    app = _app()
    bps = {name: object() for name, _ in builders._TIER_CONDITIONS}
    current = {"bp": bps["medium"]}
    app._layout_breakpoints = bps
    app.win = SimpleNamespace(get_current_breakpoint=lambda: current["bp"])
    builders.reconcile_layout_tier(app)
    assert app._layout_tier == "medium"
    current["bp"] = None
    builders.reconcile_layout_tier(app)
    assert app._layout_tier == "full"
    app.timeline_box.size = None
    builders.reconcile_layout_tier(app)  # same tier: nothing reapplied
    assert app.timeline_box.size is None
    builders.reconcile_layout_tier(app, force=True)
    assert app.timeline_box.size == (560, -1)


def test_floating_sidebar_toggle_and_hide():
    app = _app()
    assert builders.toggle_sidebar_overlay(app) is False  # docked: nothing to toggle
    builders.apply_layout_tier(app, "narrow")
    assert builders.hide_sidebar_overlay(app) is False  # already hidden
    assert builders.toggle_sidebar_overlay(app) is True
    assert app.sidebar_box.visible and app._sidebar_backdrop.visible
    assert builders.hide_sidebar_overlay(app) is True
    assert not app.sidebar_box.visible and not app._sidebar_backdrop.visible
    builders.toggle_sidebar_overlay(app, True)
    builders.toggle_sidebar_overlay(app, True)  # explicit show stays shown
    assert app.sidebar_box.visible


def test_escape_closes_the_floating_sidebar_before_anything_else():
    calls = []
    app = SimpleNamespace(
        win=SimpleNamespace(get_focus=lambda: None),
        _hide_sidebar_overlay=lambda: calls.append("hide") or True,
        hide_now_playing_overlay=lambda: calls.append("now-playing"),
    )
    assert ab.on_key_pressed(app, None, Gdk.KEY_Escape, 0, 0) is True
    assert calls == ["hide"]


class _Cell(GObject.Object):
    visible = GObject.Property(type=bool, default=True)


def test_track_columns_drive_every_bound_cell():
    app = SimpleNamespace()
    artist, album, subtitle = _Cell(), _Cell(), _Cell()
    track_table.bind_track_column(app, artist, "artist-column")
    track_table.bind_track_column(app, album, "album-column")
    track_table.bind_track_column(app, subtitle, "artist-column", invert=True)
    assert artist.props.visible and album.props.visible and not subtitle.props.visible
    cols = track_table.track_columns(app)
    cols.props.artist_column = False
    assert not artist.props.visible and subtitle.props.visible and album.props.visible
    cols.props.album_column = False
    assert not album.props.visible
    assert track_table.track_columns(app) is cols  # one shared state per app


def test_cells_built_while_narrow_start_hidden():
    app = SimpleNamespace()
    track_table.track_columns(app).props.album_column = False
    late = _Cell()
    track_table.bind_track_column(app, late, "album-column")
    assert not late.props.visible
