"""Fork #25: an "Up Next" queue, as in TIDAL, Spotify and Apple Music.

Upstream's Add to Queue appended to the end of the play queue: a queued track came after the
whole 500-track playlist, or at a random point under shuffle. Now:

- Play Next and Add to Queue put tracks in ``app.up_next``, a FIFO of queue entries, and into
  the play queue right after the playing track. Play Next goes before earlier queued tracks;
  Add to Queue goes after them.
- ``settle()`` runs whenever a track starts. The pending block moves, in order, to right after
  the new current track (after a jump elsewhere, or Previous), and is put back if a new album
  or playlist replaced the queue. An entry leaves Up Next once it starts playing, so the
  back-stack and Previous see what actually played.
- Next and the end of a track play Up Next first in every mode. Repeat-one repeats the track
  until Next is pressed. Prefetch looks at the same track.
- Entries are shallow copies: the same object twice in the queue would confuse the
  identity-based back-stack and shuffle order (fork #9), and "Play this next" on a track of
  the playing album is the common case.
"""
import copy
import logging

from gi.repository import GLib

logger = logging.getLogger(__name__)

ROW_TOOLTIP = "Up Next: plays after the current track"


def pending(app):
    return list(getattr(app, "up_next", None) or [])


def is_pending(app, entry):
    return any(e is entry for e in pending(app))


def _queue(app):
    if hasattr(app, "_get_active_queue"):
        return list(app._get_active_queue() or [])
    return list(getattr(app, "play_queue", None) or [])


def _index_of(queue, entry):
    for i, item in enumerate(queue):
        if item is entry:
            return i
    return -1


def _current_entry(app, queue):
    try:
        cur = int(getattr(app, "current_track_index", -1))
    except (TypeError, ValueError):
        cur = -1
    return queue[cur] if 0 <= cur < len(queue) else None


def _publish(app):
    if hasattr(app, "_refresh_queue_views"):
        GLib.idle_add(app._refresh_queue_views)
    if hasattr(app, "_mpris_sync_metadata"):
        app._mpris_sync_metadata()
    if hasattr(app, "_remote_publish_queue_event"):
        app._remote_publish_queue_event("queue_inserted")


def settle(app):
    """Keep the pending entries, in order, right after the current track. True if the queue changed."""
    queue = _queue(app)
    current = _current_entry(app, queue)
    up = pending(app)
    if current is not None and any(current is e for e in up):
        up = [e for e in up if e is not current]  # it is playing now
        app.up_next = up
    if not up:
        return False
    ids = {id(e) for e in up}
    rest = [e for e in queue if id(e) not in ids]
    at = _index_of(rest, current) + 1 if current is not None else 0
    new_queue = rest[:at] + up + rest[at:]
    if len(new_queue) == len(queue) and all(a is b for a, b in zip(new_queue, queue)):
        return False
    # Not _set_play_queue(): it bumps the play request, which cancels a playlist still loading.
    app.play_queue = new_queue
    if current is not None:
        app.current_track_index = _index_of(new_queue, current)
    _publish(app)
    return True


def add(app, tracks, front=False):
    """Queue `tracks` to play after the current track (front: before earlier queued tracks)."""
    entries = [copy.copy(t) for t in (tracks or []) if t is not None]
    if not entries:
        return []
    up = pending(app)
    app.up_next = entries + up if front else up + entries
    if not settle(app):
        _publish(app)
    return entries


def forget(app, entry):
    """Drop `entry` from Up Next (it was removed from the queue)."""
    up = pending(app)
    if any(e is entry for e in up):
        app.up_next = [e for e in up if e is not entry]


def clear(app):
    app.up_next = []


def peek(app):
    """The track that plays next because it was queued, or None."""
    up = pending(app)
    return up[0] if up else None


def next_index(app):
    """Queue index of the next queued track, placed right after the current one; -1 if none."""
    if not pending(app):
        return -1
    settle(app)
    up = pending(app)
    return _index_of(_queue(app), up[0]) if up else -1


def mark_row(app, row, track):
    """Style a queue row whose entry is waiting in Up Next. True if it is."""
    if row is None or not is_pending(app, track):
        return False
    row.add_css_class("queue-up-next")  # an accent edge where the list's row style allows it
    set_tooltip = getattr(row, "set_tooltip_text", None)
    if callable(set_tooltip):
        set_tooltip(ROW_TOOLTIP)
    return True
