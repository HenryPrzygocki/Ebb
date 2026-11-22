"""Fork: one rule for getting out of things.

Back (the header's arrow, Alt+Left, the Back key, the mouse's back button) and Escape step out
of whatever is on top, one layer at a time:

1. the sidebar floating over the content (narrow windows),
2. Now Playing,
3. the queue drawer,
4. Escape only: the bottom workspace (lyrics, visualizer, DSP). Back leaves it open: it is
   docked, you browse with it open, and Back is for browsing,
   Escape only, next: a selection mode on the page (search results, an album's or a
   playlist's tracks),
5. Settings, back to the page it was opened from,
6. otherwise the page history, as the header's Back always did.

In the mini player the pages are hidden, so only its queue closes.

The header's arrow is enabled whenever one of these applies, so it never sits greyed out
while there is something to step out of (Settings used to be a dead end for it).
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

SETTINGS = "settings"


class BackButton(Gtk.Button):
    """The header's Back. The page code sets its sensitivity for the page history, as it always
    did; an open layer enables it as well (set_layer_open)."""

    def __init__(self, **kwargs):
        page_back = bool(kwargs.pop("sensitive", True))
        super().__init__(**kwargs)
        self.page_back = page_back
        self.layer_open = False
        self._apply()

    def set_sensitive(self, sensitive):
        self.page_back = bool(sensitive)
        self._apply()

    def set_layer_open(self, is_open):
        self.layer_open = bool(is_open)
        self._apply()

    def _apply(self):
        Gtk.Button.set_sensitive(self, self.page_back or self.layer_open)


def _revealed(app, name):
    revealer = getattr(app, name, None)
    try:
        return revealer is not None and bool(revealer.get_reveal_child())
    except Exception:
        return False


def _sidebar_floating(app):
    sidebar = getattr(app, "sidebar_box", None)
    return bool(getattr(app, "_sidebar_collapsed", False)) and sidebar is not None and sidebar.get_visible()


def settings_open(app):
    stack = getattr(app, "right_stack", None)
    return stack is not None and stack.get_visible_child_name() == SETTINGS


def layer_open(app):
    """True while something other than the page history is there to step out of."""
    return (
        _sidebar_floating(app)
        or _revealed(app, "now_playing_revealer")
        or _revealed(app, "queue_revealer")
        or settings_open(app)
    )


def open_settings(app):
    stack = getattr(app, "right_stack", None)
    if stack is None:
        return
    current = stack.get_visible_child_name()
    if current == SETTINGS:
        return
    app._settings_return_to = current
    # Fork: Settings isn't a sidebar page, so no row stays lit under it; leaving relights it.
    nav = getattr(app, "nav_list", None)
    app._settings_return_row = nav.get_selected_row() if nav is not None else None
    if app._settings_return_row is not None:
        nav.select_row(None)
    stack.set_visible_child_name(SETTINGS)


def leave_settings(app):
    stack = app.right_stack
    target = getattr(app, "_settings_return_to", None) or "grid_view"
    app._settings_return_to = None
    if stack.get_child_by_name(target) is None:
        target = "grid_view"
    stack.set_visible_child_name(target)
    row, app._settings_return_row = getattr(app, "_settings_return_row", None), None
    nav = getattr(app, "nav_list", None)
    # Unless a row was picked meanwhile. select_row emits row-selected only: no navigation.
    if row is not None and nav is not None and nav.get_selected_row() is None and row.get_parent() is nav:
        nav.select_row(row)


def step_back(app, escape=False):
    """Close the top layer, else go back a page. True when something happened."""
    if getattr(app, "is_mini_mode", False):
        # The mini player hides the pages: only its queue is there to close.
        if _revealed(app, "mini_queue_revealer"):
            app.close_mini_queue()
            return True
        return False
    hide_sidebar = getattr(app, "_hide_sidebar_overlay", None)
    if callable(hide_sidebar) and hide_sidebar():
        return True
    if _revealed(app, "now_playing_revealer"):
        app.hide_now_playing_overlay()
        return True
    if _revealed(app, "queue_revealer"):
        app.close_queue_drawer()
        return True
    if escape and _revealed(app, "viz_revealer"):
        app._set_visualizer_expanded(False)
        app.settings["viz_expanded"] = False  # else it reopens on the next start
        app.schedule_save_settings()
        return True
    exit_selecting = getattr(app, "exit_selection_modes", None)
    if escape and not settings_open(app) and callable(exit_selecting) and exit_selecting():
        return True
    if settings_open(app):
        leave_settings(app)
        return True
    btn = getattr(app, "back_btn", None)
    if btn is not None and getattr(btn, "page_back", btn.get_sensitive()):
        app.on_back_clicked(btn)
        return True
    return False


def install(app):
    """Keep the header's Back enabled while a layer is open. Call once the window is built."""

    def sync(*_args):
        btn = getattr(app, "back_btn", None)
        if isinstance(btn, BackButton):
            btn.set_layer_open(layer_open(app))

    for name, signal in (
        ("now_playing_revealer", "notify::reveal-child"),
        ("queue_revealer", "notify::reveal-child"),
        ("right_stack", "notify::visible-child-name"),
        ("sidebar_box", "notify::visible"),
    ):
        widget = getattr(app, name, None)
        if widget is not None:
            widget.connect(signal, sync)
    sync()
