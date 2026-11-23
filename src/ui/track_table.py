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
    # Fork #27: on wide content the artist and album columns grow too (min-width tiers in
    # ui.builders). At a fixed 130/170 px, a 1920 px window gave the title ~1000 px of mostly
    # empty space while "The Brook & The…" and "I Love You, Honeybear…" were cut short.
    artist_width = GObject.Property(type=int, default=LAYOUT["artist_width"])
    album_width = GObject.Property(type=int, default=LAYOUT["album_width"])


def track_columns(app):
    cols = getattr(app, "_track_columns", None)
    if cols is None:
        cols = TrackColumns()
        app._track_columns = cols
    return cols


_COLUMN_WIDTH = {"artist-column": "artist-width", "album-column": "album-width"}


def bind_track_column(app, widget, prop, invert=False):
    flags = GObject.BindingFlags.SYNC_CREATE
    if invert:
        flags |= GObject.BindingFlags.INVERT_BOOLEAN
    cols = track_columns(app)
    cols.bind_property(prop, widget, "visible", flags)
    width = _COLUMN_WIDTH.get(prop)
    # The column cell itself (not the inverted under-title line) follows the width tier. Its
    # label's max-width-chars keeps its natural width under the request, so every row's cell
    # gets exactly the tier's width and the columns stay aligned.
    if width and not invert and widget.find_property("width-request") is not None:
        cols.bind_property(width, widget, "width-request", GObject.BindingFlags.SYNC_CREATE)
    return widget


def link_label(label, on_activate):
    """Fork: make a label's text a link: underline and pointer over the text, click to follow.

    Only the text is live, not the rest of the cell, and the click is claimed so the row
    doesn't also start playing.
    """
    if not isinstance(label, Gtk.Label) or not callable(on_activate):
        return label
    label.add_css_class("track-link")

    def over_text(x):
        layout = label.get_layout()
        if layout is None:
            return False
        _ink, logical = layout.get_pixel_extents()
        return 0 <= x <= logical.width + 1  # xalign 0: the text starts at the left edge

    def set_hot(hot):
        if hot == getattr(label, "_link_hot", False):
            return
        label._link_hot = hot
        if hot:
            label.add_css_class("track-link-hot")
            label.set_cursor_from_name("pointer")
        else:
            label.remove_css_class("track-link-hot")
            label.set_cursor(None)

    motion = Gtk.EventControllerMotion()
    motion.connect("enter", lambda _c, x, _y: set_hot(over_text(x)))
    motion.connect("motion", lambda _c, x, _y: set_hot(over_text(x)))
    motion.connect("leave", lambda _c: set_hot(False))
    label.add_controller(motion)

    click = Gtk.GestureClick(button=1)

    def pressed(gesture, _n_press, x, _y):
        if over_text(x):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def released(_gesture, n_press, x, _y):
        if n_press == 1 and over_text(x):
            on_activate()

    click.connect("pressed", pressed)
    click.connect("released", released)
    label.add_controller(click)
    return label


_QUALITY_BADGES = {
    # tier: (text, css class, tooltip)
    "hires": ("Hi-Res", "track-quality-hires", "Hi-Res: FLAC up to 24-bit/192 kHz"),
    "lossy": ("AAC", "track-quality-lossy", "TIDAL only has this track as AAC (lossy)"),
}


def track_quality_tier(track):
    """Fork: a track's best quality on TIDAL: "hires" (24-bit FLAC), "lossy" (AAC only),
    or None for the CD-quality FLAC baseline and for tracks without quality data."""
    tags = {str(tag).upper() for tag in (getattr(track, "media_metadata_tags", None) or [])}
    quality = str(getattr(track, "audio_quality", "") or "").upper()
    if "HIRES_LOSSLESS" in tags or quality == "HI_RES_LOSSLESS":
        return "hires"
    if quality in ("HIGH", "LOW") and "LOSSLESS" not in tags:
        return "lossy"
    return None


def quality_badge(track):
    """A small badge for track_quality_tier(track), or None."""
    spec = _QUALITY_BADGES.get(track_quality_tier(track))
    if spec is None:
        return None
    text, css, tip = spec
    return Gtk.Label(label=text, valign=Gtk.Align.CENTER, css_classes=["track-quality", css], tooltip_text=tip)


def adapt_track_row(app, title_widget, artist_widget, album_widget, album_hidden=False, track=None,
                    artist_hidden=False):
    """Bind a built row's artist/album cells to the column state and give the title an artist line.

    album_hidden: the page itself is one album, so the album cell would only repeat its title.
    track: makes the artist and album names links to their pages and badges the title with
        the track's quality (fork).
    artist_hidden (fork): every track on the page is by the album's own artist, whom the header
        names, so neither the artist cell nor the title's artist line is shown.
    """
    if artist_hidden:
        artist_widget.set_visible(False)
    else:
        bind_track_column(app, artist_widget, "artist-column")
    if album_hidden:
        album_widget.set_visible(False)
    else:
        bind_track_column(app, album_widget, "album-column")
    go_artist = getattr(app, "go_to_artist_of", None) if track is not None else None
    go_album = getattr(app, "go_to_album_of", None) if track is not None else None
    has_artist = callable(go_artist) and getattr(track, "artist", None) is not None
    if has_artist:
        link_label(artist_widget, lambda: go_artist(track))
    if callable(go_album) and not album_hidden and getattr(track, "album", None) is not None:
        link_label(album_widget, lambda: go_album(track))
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
    badge = quality_badge(track) if track is not None else None
    if badge is None:
        cell.append(title_widget)
    else:  # the title shrinks (ellipsizes) before the badge goes
        line = Gtk.Box(spacing=6, css_classes=["track-title-line"])
        title_widget.set_hexpand(False)
        line.append(title_widget)
        line.append(badge)
        cell.append(line)
    if not artist_hidden:
        artist_text = artist_widget.get_label() if isinstance(artist_widget, Gtk.Label) else ""
        sub = Gtk.Label(label=artist_text or "", xalign=0, ellipsize=3, css_classes=["dim-label", "track-subtitle"])
        bind_track_column(app, sub, "artist-column", invert=True)
        if has_artist:
            link_label(sub, lambda: go_artist(track))
        cell.append(sub)
    parent.insert_child_after(cell, prev)


def _same_artist(a, b):
    if a is None or b is None:
        return False
    ida, idb = getattr(a, "id", None), getattr(b, "id", None)
    if ida is not None and idb is not None:
        return str(ida) == str(idb)
    na, nb = str(getattr(a, "name", "") or "").strip(), str(getattr(b, "name", "") or "").strip()
    return bool(na) and na.casefold() == nb.casefold()


def one_artist_album(album, tracks):
    """Fork: True when every track is by the album's own artist (not a compilation, not a
    playlist), so its track rows need no artist cell."""
    artist = getattr(album, "artist", None)
    tracks = list(tracks or [])
    return bool(tracks) and all(_same_artist(getattr(t, "artist", None), artist) for t in tracks)


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


# --- Fork: the header's meta line (album / playlist): count and running time --------------

def _seconds(item):
    value = item.get("duration") if isinstance(item, dict) else getattr(item, "duration", 0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def total_seconds(owner, tracks=None):
    """The album's or playlist's own duration, else the sum of `tracks` (pass them only when
    they are all of it)."""
    own = _seconds(owner) if owner is not None else 0
    if own:
        return own
    return sum(_seconds(t) for t in tracks or ())


def runtime_text(seconds):
    """43 min, 1 hr 12 min, 2 hr; "" when unknown."""
    seconds = int(seconds or 0)
    if seconds <= 0:
        return ""
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} hr {minutes} min" if minutes else f"{hours} hr"


def count_text(count):
    count = int(count or 0)
    return "" if count <= 0 else ("1 Track" if count == 1 else f"{count} Tracks")


def meta_line(*parts):
    return "  •  ".join(p for p in parts if p)
