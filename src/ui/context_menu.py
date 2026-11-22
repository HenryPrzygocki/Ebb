"""Right-click menus for TIDAL items: tracks, albums, artists, playlists, mixes (fork #7).

Upstream's only right-click menu was a window-wide "Share… / Close" that copied the
upstream repository URL.

How it works:
- Widgets that show an item are tagged with it: ``tag(row, track, "track")``. FlowBox grid
  children that carry ``data_item = {"obj": ..., "type": ...}`` count as tagged too.
- One capture-phase secondary-click gesture on the window (``ui.builders``) picks the widget
  under the pointer. ``resolve()`` then finds the nearest tagged ancestor.
- ``actions_for()`` turns the item into ``(label, callback)`` rows, with ``None`` as a
  separator. ``popup()`` shows those rows at the pointer.
- A click that resolves to nothing is not claimed, so entries and labels keep GTK's own menus.

Everything except ``build_popover()`` and ``popup()`` is GTK-free, so it can be tested headless.
"""

import logging
from threading import Thread

from gi.repository import Gdk, GLib, Gtk

logger = logging.getLogger(__name__)

TIDAL_BROWSE = "https://tidal.com/browse"
KINDS = ("track", "video", "album", "artist", "playlist", "mix")
_KIND_ALIASES = {"userplaylist": "playlist", "mixv2": "mix"}
_CTX_ATTR = "_hiresti_ctx"
ROW_REMOVE_ATTR = "_hiresti_remove"  # fork: set on a track row that shows a trash button


# ---------------------------------------------------------------- items

def kind_of(obj, hint=None):
    """One of KINDS for `obj`: from its (tidalapi) class name first, then the caller's hint."""
    if obj is None:
        return None
    for name in (type(obj).__name__, hint):
        key = str(name or "").strip().lower()
        key = _KIND_ALIASES.get(key, key)
        if key in KINDS:
            return key
    return None


def item_id(obj):
    if obj is None:
        return None
    if isinstance(obj, dict):
        val = obj.get("id") or obj.get("uuid")
    else:
        val = getattr(obj, "id", None) or getattr(obj, "uuid", None)
    text = str(val).strip() if val is not None else ""
    return text or None


def tidal_url(kind, obj):
    """Public TIDAL link, the same form as tidalapi's ``share_url``; None if there is none."""
    oid = item_id(obj) if kind in KINDS else None
    return f"{TIDAL_BROWSE}/{kind}/{oid}" if oid else None


def tag(widget, obj, kind=None):
    """Mark `widget` as showing `obj`, or a zero-argument callable that returns the item."""
    if widget is not None:
        try:
            setattr(widget, _CTX_ATTR, (kind, obj))
        except Exception:
            logger.debug("context_menu.tag failed on %r", widget, exc_info=True)
    return widget


def _tagged_item(widget):
    ctx = getattr(widget, _CTX_ATTR, None)
    if ctx is not None:
        hint, obj = ctx
        if callable(obj):
            try:
                obj = obj()
            except Exception:
                obj = None
        return hint, obj
    data = getattr(widget, "data_item", None)
    if isinstance(data, dict) and "obj" in data:
        return data.get("type"), data.get("obj")
    return None


def resolve(widget):
    """(kind, obj) of the nearest tagged ancestor of `widget` (itself included), else None.

    The nearest tag wins even when its item is unusable (nothing playing, a page link without
    an id). An outer card must never claim a click that landed on an inner item.
    """
    cur = widget
    while cur is not None:
        found = _tagged_item(cur)
        if found is not None:
            hint, obj = found
            # Lazily-loaded playlist queue entries carry the real track once resolved.
            obj = getattr(obj, "resolved_track", None) or obj
            kind = kind_of(obj, hint)
            return (kind, obj) if kind and item_id(obj) else None
        try:
            cur = cur.get_parent()
        except Exception:
            return None
    return None


# ---------------------------------------------------------------- actions

def _notice(app, text, level="ok", ms=2200):
    fn = getattr(app, "show_output_notice", None)
    if callable(fn):
        try:
            fn(text, level, ms)
        except Exception:
            logger.debug("show_output_notice failed", exc_info=True)


def _method(app, name):
    fn = getattr(app, name, None)
    return fn if callable(fn) else None


def copy_text(app, text):
    display = None
    win = getattr(app, "win", None)
    if win is not None:
        try:
            display = win.get_display()
        except Exception:
            display = None
    if display is None:
        display = Gdk.Display.get_default()
    if display is None:
        logger.warning("Cannot copy to the clipboard: no display.")
        return False
    try:
        display.get_clipboard().set(text)
        return True
    except Exception as e:
        logger.warning("Clipboard copy failed: %s", e)
        return False


def copy_link(app, kind, obj):
    url = tidal_url(kind, obj)
    ok = bool(url) and copy_text(app, url)
    if ok:
        logger.info("Copied TIDAL link %s", url)
        _notice(app, f"{link_noun(kind)} link copied", "ok", 1800)
    else:
        _notice(app, "Couldn't copy the link", "warn", 2600)
    return ok


def _with_tracks(app, obj, then):
    """Fetch `obj`'s tracks off the GTK thread, then pass them to `then` on it."""
    backend = getattr(app, "backend", None)
    if backend is None or not hasattr(backend, "get_tracks"):
        return
    _notice(app, "Loading tracks…", "info", 1600)

    def finish(tracks):
        if tracks:
            then(tracks)
        else:
            _notice(app, "No playable tracks found", "warn", 2600)
        return False

    def task():
        try:
            tracks = list(backend.get_tracks(obj) or [])
        except Exception:
            logger.exception("Context menu: loading tracks for %s failed", item_id(obj))
            tracks = []
        GLib.idle_add(finish, tracks)

    Thread(target=task, daemon=True, name="ctx-menu-tracks").start()


def _favorite_row(app, track):
    setter = _method(app, "set_track_favorite")
    backend = getattr(app, "backend", None)
    tid = item_id(track)
    if setter is None or tid is None or not getattr(backend, "user", None):
        return None
    try:
        is_fav = bool(backend.is_track_favorite(tid))
    except Exception:
        return None
    want = not is_fav

    def done(ok):
        if ok:
            _notice(app, "Added to Favorites" if want else "Removed from Favorites", "ok", 1800)
        else:
            _notice(app, "Couldn't update Favorites", "warn", 2600)

    label = "Remove from Favorites" if is_fav else "Add to Favorites"
    return (label, lambda: setter(track, want, on_done=done))


def _track_rows(app, track):
    rows = []

    def add(label, name, *args, when=True):
        fn = _method(app, name)
        if fn is not None and when:
            rows.append((label, lambda: fn(*args)))

    add("Play Next", "on_play_next_track_clicked", track)
    add("Add to Queue", "on_add_track_to_queue_clicked", track)
    add("Add to Playlist…", "on_add_single_track_to_playlist", track)
    fav = _favorite_row(app, track)
    if fav is not None:
        rows.append(fav)
    rows.append(None)
    add("Go to Album", "go_to_album_of", track, when=item_id(getattr(track, "album", None)) is not None)
    add("Go to Artist", "go_to_artist_of", track, when=getattr(track, "artist", None) is not None)
    add("Go to Track Radio", "on_go_to_track_radio_clicked", track)
    return rows


def _collection_rows(app, kind, obj):
    """Album, playlist or mix: the tracks are fetched only when an action runs."""
    rows = []
    name = str(getattr(obj, "name", None) or getattr(obj, "title", None) or kind.title())
    source = {"type": kind, "name": name, "obj": obj}
    if kind == "playlist":
        source["playlist_id"] = item_id(obj)
    play_now = _method(app, "play_tracks_now")
    if play_now is not None:
        rows.append(("Play", lambda: _with_tracks(app, obj, lambda ts: play_now(ts, source=source))))
        rows.append(("Shuffle", lambda: _with_tracks(app, obj, lambda ts: play_now(ts, shuffle=True, source=source))))
    for label, meth in (("Play Next", "play_tracks_next"), ("Add to Queue", "add_tracks_to_queue")):
        fn = _method(app, meth)
        if fn is not None:
            rows.append((label, lambda fn=fn: _with_tracks(app, obj, fn)))
    go_artist = _method(app, "go_to_artist_of")
    if kind == "album" and go_artist is not None and getattr(obj, "artist", None) is not None:
        rows += [None, ("Go to Artist", lambda: go_artist(obj))]
    return rows


def _tidy(rows):
    """Drop leading, doubled and trailing separators."""
    out = []
    for row in rows:
        if row is None and (not out or out[-1] is None):
            continue
        out.append(row)
    while out and out[-1] is None:
        out.pop()
    return out


def removal_action(widget):
    """Fork: the "remove from this playlist" callback a row's builder left on the row, if any.

    Rows get one exactly where they show a trash button (your own TIDAL playlist; a local
    playlist in edit mode), so the menu never offers removal anywhere else.
    """
    cur = widget
    while cur is not None:
        fn = getattr(cur, ROW_REMOVE_ATTR, None)
        if callable(fn):
            return fn
        if isinstance(cur, Gtk.ListBoxRow):
            return None
        try:
            cur = cur.get_parent()
        except Exception:
            return None
    return None


# Fork #24: favorites from any menu, not only from the open page's heart. Playlists have no
# favorite call in the backend yet.
_FAVORITES = {
    "album": ("is_favorite", "toggle_album_favorite", "Add to Favorites", "Remove from Favorites"),
    "mix": ("is_mix_favorite", "toggle_mix_favorite", "Add to Favorites", "Remove from Favorites"),
    "artist": ("is_artist_favorite", "toggle_artist_favorite", "Follow", "Unfollow"),
}


def _collection_favorite_row(app, kind, obj):
    spec = _FAVORITES.get(kind)
    backend = getattr(app, "backend", None)
    oid = item_id(obj)
    if spec is None or backend is None or oid is None:
        return None
    is_fav, toggle = getattr(backend, spec[0], None), getattr(backend, spec[1], None)
    if not (callable(is_fav) and callable(toggle)):
        return None
    try:
        active = bool(is_fav(oid))
    except Exception:
        return None
    raw_id = getattr(obj, "id", None) or oid  # what the page's own heart passes to the backend
    return (spec[3] if active else spec[2], lambda: _set_favorite(app, kind, obj, raw_id, toggle, not active))


def favorite_notice(kind, name, add):
    if kind == "artist":
        return f"Following {name}" if add else f"Unfollowed {name}"
    return f"Added \u201c{name}\u201d to Favorites" if add else f"Removed \u201c{name}\u201d from Favorites"


def _set_favorite(app, kind, obj, oid, toggle, add):
    name = str(getattr(obj, "name", None) or getattr(obj, "title", None) or kind.title())

    def finish(ok):
        if ok:
            _notice(app, favorite_notice(kind, name, add), "ok", 2400)
            sync_open_page_heart(app, kind, oid, add)
        else:
            _notice(app, "TIDAL didn't accept that change. Try again.", "error", 2800)
        return False

    def task():
        try:
            ok = bool(toggle(oid, add))
        except Exception:
            logger.exception("Context menu: favorite toggle failed for %s %s", kind, oid)
            ok = False
        GLib.idle_add(finish, ok)

    Thread(target=task, daemon=True, name="ctx-menu-favorite").start()


def sync_open_page_heart(app, kind, oid, add):
    """The open album or artist page's heart follows a change made from a menu."""
    update = _method(app, "_update_fav_icon")
    if update is None:
        return
    if kind == "artist":
        shown, btn = getattr(app, "current_selected_artist", None), getattr(app, "_artist_hero_fav_btn", None)
    else:
        shown, btn = getattr(app, "current_album", None), getattr(app, "fav_btn", None)
    if btn is not None and shown is not None and str(item_id(shown)) == str(oid):
        update(btn, add)


def _artist_rows(app, obj):
    """An artist's radio, from any artist card or row."""
    play_now = _method(app, "play_tracks_now")
    if play_now is None or not callable(getattr(obj, "get_radio", None)):
        return []
    name = str(getattr(obj, "name", None) or "this artist")

    def start():
        _notice(app, "Loading radio\u2026", "info", 1600)

        def finish(tracks):
            if tracks:
                # "Playing from artist radio · <name>"; clicking it opens the artist.
                play_now(tracks, source={"type": "artist radio", "name": name, "obj": obj})
            else:
                _notice(app, f"TIDAL has no radio for {name}", "warn", 2600)
            return False

        def task():
            try:
                tracks = list(obj.get_radio() or [])
            except Exception:
                logger.exception("Context menu: artist radio failed for %s", item_id(obj))
                tracks = []
            GLib.idle_add(finish, tracks)

        Thread(target=task, daemon=True, name="ctx-menu-radio").start()

    return [("Play Artist Radio", start)]


def link_noun(kind):
    """Fork: what a copied link points at ("Copy Album Link"), not whose link it is."""
    return {"track": "Track", "video": "Video", "album": "Album", "artist": "Artist",
            "playlist": "Playlist", "mix": "Mix"}.get(kind, "TIDAL")


def actions_for(app, kind, obj, origin=None):
    """Menu rows for one item: ``(label, callback)`` tuples, with ``None`` as a separator.

    origin: the widget the menu is for (clicked or focused), so row-specific entries can appear.
    """
    if obj is None or kind not in KINDS:
        return []
    if kind == "track":
        rows = _track_rows(app, obj)
    elif kind in ("album", "playlist", "mix"):
        rows = _collection_rows(app, kind, obj)
    elif kind == "artist":
        rows = _artist_rows(app, obj)  # fork #24
    else:  # video: left-click already opens it.
        rows = []
    favorite = _collection_favorite_row(app, kind, obj)  # fork #24
    if favorite is not None:
        rows += [None, favorite]
    if tidal_url(kind, obj):
        rows += [None, (f"Copy {link_noun(kind)} Link", lambda: copy_link(app, kind, obj))]
    remove = removal_action(origin) if kind == "track" else None
    if remove is not None:  # destructive, so last
        rows += [None, ("Remove from This Playlist", remove)]
    return _tidy(rows)


# ---------------------------------------------------------------- GTK

def build_popover(rows):
    pop = Gtk.Popover()
    pop.add_css_class("track-row-overflow-popover")
    pop.set_has_arrow(False)
    pop.set_halign(Gtk.Align.START)
    pop.set_position(Gtk.PositionType.BOTTOM)
    box = Gtk.ListBox(css_classes=["track-row-overflow-menu"])
    box.set_selection_mode(Gtk.SelectionMode.NONE)
    for entry in rows:
        if entry is None:
            sep = Gtk.ListBoxRow(activatable=False, selectable=False)
            sep.set_child(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_top=3, margin_bottom=3))
            box.append(sep)
            continue
        label, callback = entry
        row = Gtk.ListBoxRow(css_classes=["track-row-overflow-item"])
        row.set_child(Gtk.Label(
            label=label, xalign=0.0, halign=Gtk.Align.START,
            margin_top=8, margin_bottom=8, margin_start=14, margin_end=14,
        ))
        row._ctx_callback = callback
        box.append(row)

    def on_activated(_box, row):
        callback = getattr(row, "_ctx_callback", None)
        pop.popdown()
        if callback is not None:
            try:
                callback()
            except Exception:
                logger.exception("Context menu action failed")

    box.connect("row-activated", on_activated)
    pop.set_child(box)
    return pop


def _unparent(pop):
    try:
        if pop.get_parent() is not None:
            pop.unparent()
    except Exception:
        pass
    return False


def close(app):
    pop = getattr(app, "_context_popover", None)
    if pop is not None:
        try:
            pop.popdown()
        except Exception:
            pass


def popup(app, parent, x, y, rows, on_closed=None):
    """Show `rows` as a menu at (x, y), given in `parent`'s coordinates."""
    close(app)
    pop = build_popover(rows)
    pop.set_parent(parent)
    rect = Gdk.Rectangle()
    rect.x, rect.y, rect.width, rect.height = int(x), int(y), 1, 1
    pop.set_pointing_to(rect)

    def on_pop_closed(p):
        if getattr(app, "_context_popover", None) is p:
            app._context_popover = None
        if on_closed is not None:
            try:
                on_closed()
            except Exception:
                logger.debug("context menu on_closed failed", exc_info=True)
        GLib.idle_add(_unparent, p)

    pop.connect("closed", on_pop_closed)
    app._context_popover = pop
    pop.popup()
    return pop


def _tagged_widget(widget):
    cur = widget
    while cur is not None:
        if _tagged_item(cur) is not None:
            return cur
        cur = cur.get_parent()
    return None


def open_for_focus(app):
    """Fork #24: Menu key / Shift+F10 opens the focused row's or card's menu, anchored on it."""
    win = getattr(app, "win", None)
    focus = win.get_focus() if win is not None else None
    item = resolve(focus) if focus is not None else None
    rows = actions_for(app, *item, origin=focus) if item else []
    if not rows:
        return False
    anchor = _tagged_widget(focus) or focus
    gesture = getattr(app, "_context_menu_gesture", None)
    parent = gesture.get_widget() if gesture is not None else None
    parent = parent or win
    from gi.repository import Graphene

    ok, pt = anchor.compute_point(parent, Graphene.Point().init(24.0, max(0.0, anchor.get_height() - 6.0)))
    if not ok:
        return False

    def _refocus():
        if focus.get_mapped():
            focus.grab_focus()

    popup(app, parent, pt.x, pt.y, rows, on_closed=lambda: GLib.idle_add(lambda: (_refocus(), False)[1]))
    return True
