import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk


LAYOUT = {
    "index_width": 30,
    "artist_width": 130,
    "album_width": 170,
    "time_width": 64,
    "col_gap": 16,
    "head_margin_x": 0,
    "head_margin_bottom": 6,
    "row_margin_y": 6,
    "row_margin_x": 0,
    "cell_margin_end": 12,
}


def create_head_click_label(text, on_click, xalign=0.0, hexpand=False, extra_classes=None):
    classes = ["tracks-head-label", "tracks-head-click"]
    if extra_classes:
        classes.extend(extra_classes)
    lbl = Gtk.Label(label=text, xalign=xalign, css_classes=classes)
    if hexpand:
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.FILL)
    tap = Gtk.GestureClick()
    tap.connect("pressed", lambda *_args: on_click(None))
    lbl.add_controller(tap)
    return lbl


def build_tracks_header(
    *,
    on_sort_title,
    on_sort_artist,
    on_sort_album,
    on_sort_time,
    title_text="Title",
    artist_text="Artist",
    album_text="Album",
    time_text="Time",
    app=None,
):
    head = Gtk.Box(
        spacing=LAYOUT["col_gap"],
        margin_start=LAYOUT["head_margin_x"],
        margin_end=LAYOUT["head_margin_x"],
        margin_bottom=LAYOUT["head_margin_bottom"],
        css_classes=["tracks-table-head"],
    )
    idx_head = Gtk.Label(label="#", xalign=0.5, css_classes=["tracks-head-label", "tracks-head-index"])
    idx_head.set_size_request(LAYOUT["index_width"], -1)
    title_head = create_head_click_label(title_text, on_sort_title, xalign=0.0, hexpand=True)
    title_head.set_halign(Gtk.Align.FILL)
    artist_head = create_head_click_label(artist_text, on_sort_artist, xalign=0.0)
    artist_head.set_size_request(LAYOUT["artist_width"], -1)
    artist_head.set_margin_end(LAYOUT["cell_margin_end"])
    album_head = create_head_click_label(album_text, on_sort_album, xalign=0.0)
    album_head.set_size_request(LAYOUT["album_width"], -1)
    album_head.set_margin_end(LAYOUT["cell_margin_end"])
    dur_head = create_head_click_label(time_text, on_sort_time, xalign=1.0, extra_classes=["tracks-head-time"])
    dur_head.set_halign(Gtk.Align.END)
    dur_head.set_size_request(LAYOUT["time_width"], -1)
    head.append(idx_head)
    head.append(title_head)
    head.append(artist_head)
    head.append(album_head)
    head.append(dur_head)
    if app is not None:
        bind_track_column(app, artist_head, "artist-column")
        bind_track_column(app, album_head, "album-column")
    return head, {"title": title_head, "artist": artist_head, "album": album_head, "time": dur_head}


def _build_header_action_spacer(kind):
    if kind == "fav":
        w = Gtk.Button(
            icon_name="hiresti-favorite-outline-symbolic",
            css_classes=["flat", "circular", "track-heart-btn"],
        )
        w.set_sensitive(False)
        w.set_focusable(False)
        w.set_opacity(0.0)
        return w

    if kind == "add":
        w = Gtk.Button(
            icon_name="list-add-symbolic",
            css_classes=["flat", "circular", "history-scroll-btn"],
        )
        w.set_sensitive(False)
        w.set_focusable(False)
        w.set_opacity(0.0)
        return w

    if kind == "menu":
        w = Gtk.MenuButton(
            icon_name="view-more-symbolic",
            css_classes=["flat", "circular", "history-scroll-btn", "track-row-overflow-btn"],
        )
        w.set_sensitive(False)
        w.set_focusable(False)
        w.set_opacity(0.0)
        return w

    if kind == "remove":
        w = Gtk.Button(
            icon_name="list-remove-symbolic",
            css_classes=["flat", "playlist-tool-btn", "queue-remove-btn"],
        )
        w.set_sensitive(False)
        w.set_focusable(False)
        w.set_opacity(0.0)
        return w

    if kind == "playlist_remove":
        w = Gtk.Button(
            icon_name="user-trash-symbolic",
            css_classes=["flat", "playlist-tool-btn"],
        )
        w.set_sensitive(False)
        w.set_focusable(False)
        w.set_opacity(0.0)
        return w

    if kind == "drag":
        w = Gtk.Image.new_from_icon_name("open-menu-symbolic")
        w.add_css_class("dim-label")
        w.set_opacity(0.0)
        return w

    w = Gtk.Box()
    w.set_size_request(1, -1)
    return w


def append_header_action_spacers(head, kinds):
    for kind in list(kinds or []):
        head.append(_build_header_action_spacer(kind))


# ---------------------------------------------------------------- fork: adaptive columns
class TrackColumns(GObject.Object):
    """Which optional track-table columns fit the content width.

    Adw.Breakpoint setters on the content area flip these (ui.builders); every row binds its
    labels' "visible" to them, so a resize updates thousands of rows without a Python loop.
    With artist-column off, the artist shows under the title instead of in its own column.
    """

    artist_column = GObject.Property(type=bool, default=True)
    album_column = GObject.Property(type=bool, default=True)


def track_columns(app):
    cols = getattr(app, "_track_columns", None)
    if cols is None:
        cols = TrackColumns()
        app._track_columns = cols
    return cols


def bind_track_column(app, widget, prop, invert=False):
    flags = GObject.BindingFlags.SYNC_CREATE
    if invert:
        flags |= GObject.BindingFlags.INVERT_BOOLEAN
    track_columns(app).bind_property(prop, widget, "visible", flags)
    return widget


def adapt_track_row(app, title_widget, artist_widget, album_widget, album_hidden=False):
    """Bind a built row's artist/album cells to the column state and give the title an artist line.

    album_hidden: the page itself is one album, so the album cell would only repeat its title.
    """
    bind_track_column(app, artist_widget, "artist-column")
    if album_hidden:
        album_widget.set_visible(False)
    else:
        bind_track_column(app, album_widget, "album-column")
    parent = title_widget.get_parent()
    if parent is None:
        return
    prev = title_widget.get_prev_sibling()
    cell = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        hexpand=True,
        valign=Gtk.Align.CENTER,
        css_classes=["track-title-cell"],
    )
    parent.remove(title_widget)
    cell.append(title_widget)
    artist_text = artist_widget.get_label() if isinstance(artist_widget, Gtk.Label) else ""
    sub = Gtk.Label(label=artist_text or "", xalign=0, ellipsize=3, css_classes=["dim-label", "track-subtitle"])
    bind_track_column(app, sub, "artist-column", invert=True)
    cell.append(sub)
    parent.insert_child_after(cell, prev)


def clear_track_rows(listbox):
    """Fork: remove the rows only. A ListBox's placeholder is a child widget too, so walking
    get_first_child() (or calling remove_all()) also removes and drops the placeholder."""
    while (row := listbox.get_row_at_index(0)) is not None:
        listbox.remove(row)


def set_track_rows_hidden(listbox, track_id, hidden):
    """Fork: hide (or show again) every row for track_id, then renumber the visible rows.

    Hidden rows keep their index, so row.get_index() still matches app.current_track_list."""
    if listbox is None or track_id is None:
        return
    i = shown = 0
    while (row := listbox.get_row_at_index(i)) is not None:
        i += 1
        if getattr(row, "track_id", None) == track_id:
            row.set_visible(not hidden)
        if row.get_visible():
            shown += 1
            label = getattr(row, "track_number_label", None)
            if label is not None:
                label.set_text(str(shown))
