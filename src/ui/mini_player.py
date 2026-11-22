"""Fork: the mini player has two layouts, a strip and a cover (#18).

Upstream's mini player was one strip, fixed at 390 x 85 px, and its content did not fit: the
bar's padding and the 80 px cover made it about 130 px tall, so the cover was cut off, the play
button clipped and the queue arrow fell outside the window. On a large or high-resolution
screen it was tiny too, and there was no way to see the cover any bigger
(`yelanxin/hiresTI#17`, answered with "scale to 150%", and `#30`).

- Strip: 420 x 96 px, fixed. The cover (as tall as the strip), the title and artist, and on the right the
  queue / layout / leave / close buttons over the transport. A GTK 4 window has no maximum
  size, so a resizable strip could be pulled into a tall window with a thin bar in it, and a
  tiling compositor would do that by itself.
- Cover: the cover as large as the window allows, the title, artist and album under it, then
  the timeline and the whole transport, Shuffle and Repeat included. This window is resizable
  and keeps the size you give it.

The button in the corner switches between them; the choice and the cover window's size are
kept (settings "mini_layout", "mini_cover_width", "mini_cover_height").

Both layouts are the player bar's own widgets, so whatever updates the bar (the track, the
heart, the timeline, the play button, Shuffle and Repeat) updates them too. The transport
moves from the bar's centre slot to its end slot: in the strip that puts it on the right
under the corner buttons, and in the cover layout, where the bar turns vertical, under the
cover (a vertical Gtk.CenterBox centres its middle child in the whole height: on the cover).
The cover is a Gtk.Picture loaded at 640 px and scaled by GTK, sharp at either size and at
any display scale; the bar's own cover is an 80 px bitmap. The cover layout keeps the window
decorated, without the header: an undecorated GTK window has no resize edges.
"""
import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

import utils  # noqa: E402

STRIP = "strip"
COVER = "cover"
STRIP_SIZE = (420, 96)
COVER_MIN = (320, 460)
COVER_DEFAULT = (340, 530)  # the cover spans the width at this height
COVER_PX = 640  # TIDAL serves 80, 160, 320, 640 and 1280 px covers; the bar uses 320
_TIDAL_SIZE = re.compile(r"(resources\.tidal\.com/images/.+/)\d+x\d+(\.jpg)$")


def layout(app):
    settings = getattr(app, "settings", None) or {}
    return COVER if settings.get("mini_layout") == COVER else STRIP


def build(app):
    """The mini player's cover (hidden until used), the layout button, and the queue button in
    the corner row. Called once the player bar is built."""
    picture = Gtk.Picture(content_fit=Gtk.ContentFit.COVER, can_shrink=True, css_classes=["mini-cover-art"])
    picture.set_overflow(Gtk.Overflow.HIDDEN)  # clips to the CSS border-radius
    picture.set_tooltip_text("Now Playing")
    picture.set_cursor_from_name("pointer")
    click = Gtk.GestureClick()
    # As a click on the bar's cover: Now Playing, which leaves the mini player. "released", so a
    # drag that starts on the cover still moves the window.
    click.connect("released", lambda gesture, n, x, y: app.on_player_art_clicked(gesture, n, x, y))
    picture.add_controller(click)
    # In the cover layout the corner buttons move onto the cover (an overlay on it), so they
    # sit on its corner whatever the window's shape. Left-aligned: a wide window keeps one left
    # edge for the cover, the text and the timeline.
    overlay = Gtk.Overlay()
    overlay.set_child(picture)
    frame = Gtk.AspectFrame(ratio=1.0, obey_child=False, xalign=0.0, yalign=0.0)
    frame.set_child(overlay)
    frame.set_visible(False)
    app.mini_cover = picture
    app.mini_cover_overlay = overlay
    app.mini_cover_frame = frame
    app.info_area.prepend(frame)

    controls = app.mini_controls
    controls.add_css_class("mini-controls")
    button = Gtk.Button(css_classes=["flat", "circular"])
    button.connect("clicked", lambda _b: toggle(app))
    app.mini_layout_btn = button
    controls.prepend(button)
    # The queue button sat at the bar's bottom edge, which was outside the window.
    arrow = getattr(app, "mini_queue_arrow", None)
    if arrow is not None:
        app.player_overlay.remove_overlay(arrow)
        arrow.set_icon_name("hiresti-queue-symbolic")
        arrow.set_halign(Gtk.Align.CENTER)
        arrow.set_valign(Gtk.Align.CENTER)
        arrow.set_margin_bottom(0)
        controls.prepend(arrow)
    _sync_button(app)


def toggle(app):
    """Switch between the strip and the cover, and keep the choice."""
    new = STRIP if layout(app) == COVER else COVER
    mini = bool(getattr(app, "is_mini_mode", False))
    if mini:
        leave(app)
    app.settings["mini_layout"] = new
    app.schedule_save_settings()
    if mini:
        enter(app)
    _sync_button(app)


def enter(app):
    """Lay the mini player out. toggle_mini_mode has already hidden the pages and set up what
    the two layouts share."""
    which = layout(app)
    cover = which == COVER
    win = app.win
    if cover and hasattr(app, "close_mini_queue"):
        app.close_mini_queue()  # the strip's drawer
    _shape(app, which)
    _show(getattr(app, "mini_queue_arrow", None), not cover)
    _show(getattr(app, "timeline_box", None), cover)
    for name in ("shuffle_btn", "repeat_btn"):
        _show(getattr(app, name, None), cover)
    load_cover(app)
    if cover:
        win.remove_css_class("mini-mode")
        win.add_css_class("mini-cover")
        win.set_decorated(True)
        win.set_resizable(True)
        win.set_size_request(*COVER_MIN)
        win.set_default_size(*cover_size(app))
    else:
        win.remove_css_class("mini-cover")
        win.set_decorated(False)
        win.add_css_class("mini-mode")
        win.set_resizable(False)
        win.set_size_request(*STRIP_SIZE)
        win.set_default_size(*STRIP_SIZE)
    _sync_button(app)


def leave(app):
    """Put the bar back as it was, before it goes back to normal or to the other layout."""
    if getattr(app, "_mini_shape", None) == COVER:
        _remember_cover_size(app)
    _shape(app, None)
    win = getattr(app, "win", None)
    if win is not None:
        win.remove_css_class("mini-cover")


def cover_size(app):
    settings = getattr(app, "settings", None) or {}
    width = int(settings.get("mini_cover_width") or COVER_DEFAULT[0])
    height = int(settings.get("mini_cover_height") or COVER_DEFAULT[1])
    return max(COVER_MIN[0], width), max(COVER_MIN[1], height)


def cover_url(app, ref):
    """The 640 px version of a cover reference (a TIDAL image id; a URL or a path as is)."""
    if not ref:
        return None
    if isinstance(ref, str) and ("http" in ref or "file://" in ref or ref.startswith("/")):
        return _TIDAL_SIZE.sub(rf"\g<1>{COVER_PX}x{COVER_PX}\g<2>", ref)
    return app._get_tidal_image_url(ref, COVER_PX, COVER_PX)


def load_cover(app):
    """Show the playing track's cover in the mini player, if it is open. Called when it opens
    and when a track's cover loads (playback_stream_actions.load_cover_art)."""
    picture = getattr(app, "mini_cover", None)
    if picture is None or getattr(app, "_mini_shape", None) is None:
        return
    url = cover_url(app, getattr(app, "_bar_cover_ref", None))
    if not url or getattr(picture, "_cover_url", None) == url:
        return
    picture._cover_url = url
    utils.load_img(picture, url, app.cache_dir, COVER_PX, fit=True)


def _shape(app, which):
    """Lay the bar's widgets out for the strip, the cover, or (None) the bar itself."""
    current = getattr(app, "_mini_shape", None)
    if current == which:
        return
    app._mini_shape = which
    mini = which is not None
    cover = which == COVER
    bar = app.bottom_bar
    center = app.player_center_panel
    if mini and current is None:  # the transport goes to the end slot
        bar.set_center_widget(None)
        bar.set_end_widget(None)
        bar.set_end_widget(center)
    elif not mini and current is not None:
        bar.set_end_widget(None)
        bar.set_center_widget(center)
        bar.set_end_widget(app.player_right_panel)
    bar.set_orientation(Gtk.Orientation.VERTICAL if cover else Gtk.Orientation.HORIZONTAL)
    for name in ("mini-strip", "mini-cover"):
        bar.remove_css_class(name)
    if mini:
        bar.add_css_class("mini-cover" if cover else "mini-strip")
    # Strip: the transport at the bottom, under the corner buttons.
    center.set_valign(Gtk.Align.END if which == STRIP else Gtk.Align.FILL)

    info = app.info_area
    info.set_orientation(Gtk.Orientation.VERTICAL if cover else Gtk.Orientation.HORIZONTAL)
    info.set_valign(Gtk.Align.FILL if cover else Gtk.Align.CENTER)
    for widget in (app.player_left_panel, info):
        widget.set_hexpand(mini)  # the text takes the room the transport leaves
        widget.set_vexpand(cover)
        widget.set_halign(Gtk.Align.FILL if mini else Gtk.Align.START)
    app.player_text_box.set_hexpand(mini)
    # Cover: the title takes the row, so the heart sits under the cover's right edge.
    for widget in (app.player_title_row, app.lbl_title):
        widget.set_hexpand(cover)
    if mini:
        _show(getattr(app, "lbl_album", None), cover)  # leaving puts the window tier's back

    timeline = app.timeline_box
    timeline.set_hexpand(cover)
    timeline.set_halign(Gtk.Align.FILL if cover else Gtk.Align.CENTER)
    if cover:
        timeline.set_size_request(-1, -1)  # leaving puts the window tier's width back
        app.player_center_box.reorder_child_after(app.player_ctrls, timeline)  # timeline, transport
    elif current == COVER:
        app.player_center_box.reorder_child_after(timeline, app.player_ctrls)

    # The cover's natural size is its texture's (640 px), so it takes all the width it is given
    # and is square: the strip's full height, the cover layout's full width. It does not
    # expand: a taller window puts the room under the text, not between the cover and the title.
    frame = app.mini_cover_frame
    frame.set_visible(mini)
    frame.set_hexpand(cover)
    frame.set_valign(Gtk.Align.START if cover else Gtk.Align.CENTER)
    _show(getattr(app, "art_img", None), not mini)
    _move_controls(app, app.mini_cover_overlay if cover else app.player_overlay)


def _move_controls(app, overlay):
    controls = app.mini_controls
    parent = controls.get_parent()
    if parent is overlay:
        return
    if parent is not None:
        parent.remove_overlay(controls)
    overlay.add_overlay(controls)


def _remember_cover_size(app):
    """The default size follows the user's resizing and is what set_default_size takes; the
    allocation can differ by the window frame, which shrank the window on every round trip."""
    win = getattr(app, "win", None)
    settings = getattr(app, "settings", None)
    if win is None or not isinstance(settings, dict):
        return
    width, height = win.get_default_size()
    if width < COVER_MIN[0] or height < COVER_MIN[1]:
        width, height = win.get_width(), win.get_height()
    if width >= COVER_MIN[0] and height >= COVER_MIN[1]:
        settings["mini_cover_width"] = width
        settings["mini_cover_height"] = height
        app.schedule_save_settings()


def _sync_button(app):
    button = getattr(app, "mini_layout_btn", None)
    if button is None:
        return
    if layout(app) == COVER:
        button.set_icon_name("ebb-mini-strip-symbolic")
        button.set_tooltip_text("Compact Strip")
    else:
        button.set_icon_name("ebb-mini-cover-symbolic")
        button.set_tooltip_text("Large Cover")


def _show(widget, visible):
    if widget is not None:
        widget.set_visible(visible)
