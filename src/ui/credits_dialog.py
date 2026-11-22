"""Fork #24: a track's credits, from its right-click menu (upstream `#54` asked for them).

tidalapi doesn't wrap TIDAL's `tracks/{id}/credits`; backend.get_track_credits does. The dialog
opens at once with a spinner and fills in when the credits arrive: the track and its artist,
then each role (Producer, Composer, Engineer, ...) with its people. A name TIDAL knows as an
artist opens that artist's page, the way "Go to Artist" does.
"""
import logging
from threading import Thread
from types import SimpleNamespace

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

logger = logging.getLogger(__name__)


def show(app, track):
    """Open the credits of `track` over the window."""
    tid = getattr(track, "id", None)
    title = str(getattr(track, "name", None) or getattr(track, "title", None) or "Track")
    artist = str(getattr(getattr(track, "artist", None), "name", None) or "")
    dialog = Adw.Dialog(title="Credits", content_width=400, content_height=560)
    view = Adw.ToolbarView()
    view.add_top_bar(Adw.HeaderBar())
    stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
    spinner = Adw.Spinner(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
    spinner.set_size_request(32, 32)
    stack.add_named(spinner, "loading")
    view.set_content(stack)
    dialog.set_child(view)
    app._credits_dialog = dialog
    dialog.present(getattr(app, "win", None))

    def finish(credits):
        stack.add_named(content(app, dialog, title, artist, credits), "credits")
        stack.set_visible_child_name("credits")
        return False

    def task():
        try:
            credits = app.backend.get_track_credits(tid)
        except Exception:
            logger.exception("Credits for track %s failed", tid)
            credits = None
        GLib.idle_add(finish, credits)

    Thread(target=task, daemon=True, name="credits").start()
    return dialog


def content(app, dialog, title, artist, credits):
    """The dialog's page for `credits` (backend.get_track_credits): a status page when it
    failed (None) or there are none, else the roles and their people."""
    if not credits:
        page = Adw.StatusPage(
            title="Couldn't load the credits" if credits is None else "No credits",
            description="TIDAL didn't send them. Try again in a moment."
            if credits is None else "TIDAL has no credits for this track.",
        )
        page.add_css_class("compact")
        return page
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=6, margin_bottom=24,
                  margin_start=24, margin_end=24)
    box.append(Gtk.Label(label=title, xalign=0, wrap=True, css_classes=["title-3"]))
    if artist:
        box.append(Gtk.Label(label=artist, xalign=0, wrap=True, css_classes=["dim-label"]))
    for role, people in credits:
        box.append(Gtk.Label(label=role, xalign=0, wrap=True,
                             css_classes=["credits-role", "caption-heading", "dim-label"]))
        for name, artist_id in people:
            box.append(_person(app, dialog, name, artist_id))
    scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
    scroller.set_child(box)
    return scroller


def _person(app, dialog, name, artist_id):
    label = Gtk.Label(label=name, xalign=0, wrap=True)
    if not artist_id:
        label.add_css_class("credits-name")
        return label
    button = Gtk.Button(child=label, halign=Gtk.Align.START, css_classes=["flat", "credits-name"])
    button.set_tooltip_text("Go to Artist")
    button.connect("clicked", lambda _b: open_artist(app, dialog, artist_id, name))
    return button


def open_artist(app, dialog, artist_id, name):
    dialog.close()
    go = getattr(app, "go_to_artist_of", None)
    if callable(go):
        go(SimpleNamespace(artist=SimpleNamespace(id=artist_id, name=name)))
