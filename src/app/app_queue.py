"""Queue-related handlers extracted from app_handlers."""

import logging
import random
from threading import Thread

from gi.repository import GLib, Gtk

from actions import up_next  # fork #25
from ui import context_menu

logger = logging.getLogger(__name__)


def _get_active_queue(self):
    q = list(getattr(self, "play_queue", []) or [])
    if q:
        return q
    return list(getattr(self, "current_track_list", []) or [])


def _get_current_track_view_tracks(self):
    playlist_id = getattr(self, "current_playlist_id", None)
    if playlist_id is not None and hasattr(self, "get_sorted_playlist_tracks"):
        try:
            tracks = list(self.get_sorted_playlist_tracks(playlist_id) or [])
        except Exception:
            tracks = []
        if tracks:
            return tracks
    return list(getattr(self, "current_track_list", []) or [])


def _set_play_queue(self, tracks):
    self._playlist_play_request = getattr(self, "_playlist_play_request", 0) + 1
    new_queue = list(tracks or [])
    current_entry = getattr(self, "_current_queue_entry", None)
    self.play_queue = new_queue
    self.shuffle_indices = []
    # A new queue invalidates the actually-played back-stack and the shuffle order. An edit of
    # the playing queue (insert, move, Play Next: the playing entry is still in it) keeps both.
    # They hold entries, not indices, so the position shift doesn't invalidate them (fork #9;
    # upstream wiped the stack on every edit).
    if current_entry is None or not any(t is current_entry for t in new_queue):
        self._play_history = []
        self._shuffle_order = None
    if hasattr(self, "_render_now_playing_queue"):
        GLib.idle_add(lambda: (self._render_now_playing_queue(self._get_active_queue()), False)[1])
    if hasattr(self, "_mpris_sync_metadata"):
        self._mpris_sync_metadata()
    if hasattr(self, "_remote_publish_queue_event"):
        self._remote_publish_queue_event("queue_set")


def _is_queue_nav_selected(self):
    row = self.nav_list.get_selected_row() if self.nav_list is not None else None
    return bool(row and getattr(row, "nav_id", None) == "queue")


def _sync_queue_handle_state(self, expanded):
    btn = getattr(self, "queue_btn", None)
    if btn is not None:
        btn.set_icon_name(
            "hiresti-queue-handle-right-symbolic" if expanded else "hiresti-queue-handle-left-symbolic"
        )
        btn.set_tooltip_text("Close Queue" if expanded else "Open Queue")
        if expanded:
            btn.add_css_class("active")
        else:
            btn.remove_css_class("active")
    anchor = getattr(self, "queue_anchor", None)
    if anchor is not None:
        if expanded:
            anchor.add_css_class("open")
        else:
            anchor.remove_css_class("open")


def toggle_queue_drawer(self, _btn=None):
    revealer = getattr(self, "queue_revealer", None)
    if revealer is None:
        return
    show = not revealer.get_reveal_child()
    revealer.set_reveal_child(show)
    if getattr(self, "queue_backdrop", None) is not None:
        self.queue_backdrop.set_visible(show)
    _sync_queue_handle_state(self, show)
    if show:
        GLib.timeout_add(120, lambda: (self.render_queue_drawer(), False)[1])


def close_queue_drawer(self):
    revealer = getattr(self, "queue_revealer", None)
    if revealer is not None:
        revealer.set_reveal_child(False)
    if getattr(self, "queue_backdrop", None) is not None:
        self.queue_backdrop.set_visible(False)
    _sync_queue_handle_state(self, False)


_MINI_QUEUE_HEIGHT = 500
_MINI_BAR_HEIGHT = 85
_MINI_WIDTH = 390
_MINI_QUEUE_HEAD = 30   # header area


def toggle_mini_queue(self, _btn=None):
    """Toggle the mini-mode queue drawer open/closed."""
    revealer = getattr(self, "mini_queue_revealer", None)
    arrow = getattr(self, "mini_queue_arrow", None)
    if revealer is None:
        return
    opening = not revealer.get_reveal_child()
    if arrow is not None:
        arrow.set_icon_name("pan-up-symbolic" if opening else "pan-down-symbolic")
    if opening:
        self.render_mini_queue()
        self.bottom_bar.add_css_class("mini-queue-open")
        revealer.set_visible(True)
        revealer.set_reveal_child(True)
        self.win.set_size_request(_MINI_WIDTH, _MINI_BAR_HEIGHT + _MINI_QUEUE_HEIGHT + _MINI_QUEUE_HEAD)
    else:
        self.bottom_bar.remove_css_class("mini-queue-open")
        revealer.set_reveal_child(False)
        revealer.set_visible(False)
        self.win.set_size_request(_MINI_WIDTH, _MINI_BAR_HEIGHT)


def close_mini_queue(self):
    """Close the mini queue drawer if open."""
    revealer = getattr(self, "mini_queue_revealer", None)
    if revealer is not None and revealer.get_reveal_child():
        if getattr(self, "bottom_bar", None) is not None:
            self.bottom_bar.remove_css_class("mini-queue-open")
        revealer.set_reveal_child(False)
        revealer.set_visible(False)
        # Reset scroll height to default so it doesn't affect main mode layout.
        scroll = getattr(self, "mini_queue_scroll", None)
        if scroll is not None:
            scroll.set_size_request(-1, _MINI_QUEUE_HEIGHT)
        self.win.set_size_request(_MINI_WIDTH, _MINI_BAR_HEIGHT)
    arrow = getattr(self, "mini_queue_arrow", None)
    if arrow is not None:
        arrow.set_icon_name("pan-down-symbolic")


def _build_mini_queue_row(app, track, i, current_idx):
    """Build a two-line queue row: title on top, artist · album below."""
    row = Gtk.ListBoxRow(css_classes=["track-row"])
    row.queue_track_index = i
    row.track_id = getattr(track, "id", None)
    up_next.mark_row(app, row, track)  # fork #25
    context_menu.tag(row, track, "track")

    box = Gtk.Box(spacing=6, margin_top=2, margin_bottom=2)

    # Index / play icon stack
    stack = Gtk.Stack()
    stack.set_size_request(16, -1)
    stack.add_css_class("track-index-stack")
    num_lbl = Gtk.Label(label=str(i + 1), css_classes=["dim-label"])
    stack.add_named(num_lbl, "num")
    play_icon = Gtk.Image(icon_name="media-playback-start-symbolic")
    play_icon.add_css_class("accent")
    stack.add_named(play_icon, "icon")
    # Default to number; _update_track_list_icon will set the play icon by track_id.
    stack.set_visible_child_name("num")
    box.append(stack)

    # Title + subtitle (artist · album)
    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1,
                   hexpand=True, valign=Gtk.Align.CENTER)
    title = getattr(track, "name", "Unknown Track")
    title_lbl = Gtk.Label(label=title, xalign=0, ellipsize=3,
                          css_classes=["track-title", "mini-queue-title"])
    title_lbl.set_tooltip_text(title)
    info.append(title_lbl)

    artist_name = getattr(getattr(track, "artist", None), "name", None) or ""
    album_name = getattr(getattr(track, "album", None), "name", None) or ""
    parts = [p for p in (artist_name, album_name) if p]
    if parts:
        sub_text = " · ".join(parts)
        sub_lbl = Gtk.Label(label=sub_text, xalign=0, ellipsize=3,
                            css_classes=["dim-label", "mini-queue-subtitle"])
        sub_lbl.set_tooltip_text(sub_text)
        info.append(sub_lbl)
    box.append(info)

    # Favorite button
    if hasattr(app, "create_track_fav_button"):
        fav_btn = app.create_track_fav_button(track)
        fav_btn.set_margin_start(2)
        fav_btn.set_margin_end(0)
        box.append(fav_btn)

    # Remove from queue button
    rm_btn = Gtk.Button(icon_name="list-remove-symbolic",
                        css_classes=["flat", "playlist-tool-btn", "queue-remove-btn"])
    rm_btn.set_tooltip_text("Remove from Queue")
    rm_btn.set_margin_start(0)
    rm_btn.set_margin_end(0)
    rm_btn.connect("clicked", lambda _b, idx=i: app.on_queue_remove_track_clicked(idx))
    box.append(rm_btn)

    row.set_child(box)
    return row


def render_mini_queue(self):
    """Populate the mini-mode queue drawer with compact track rows."""
    list_box = getattr(self, "mini_queue_list", None)
    if list_box is None:
        return
    tracks = self._get_active_queue()
    current_idx = int(getattr(self, "current_track_index", -1) or -1)

    count_lbl = getattr(self, "mini_queue_count_label", None)
    if count_lbl is not None:
        count_lbl.set_text(f"{len(tracks)} tracks")

    # Signature-based skip to avoid rebuilding unchanged queue.
    sig = (len(tracks), current_idx,
           tuple(str(getattr(t, "id", None) or f"obj:{id(t)}") for t in tracks[:200]))
    if getattr(self, "_mini_queue_sig", None) == sig and list_box.get_first_child() is not None:
        return

    # Clear existing rows.
    while True:
        child = list_box.get_first_child()
        if child is None:
            break
        list_box.remove(child)

    if not tracks:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        row.set_activatable(False)
        hint = Gtk.Label(
            label="Queue is empty.",
            xalign=0,
            css_classes=["dim-label"],
            margin_start=10, margin_end=10, margin_top=12, margin_bottom=12,
        )
        row.set_child(hint)
        list_box.append(row)
        self._mini_queue_sig = sig
        return

    # Show a window around the current track (max ~80 rows for performance).
    window_before, window_after = 20, 60
    total = len(tracks)
    anchor = max(0, min(current_idx, total - 1)) if total > 0 else 0
    start = max(0, anchor - window_before)
    end = min(total, anchor + window_after + 1)

    for i in range(start, end):
        row = _build_mini_queue_row(self, tracks[i], i, current_idx)
        list_box.append(row)

    # Scroll the current track into view after layout.
    if 0 <= current_idx < total:
        def _scroll_to_current():
            target_row = list_box.get_row_at_index(current_idx - start)
            if target_row is not None:
                target_row.grab_focus()
            return False
        GLib.timeout_add(80, _scroll_to_current)

    self._mini_queue_sig = sig
    if hasattr(self, "_update_track_list_icon"):
        self._update_track_list_icon(target_list=list_box)


def on_queue_track_selected(self, box, row):
    if not row:
        return
    idx = getattr(row, "queue_track_index", row.get_index())
    tracks = self._get_active_queue()
    if idx < 0 or idx >= len(tracks):
        return
    self.playback_source = {"type": "queue", "name": "Queue"}
    self.play_track(idx)


def _refresh_queue_views(self):
    if self._is_queue_nav_selected():
        self.render_queue_dashboard()
    if getattr(self, "queue_revealer", None) is not None and self.queue_revealer.get_reveal_child():
        self.render_queue_drawer()
    if hasattr(self, "_render_now_playing_queue"):
        self._render_now_playing_queue(self._get_active_queue())
    # Refresh the mini-mode queue drawer if it is currently open.
    rev = getattr(self, "mini_queue_revealer", None)
    if rev is not None and rev.get_reveal_child():
        self._mini_queue_sig = None  # force rebuild
        self.render_mini_queue()


def _play_tracks_now(self, tracks):
    queue = [track for track in list(tracks or []) if track is not None]
    if not queue:
        return {"queue_size": 0, "autoplay": False, "start_index": -1}
    self.current_track_list = list(queue)
    if hasattr(self, "_set_play_queue"):
        self._set_play_queue(queue)
    else:
        self.play_queue = list(queue)
    self.play_track(0)
    return {"queue_size": len(queue), "autoplay": True, "start_index": 0}


def _insert_queue_at(self, tracks, index, event_reason="queue_inserted"):
    additions = [track for track in list(tracks or []) if track is not None]
    base_queue = list(self._get_active_queue() if hasattr(self, "_get_active_queue") else [])
    insert_index = max(0, min(int(index), len(base_queue)))
    try:
        current_index = int(getattr(self, "current_track_index", -1))
    except Exception:
        current_index = -1
    original_current = current_index

    if not additions:
        return {
            "queue_size": len(base_queue),
            "insert_index": insert_index,
            "inserted": 0,
            "current_index": current_index,
        }

    new_queue = base_queue[:insert_index] + additions + base_queue[insert_index:]
    if current_index >= insert_index:
        current_index += len(additions)

    self._remote_queue_event_suppression = int(getattr(self, "_remote_queue_event_suppression", 0) or 0) + 1
    try:
        if hasattr(self, "_set_play_queue"):
            self._set_play_queue(new_queue)
        else:
            self.play_queue = list(new_queue)
    finally:
        self._remote_queue_event_suppression = max(
            0,
            int(getattr(self, "_remote_queue_event_suppression", 1) or 1) - 1,
        )

    self.current_track_index = current_index if 0 <= current_index < len(new_queue) else -1
    if 0 <= self.current_track_index < len(new_queue):
        self.playing_track = new_queue[self.current_track_index]
        self.playing_track_id = getattr(self.playing_track, "id", None)

    from actions.playback_actions import shuffle_order_add
    shuffle_order_add(self, additions, play_next=insert_index == original_current + 1)

    if hasattr(self, "_refresh_queue_views"):
        GLib.idle_add(self._refresh_queue_views)
    if hasattr(self, "_mpris_sync_metadata"):
        self._mpris_sync_metadata()
    if hasattr(self, "_remote_publish_queue_event"):
        self._remote_publish_queue_event(str(event_reason or "queue_inserted"))

    return {
        "queue_size": len(new_queue),
        "insert_index": insert_index,
        "inserted": len(additions),
        "current_index": self.current_track_index,
    }


def _insert_queue_next(self, tracks):
    try:
        current_index = int(getattr(self, "current_track_index", -1))
    except Exception:
        current_index = -1
    base_queue = list(self._get_active_queue() if hasattr(self, "_get_active_queue") else [])
    insert_index = current_index + 1 if 0 <= current_index < len(base_queue) else 0
    return _insert_queue_at(self, tracks, insert_index)


def _show_play_next_notice(self, tracks, played_now=False):
    notice = getattr(self, "show_output_notice", None)
    if not callable(notice):
        return
    items = [track for track in list(tracks or []) if track is not None]
    if not items:
        return
    count = len(items)
    if count == 1:
        title = str(getattr(items[0], "name", "Unknown Track") or "Unknown Track")
        text = f"Playing now: {title}" if played_now else f"Queued next: {title}"
    else:
        text = f"Playing {count} tracks now" if played_now else f"Added {count} tracks to play next"
    notice(text, "ok", 2400)


def play_tracks_next(self, tracks):
    """Insert `tracks` after the current track, or start them if nothing is playing."""
    items = [track for track in list(tracks or []) if track is not None]
    if not items:
        return
    if getattr(self, "playing_track", None) is None:
        _play_tracks_now(self, items)
        _show_play_next_notice(self, items, played_now=True)
        return
    up_next.add(self, items, front=True)  # fork #25: before earlier queued tracks
    _show_play_next_notice(self, items, played_now=False)


def add_tracks_to_queue(self, tracks):
    """Append `tracks` to the queue, or start them if nothing is playing."""
    items = [track for track in list(tracks or []) if track is not None]
    if not items:
        return
    if getattr(self, "playing_track", None) is None:
        _play_tracks_now(self, items)
        _show_add_to_queue_notice(self, items, played_now=True)
        return
    # Fork #25: after the current track and earlier queued tracks, not after the whole list.
    up_next.add(self, items)
    _show_add_to_queue_notice(self, items, played_now=False)


def play_tracks_now(self, tracks, shuffle=False, source=None):
    """Replace the queue with `tracks` and play them (context-menu Play/Shuffle).

    Unlike _play_tracks_now, this leaves current_track_list (the list on screen) alone.
    """
    items = [track for track in list(tracks or []) if track is not None]
    if not items:
        return False
    if shuffle:
        random.shuffle(items)
    if source is not None:
        self.playback_source = source
    if hasattr(self, "_set_play_queue"):
        self._set_play_queue(items)
    else:
        self.play_queue = list(items)
    self.play_track(0)
    return True


def on_play_next_track_clicked(self, track):
    if track is None:
        return
    play_tracks_next(self, [track])


def on_add_track_to_queue_clicked(self, track):
    if track is None:
        return
    add_tracks_to_queue(self, [track])


def _notify_track_radio_unavailable(self, track_name):
    notice = getattr(self, "show_output_notice", None)
    if callable(notice):
        notice(f"Track radio not available for {track_name}", "warn", 3200)


def on_go_to_track_radio_clicked(self, track):
    if track is None:
        return
    track_name = str(getattr(track, "name", "Track") or "Track")
    notice = getattr(self, "show_output_notice", None)
    if callable(notice):
        notice("Loading track radio…", "info", 2200)

    def task():
        mix = None
        try:
            mix = self.backend.get_track_radio_mix(track)
        except Exception:
            logger.exception("Failed to load track radio for %s", getattr(track, "id", "unknown"))
        if mix is None:
            GLib.idle_add(_notify_track_radio_unavailable, self, track_name)
            return
        GLib.idle_add(self.show_album_details, mix)

    Thread(target=task, daemon=True).start()


def _show_add_to_queue_notice(self, tracks, played_now=False):
    notice = getattr(self, "show_output_notice", None)
    if not callable(notice):
        return
    items = [track for track in list(tracks or []) if track is not None]
    if not items:
        return
    count = len(items)
    if count == 1:
        title = str(getattr(items[0], "name", "Unknown Track") or "Unknown Track")
        text = f"Playing now: {title}" if played_now else f"Added to queue: {title}"
    else:
        text = f"Playing {count} tracks now" if played_now else f"Added {count} tracks to queue"
    notice(text, "ok", 2400)


def on_play_next_current_tracks_clicked(self, _btn=None):
    play_tracks_next(self, _get_current_track_view_tracks(self))


def on_add_current_tracks_to_queue_clicked(self, _btn=None):
    add_tracks_to_queue(self, _get_current_track_view_tracks(self))


def on_queue_remove_track_clicked(self, track_index):
    tracks = self._get_active_queue()
    idx = int(track_index)
    if idx < 0 or idx >= len(tracks):
        return
    removed_current = idx == int(getattr(self, "current_track_index", -1))
    up_next.forget(self, tracks.pop(idx))  # fork #25: else settle() would put it back
    self.play_queue = tracks

    if not tracks:
        self.current_track_index = -1
        self.playing_track = None
        self.playing_track_id = None
        try:
            self.player.stop()
        except Exception:
            pass
        if self.play_btn is not None:
            self.play_btn.set_icon_name("media-playback-start-symbolic")
        self.refresh_current_track_favorite_state()
        if hasattr(self, "_mpris_sync_all"):
            self._mpris_sync_all(force=True)
        if hasattr(self, "_remote_publish_queue_event"):
            self._remote_publish_queue_event("queue_removed")
        if hasattr(self, "_remote_publish_playback_event"):
            self._remote_publish_playback_event("queue_cleared")
        GLib.idle_add(self._refresh_queue_views)
        return

    if idx < self.current_track_index:
        self.current_track_index = max(0, self.current_track_index - 1)

    if removed_current:
        new_idx = min(idx, len(tracks) - 1)
        if hasattr(self, "_mpris_sync_metadata"):
            self._mpris_sync_metadata()
        if hasattr(self, "_remote_publish_queue_event"):
            self._remote_publish_queue_event("queue_removed")
        GLib.idle_add(self._refresh_queue_views)
        GLib.idle_add(lambda: self.play_track(new_idx) or False)
        return

    GLib.idle_add(self._refresh_queue_views)
    self._update_track_list_icon()
    if hasattr(self, "_mpris_sync_metadata"):
        self._mpris_sync_metadata()
    if hasattr(self, "_remote_publish_queue_event"):
        self._remote_publish_queue_event("queue_removed")


def on_queue_clear_clicked(self, _btn=None):
    self._playlist_play_request = getattr(self, "_playlist_play_request", 0) + 1
    self._play_request_id = getattr(self, "_play_request_id", 0) + 1
    tracks = self._get_active_queue()
    if not tracks:
        return
    self.play_queue = []
    up_next.clear(self)  # fork #25
    self.current_track_index = -1
    self.playing_track = None
    self.playing_track_id = None
    try:
        self.player.stop()
    except Exception:
        pass
    if self.play_btn is not None:
        self.play_btn.set_icon_name("media-playback-start-symbolic")
    self.refresh_current_track_favorite_state()
    if hasattr(self, "_mpris_sync_all"):
        self._mpris_sync_all(force=True)
    if hasattr(self, "_remote_publish_queue_event"):
        self._remote_publish_queue_event("queue_cleared")
    if hasattr(self, "_remote_publish_playback_event"):
        self._remote_publish_playback_event("queue_cleared")
    GLib.idle_add(self._refresh_queue_views)
