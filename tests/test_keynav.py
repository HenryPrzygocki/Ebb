"""Fork: keyboard navigation (ui/keynav.py): one Tab stop per card, per track list, per sidebar."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui import keynav  # noqa: E402


class _W:
    def __init__(self, parent=None, css=(), native=None):
        self.parent, self.css, self.native = parent, set(css), native
        self.can_focus = self.focusable = self.visible = True
        self.win = None

    def get_parent(self):
        return self.parent

    def has_css_class(self, name):
        return name in self.css

    def get_native(self):
        return self.native

    def set_can_focus(self, value):
        self.can_focus = value

    def set_focusable(self, value):
        self.focusable = value

    def get_focusable(self):
        return self.focusable

    def get_visible(self):
        return self.visible

    def grab_focus(self):
        self.win.focus = self


class _Holder(_W):
    def __init__(self, child):
        super().__init__()
        self.child = child

    def get_child(self):
        return self.child


class _Button(_W):
    pass


class _Overlay(_Holder):
    pass


class _Cell(_Holder):
    pass


class _Row(_W):
    pass


class _List(_W):
    def __init__(self, win, n, css=(), native=None):
        super().__init__(css=css, native=win if native is None else native)
        self.rows = [_Row(parent=self, css=("track-row",)) for _ in range(n)]
        for r in self.rows:
            r.win = win
        self.selected = None

    def get_row_at_index(self, i):
        return self.rows[i] if i < len(self.rows) else None

    def get_selected_row(self):
        return self.selected


class _Win:
    def __init__(self):
        self.focus, self.next_focus, self.moves, self.watch = None, None, [], []

    def get_focus(self):
        return self.focus

    def child_focus(self, direction):
        self.moves.append((direction, [lst.can_focus for lst in self.watch]))
        self.focus = self.next_focus
        return True


@pytest.fixture(autouse=True)
def _fake_gtk(monkeypatch):
    monkeypatch.setattr(keynav, "Gtk", SimpleNamespace(
        Button=_Button, Overlay=_Overlay, FlowBoxChild=_Cell, ListBoxRow=_Row, ListBox=_List,
        DirectionType=SimpleNamespace(TAB_FORWARD="forward", TAB_BACKWARD="backward"),
    ))
    monkeypatch.setattr(keynav.GLib, "idle_add", lambda fn, *a: fn(*a))


def test_a_cell_holding_a_button_is_not_a_tab_stop_itself():
    plain, button, badge = _Cell(_W()), _Cell(_Button()), _Cell(_Overlay(_Button()))
    for cell in (plain, button, badge):
        keynav.settle_cell(cell)
    assert plain.focusable and not button.focusable and not badge.focusable


def _track_list(n=4, **kw):
    win = _Win()
    lst = _List(win, n, **kw)
    win.watch = [lst]
    win.next_focus = _W()
    return win, lst


def test_tab_from_anywhere_in_a_track_row_leaves_the_whole_list():
    win, lst = _track_list()
    win.focus = _Button(parent=lst.rows[2])
    assert keynav.leave_list(win) is True
    assert win.moves == [("forward", [False])]  # GTK skipped the list...
    assert lst.can_focus is True  # ...which can take focus again afterwards
    assert lst._fork_last_row is lst.rows[2]
    win.focus = lst.rows[1]
    keynav.leave_list(win, backward=True)
    assert win.moves[-1][0] == "backward"


def test_settings_style_lists_and_popover_menus_keep_gtk_tab():
    win, settings = _track_list()
    for r in settings.rows:
        r.css.clear()
    win.focus = settings.rows[0]
    assert keynav.leave_list(win) is False
    other_native = object()
    _win2, menu = _track_list(native=other_native)
    _win2.focus = menu.rows[0]
    assert keynav.leave_list(_win2) is False
    assert win.moves == [] and _win2.moves == []


def test_entering_a_list_lands_on_a_row_not_on_a_button_in_the_last_row():
    win, lst = _track_list()
    outside = _W()
    win.focus = _Button(parent=lst.rows[3])  # where GTK puts Shift+Tab
    keynav._settle_entry(win, outside)
    assert win.focus is lst.rows[0]
    lst._fork_last_row = lst.rows[2]
    win.focus = _Button(parent=lst.rows[3])
    keynav._settle_entry(win, outside)
    assert win.focus is lst.rows[2]
    lst.selected = lst.rows[1]
    win.focus = lst.rows[0]
    keynav._settle_entry(win, outside)
    assert win.focus is lst.rows[1]


def test_moving_within_a_list_is_left_alone():
    win, lst = _track_list()
    win.focus = _Button(parent=lst.rows[3])
    keynav._settle_entry(win, lst.rows[3])
    assert isinstance(win.focus, _Button)


def test_tab_out_and_back_returns_to_the_same_row():
    win, lst = _track_list()
    win.focus = lst.rows[2]
    assert keynav.on_tab(win) is True
    win.next_focus = _Button(parent=lst.rows[3])
    win.focus = win.next_focus
    keynav._settle_entry(win, _W())
    assert win.focus is lst.rows[2]
