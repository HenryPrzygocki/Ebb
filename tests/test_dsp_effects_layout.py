"""Fork: DSP Effects & Config follows the window's width, and the Presets row fits a long name.

The page put the module list in one column of three (the list needs 250 px) and the module's card
in the other two (the PEQ card needs 630). In three of Henry's six niri tiles one or both were cut:
the list's switches, or the PEQ's right bands with its preset menu and Reset."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_builders  # noqa: E402

# Henry's tiles: niri column presets 0.3-0.7 and full width of a 1920 px output.
TILES = {571: (True, True), 763: (True, True), 954: (False, True), 1145: (False, False), 1337: (False, False), 1912: (False, False)}


@pytest.mark.parametrize("tile", sorted(TILES))
def test_each_tile_gets_its_layout_with_room_either_side(tile):
    # The sandbox's window reports 10 px less than asked for: no threshold sits that close to a tile.
    for width in (tile - 10, tile, tile + 10):
        assert app_builders._dsp_effects_layout(width) == TILES[tile], width


def test_an_unrealized_window_is_not_an_error():
    assert app_builders._dsp_effects_layout(0) == (True, True)
    assert app_builders._dsp_effects_layout(None) == (True, True)


class _Row:
    def __init__(self, module_id, next_row=None):
        self.dsp_module_id, self.next_row, self.activatable, self.focused = module_id, next_row, None, False

    def get_next_sibling(self):
        return self.next_row

    def set_activatable(self, on):
        self.activatable = on

    def grab_focus(self):
        self.focused = True


class _Widget:
    def __init__(self):
        self.visible, self.focused, self.spacing, self.value_pos = True, False, None, None

    def set_visible(self, on):
        self.visible = on

    def grab_focus(self):
        self.focused = True

    def set_spacing(self, spacing):
        self.spacing = spacing

    def set_value_pos(self, position):
        self.value_pos = position


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(
        app_builders, "Gtk", SimpleNamespace(ListBoxRow=_Row, PositionType=SimpleNamespace(TOP="top", RIGHT="right"))
    )
    monkeypatch.setattr(app_builders.GLib, "idle_add", lambda fn, *a: fn(*a))
    tube = _Row("tube")
    peq = _Row("peq", tube)
    width = {"now": 1912}
    fake = SimpleNamespace(
        win=SimpleNamespace(get_width=lambda: width["now"]),
        width=width,
        rows=(peq, tube),
        dsp_effects_grid=object(),
        dsp_effects_list_pane=_Widget(),
        dsp_effects_detail_pane=_Widget(),
        dsp_effects_back_btn=_Widget(),
        dsp_module_list=SimpleNamespace(get_first_child=lambda: peq, get_selected_row=lambda: peq),
        dsp_peq_sliders=[_Widget(), _Widget()],
        dsp_peq_sliders_row=_Widget(),
    )
    for name in ("_apply_dsp_effects_layout", "_dsp_effects_show_detail", "_dsp_effects_show_list"):
        fn = getattr(app_builders, name)
        setattr(fake, name, lambda *a, _fn=fn, **k: _fn(fake, *a, **k))
    return fake


def _shown(app):
    return (app.dsp_effects_list_pane.visible, app.dsp_effects_detail_pane.visible, app.dsp_effects_back_btn.visible)


def test_wide_shows_both_and_the_full_peq(app):
    app._apply_dsp_effects_layout()
    assert _shown(app) == (True, True, False)
    assert [row.activatable for row in app.rows] == [False, False]  # upstream's rows: no click navigation
    assert [s.value_pos for s in app.dsp_peq_sliders] == ["right", "right"]
    assert app.dsp_peq_sliders_row.spacing == 8


def test_narrow_shows_the_list_then_the_module_a_click_opens(app):
    app.width["now"] = 571
    app._apply_dsp_effects_layout()
    assert _shown(app) == (True, False, False)
    assert [row.activatable for row in app.rows] == [True, True]
    assert [s.value_pos for s in app.dsp_peq_sliders] == ["top", "top"] and app.dsp_peq_sliders_row.spacing == 2

    # PEQ is selected from the start, so it is a click on the row already selected: no row-selected.
    app_builders._on_dsp_module_activated(app, None, app.rows[0])
    assert _shown(app) == (False, True, True)
    assert app.dsp_effects_back_btn.focused  # its row went away under the click

    app._dsp_effects_show_list()
    assert _shown(app) == (True, False, False) and app.rows[0].focused


def test_widening_with_a_module_open_puts_it_beside_the_list(app):
    app.width["now"] = 763
    app._apply_dsp_effects_layout()
    app._dsp_effects_show_detail(focus=False)
    assert _shown(app) == (False, True, True) and not app.dsp_effects_back_btn.focused
    app.width["now"] = 1337
    app._apply_dsp_effects_layout()
    assert _shown(app) == (True, True, False)
    assert [s.value_pos for s in app.dsp_peq_sliders] == ["right", "right"]


def test_a_click_in_the_side_by_side_list_only_selects(app):
    app._apply_dsp_effects_layout()
    app_builders._on_dsp_module_activated(app, None, app.rows[1])
    assert _shown(app) == (True, True, False) and not getattr(app, "_dsp_effects_detail_open", False)


def test_before_the_page_is_built_nothing_happens():
    app_builders._apply_dsp_effects_layout(SimpleNamespace())


class _Factory:
    def __init__(self):
        self.handlers = {}

    def connect(self, signal, handler):
        self.handlers[signal] = handler


class _Label:
    def __init__(self, **kw):
        self.kw, self.label = kw, None

    def set_label(self, text):
        self.label = text


class _Item:
    def __init__(self, text):
        self.text, self.child = text, None

    def set_child(self, child):
        self.child = child

    def get_child(self):
        return self.child

    def get_item(self):
        return SimpleNamespace(get_string=lambda: self.text)


class _DropDown:
    def __init__(self, list_factory=None):
        self.factory, self.list_factory = "built-in", list_factory

    def get_factory(self):
        return self.factory

    def get_list_factory(self):
        return self.list_factory

    def set_factory(self, factory):
        self.factory = factory

    def set_list_factory(self, factory):
        self.list_factory = factory


def test_a_long_preset_name_is_cut_short_in_the_button_and_whole_in_the_list(monkeypatch):
    monkeypatch.setattr(app_builders, "Gtk", SimpleNamespace(SignalListItemFactory=_Factory, Label=_Label))
    dropdown = _DropDown()
    app_builders._ellipsize_selected_name(dropdown)
    assert dropdown.list_factory == "built-in"  # the open list: whole names, the selection checked
    item = _Item("Late-night headphones, warm tilt with crossfeed and a soft limiter")
    dropdown.factory.handlers["setup"](dropdown.factory, item)
    dropdown.factory.handlers["bind"](dropdown.factory, item)
    assert item.child.kw["ellipsize"] == app_builders.Pango.EllipsizeMode.END
    assert item.child.kw["width_chars"] == 8 and item.child.label == item.text

    kept = _DropDown(list_factory="its own")
    app_builders._ellipsize_selected_name(kept)
    assert kept.list_factory == "its own"


def _chain_app(window, card):
    flow = SimpleNamespace(get_parent=lambda: SimpleNamespace(get_width=lambda: card))
    return SimpleNamespace(dsp_chain_flow=flow, win=SimpleNamespace(get_width=lambda: window))


@pytest.mark.parametrize("tile, modules", [(571, 2), (763, 3), (954, 4), (1145, 5), (1337, 6), (1912, 7)])
def test_the_signal_chain_fills_each_tile(tile, modules):
    # The card measured window - 158 at every tile, the sidebar docked or collapsed.
    assert app_builders._dsp_overview_modules_per_row(_chain_app(tile, tile - 158)) == modules


def test_the_chain_reflows_from_a_card_still_wide_from_before(monkeypatch):
    # Narrowed from 1912 to 620 px: the card still reports 1744 when the new row length is picked.
    # The old cap (window - 72, the sidebar collapsed) chose 3 modules (488 px) for a 430 px card
    # and stayed cut.
    assert app_builders._dsp_overview_modules_per_row(_chain_app(620, 1744)) == 2
    assert app_builders._dsp_overview_modules_per_row(_chain_app(600, 1744)) == 2
