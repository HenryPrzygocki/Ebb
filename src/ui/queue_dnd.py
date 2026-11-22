"""Fork #10: reorder the queue by dragging its rows, or with Alt+Up / Alt+Down on a focused row.

A row drags as a small label with its title. Over another row, a line shows where it will land:
above or below that row's middle. Near the top or bottom edge of the list, the list scrolls.
The move itself is app.move_queue_entry (app/app_queue.py), which keeps the playing track,
Previous, the shuffle order and Up Next consistent. The playing track can't be picked up.
"""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, GObject, Graphene, Gtk, Pango  # noqa: E402

MARK = "ebb-queue-row"
ABOVE, BELOW = "queue-drop-above", "queue-drop-below"
EDGE = 40  # px from a list's top or bottom edge where a drag scrolls it
_drag = {"entry": None}


def current_index(app):
    """The playing track's queue index, or -1. (Not `int(x or -1)`: index 0 is falsy.)"""
    try:
        return int(getattr(app, "current_track_index", -1))
    except (TypeError, ValueError):
        return -1


def attach(app, row, entry, index):
    """Make the queue row for `entry` (at queue `index`) a drop target, and draggable unless it
    is the playing track."""
    row.queue_entry = entry
    if index != current_index(app):
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare", _prepare, entry)
        source.connect("drag-begin", _begin, row)
        source.connect("drag-end", _end, row)
        row.add_controller(source)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", _key, app, row)
        row.add_controller(keys)
    target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
    target.connect("motion", _motion, row)
    target.connect("leave", lambda *_a: _unmark(row))
    target.connect("drop", _drop, app, row)
    row.add_controller(target)


def _prepare(_source, _x, _y, entry):
    _drag["entry"] = entry
    return Gdk.ContentProvider.new_for_value(GObject.Value(GObject.TYPE_STRING, MARK))


def _begin(_source, drag, row):
    title = str(getattr(row.queue_entry, "name", "") or "Track")
    label = Gtk.Label(label=title, ellipsize=Pango.EllipsizeMode.END, max_width_chars=36, css_classes=["queue-drag-icon"])
    Gtk.DragIcon.get_for_drag(drag).set_child(label)
    drag.set_hotspot(-12, -12)
    row.add_css_class("queue-row-dragging")


def _end(_source, _drag_obj, _delete, row):
    _drag["entry"] = None
    row.remove_css_class("queue-row-dragging")


def _unmark(row):
    row.remove_css_class(ABOVE)
    row.remove_css_class(BELOW)


def _motion(_target, x, y, row):
    if _drag["entry"] is None:
        return Gdk.DragAction(0)
    above = y < row.get_height() / 2
    row.remove_css_class(BELOW if above else ABOVE)
    row.add_css_class(ABOVE if above else BELOW)
    _autoscroll(row, x, y)
    return Gdk.DragAction.MOVE


def _index(app, entry):
    return next((i for i, e in enumerate(app._get_active_queue() or []) if e is entry), -1)


def _drop(_target, value, _x, y, app, row):
    _unmark(row)
    entry = _drag["entry"]
    if entry is None or value != MARK:
        return False
    at = _index(app, getattr(row, "queue_entry", None))
    if at < 0:
        return False
    app.move_queue_entry(entry, at if y < row.get_height() / 2 else at + 1)
    return True


def _autoscroll(row, x, y):
    scrolled = row.get_ancestor(Gtk.ScrolledWindow)
    if scrolled is None:
        return
    ok, point = row.compute_point(scrolled, Graphene.Point().init(x, y))
    if not ok:
        return
    height = scrolled.get_height()
    speed = 0.0
    if point.y < EDGE:
        speed = -(EDGE - point.y) / 3
    elif point.y > height - EDGE:
        speed = (point.y - (height - EDGE)) / 3
    scrolled.ebb_drag_speed = speed
    if speed and not getattr(scrolled, "ebb_drag_tick", 0):
        scrolled.ebb_drag_tick = GLib.timeout_add(16, _scroll_tick, scrolled)


def _scroll_tick(scrolled):
    speed = getattr(scrolled, "ebb_drag_speed", 0)
    if not speed or _drag["entry"] is None:
        scrolled.ebb_drag_tick = 0
        return False
    adj = scrolled.get_vadjustment()
    top = max(adj.get_lower(), adj.get_upper() - adj.get_page_size())
    adj.set_value(max(adj.get_lower(), min(top, adj.get_value() + speed)))
    return True


def _key(_ctl, keyval, _code, state, app, row):
    if not (state & Gdk.ModifierType.ALT_MASK) or keyval not in (Gdk.KEY_Up, Gdk.KEY_Down):
        return False
    entry = getattr(row, "queue_entry", None)
    at = _index(app, entry)
    if at < 0:
        return True
    slot = at - 1 if keyval == Gdk.KEY_Up else at + 2
    if 0 <= slot <= len(app._get_active_queue() or []) and app.move_queue_entry(entry, slot):
        GLib.idle_add(_refocus, row.get_parent(), entry)  # after the re-render, also an idle
    return True


def _refocus(list_box, entry):
    child = list_box.get_first_child() if list_box is not None else None
    while child is not None:
        if getattr(child, "queue_entry", None) is entry:
            child.grab_focus()
            break
        child = child.get_next_sibling()
    return False
