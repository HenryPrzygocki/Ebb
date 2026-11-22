"""Fork: app-wide keyboard-navigation fixes.

GTK makes every FlowBox cell a Tab stop. Most grids here put a Button inside the cell (cards,
recent-search chips), so Tab stopped twice per item: first on the cell, then on the button.
A cell that holds its own control must not take focus itself; GTK then hands focus straight to
the control (gtk_flow_box_child_focus), so each card is one stop. Patching FlowBox.append and
insert once covers every grid, including ones upstream adds later, without touching each site.
"""
from gi.repository import GLib, Gtk


def holds_control(widget):
    """True for a Button, or an Overlay drawn over a Button (cards with badges)."""
    if isinstance(widget, Gtk.Button):
        return True
    return isinstance(widget, Gtk.Overlay) and isinstance(widget.get_child(), Gtk.Button)


def settle_cell(cell):
    if cell is not None and holds_control(cell.get_child()):
        cell.set_focusable(False)


def _cell_of(child):
    return child if isinstance(child, Gtk.FlowBoxChild) else child.get_parent()


def install():
    if getattr(Gtk.FlowBox, "_fork_keynav", False):
        return
    append, insert = Gtk.FlowBox.append, Gtk.FlowBox.insert

    def _append(self, child):
        append(self, child)
        settle_cell(_cell_of(child))

    def _insert(self, child, position):
        insert(self, child, position)
        settle_cell(_cell_of(child))

    Gtk.FlowBox.append, Gtk.FlowBox.insert = _append, _insert
    Gtk.FlowBox._fork_keynav = True


# --- Tab past whole lists ------------------------------------------------------------------
#
# GTK4 ListBox treats Tab like Down: every row is a Tab stop, so getting past Liked Songs took
# hundreds of presses. In track lists and the sidebar, Tab now leaves the list (one stop per
# list, as in Nautilus); Up/Down move between rows, Left/Right reach a row's buttons, Enter
# plays, and Menu / Shift+F10 opens the row's menu. Settings-style lists keep per-row Tab,
# since each of their rows holds its own control.


def _list_to_leave(widget, win):
    row = None
    while widget is not None:
        if isinstance(widget, Gtk.ListBoxRow):
            row = widget
        elif isinstance(widget, Gtk.ListBox):
            if row is None or widget.get_native() is not win:
                return None  # popover menus keep GTK's own Tab
            if row.has_css_class("track-row") or widget.has_css_class("navigation-sidebar"):
                return widget
            return None
        widget = widget.get_parent()
    return None


def _row_of(widget):
    while widget is not None and not isinstance(widget, Gtk.ListBoxRow):
        widget = widget.get_parent()
    return widget


def _entry_row(lst):
    """Where Tab enters a list: its selected row, else the row Tab last left from, else the first."""
    for row in (lst.get_selected_row(), getattr(lst, "_fork_last_row", None)):
        if row is not None and row.get_parent() is lst and row.get_visible():
            return row
    i = 0
    while (row := lst.get_row_at_index(i)) is not None:
        if row.get_visible() and row.get_focusable():
            return row
        i += 1
    return None


def _settle_entry(win, before):
    # GTK enters a ListBox backwards on the last row's last button; land on a row instead.
    focus = win.get_focus()
    lst = _list_to_leave(focus, win)
    if lst is not None and lst is not _list_to_leave(before, win):
        row = _entry_row(lst)
        if row is not None and row is not focus:
            row.grab_focus()
    return False


def on_tab(win, backward=False):
    """Tab / Shift+Tab from the window's capture phase. True when the key was handled here."""
    if win is None:
        return False
    before = win.get_focus()
    handled = leave_list(win, backward)
    GLib.idle_add(_settle_entry, win, before)
    return handled


def leave_list(win, backward=False):
    """Move focus past the list holding the focus, if it is one Tab should skip as a whole."""
    focus = win.get_focus() if win is not None else None
    lst = _list_to_leave(focus, win)
    if lst is None:
        return False
    lst._fork_last_row = _row_of(focus)
    direction = Gtk.DirectionType.TAB_BACKWARD if backward else Gtk.DirectionType.TAB_FORWARD
    # With the list unable to take focus, GTK's own traversal resumes at the next widget after it.
    lst.set_can_focus(False)
    try:
        return bool(win.child_focus(direction))
    finally:
        lst.set_can_focus(True)
