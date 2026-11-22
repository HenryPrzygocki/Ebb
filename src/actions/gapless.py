"""Fork: gapless playback, the app's half. The engine's half is native_transport/gapless.rs.

Upstream played every track change the same way:
  1. the track ran out;
  2. the engine reported EOS;
  3. the app loaded the next track.
Closing and reopening the output in between left an audible gap, which breaks albums meant
to play as one piece.

Now:
1. About 20 s before a track ends, the engine sends `about-to-finish`.
2. The app answers with the track Next would play: Up Next first, then the queue under the
   current play mode. It resolves that track's stream as play_track() does, using the prefetch
   cache when the cached URL is still fresh, and hands it over with player.queue_next().
3. Until the track ends, the app re-checks what should follow every WATCH_MS. If the queue or
   the play mode changed, it hands the engine the new track instead, or clears it. It polls
   because what follows can change from many places (the UI, MPRIS, remote control, Up Next,
   a playlist refresh), and the window lasts only about 20 s per track.
4. The engine opens the stream ahead. At the end of the current track it keeps decoding into
   the same output, so no silence is added between the two.
5. When the engine moves on (`gapless-advance`), play_track(engine_advanced=True) does a track
   change's bookkeeping (UI, queue position, history, scrobbling, MPRIS) without loading
   anything.
6. If the engine moved on to a track that should no longer follow (a change too close to the
   end to re-queue), the app loads the right one the usual way.

These cases end the track as before, with a reload:
- repeat-one;
- the end of the queue;
- a next track in another format (the engine checks).

HIRESTI_DISABLE_GAPLESS=1 turns gapless playback off.
"""
import logging
import os
import time
from threading import Thread

from gi.repository import GLib

logger = logging.getLogger(__name__)

WATCH_MS = 400  # how often, near the end of a track, the app re-checks what follows it
# The re-checks stop this long after the last about-to-finish (a long pause). Resuming
# restarts the decoder, which sends about-to-finish again and so restarts them.
WATCH_LIMIT_S = 120.0


def _now():
    return time.monotonic()


def enabled(app):
    if os.environ.get("HIRESTI_DISABLE_GAPLESS", "").strip().lower() not in ("", "0", "false", "off"):
        return False
    if os.environ.get("HIRESTI_LOCAL_URI", "").strip():  # a debugging override plays one file
        return False
    supports = getattr(getattr(app, "player", None), "supports_gapless", None)
    return bool(callable(supports) and supports())


def _same(a, b):
    return str(a or "").strip() == str(b or "").strip()


def _same_track(a, b):
    """Whether two queue entries play the same audio (a refreshed queue has new objects)."""
    if a is None or b is None:
        return False
    if a is b:
        return True
    a_id = getattr(a, "id", None)
    return a_id is not None and a_id == getattr(b, "id", None)


def _queue(app):
    if hasattr(app, "_get_active_queue"):
        return list(app._get_active_queue() or [])
    return list(getattr(app, "current_track_list", None) or [])


def expected_next(app):
    """(index, queue entry) of the track that plays when this one ends, or (-1, None)."""
    if getattr(app, "play_mode", None) == getattr(app, "MODE_ONE", 1):
        return -1, None  # repeat-one restarts the track: a reload, as before
    queue = _queue(app)
    get_next = getattr(app, "get_next_index", None)
    idx = get_next(direction=1) if callable(get_next) else -1
    current = getattr(app, "current_track_index", -1)
    if not isinstance(idx, int) or idx < 0 or idx >= len(queue) or idx == current:
        return -1, None
    return idx, queue[idx]


def disarm(app):
    """Forget the handed-over track and stop re-checking (a track change voids both; the
    engine drops its queued track on load)."""
    app._gapless_armed = None
    app._gapless_due = None
    app._gapless_resolving = None


def on_about_to_finish(app, uri):
    """The engine reaches the end of `uri` soon: until the track changes, keep the engine's
    next track the one Next would play. Main loop."""
    try:
        player = getattr(app, "player", None)
        if not enabled(app) or not _same(uri, getattr(player, "_last_loaded_uri", "")):
            return False  # off, or an event from a track that is no longer loaded
        request_id = getattr(app, "_play_request_id", 0)
        app._gapless_due = request_id
        app._gapless_due_until = _now() + WATCH_LIMIT_S
        sync(app)
        if getattr(app, "_gapless_watching", None) != request_id:
            app._gapless_watching = request_id
            GLib.timeout_add(WATCH_MS, _watch, app, request_id)
    except Exception:
        logger.debug("Gapless: about-to-finish handling failed", exc_info=True)
    return False


def _watch(app, request_id):
    keep = False
    try:
        keep = (request_id == getattr(app, "_play_request_id", 0)
                and _now() < float(getattr(app, "_gapless_due_until", 0.0) or 0.0)
                and sync(app))
    except Exception:
        logger.debug("Gapless: re-checking the next track failed", exc_info=True)
    if not keep and getattr(app, "_gapless_watching", None) == request_id:
        app._gapless_watching = None
    return keep


def sync(app):
    """Main loop: make the engine's next track the one Next would play now. Hand it over, or
    replace or clear one handed over before the queue or play mode changed. Returns False
    once there is nothing more to keep in sync (another track started, or gapless is off)."""
    request_id = getattr(app, "_play_request_id", 0)
    if getattr(app, "_gapless_due", None) != request_id or not enabled(app):
        return False
    _idx, entry = expected_next(app)
    armed = getattr(app, "_gapless_armed", None)
    if armed and armed.get("request_id") == request_id:
        if _same_track(armed.get("entry"), entry):
            armed["entry"] = entry  # the current object, for the advance's bookkeeping
            return True
        app._gapless_armed = None
        app.player.queue_next(None)  # the engine must not continue into it
        logger.info("Gapless: what follows changed; replacing the engine's next track")
    if entry is not None and not _same_track(getattr(app, "_gapless_resolving", None), entry):
        app._gapless_resolving = entry
        Thread(target=_resolve_and_hand_over, args=(app, request_id, entry), daemon=True).start()
    return True


def resolve_stream(app, entry):
    """The stream URL for a queue entry, resolved as play_track() resolves it. None if none."""
    from actions import lyrics_playback_actions as playback

    track = entry
    if isinstance(track, playback.PlaylistQueueTrack):
        track = track.resolve()
        if hasattr(app, "_refresh_queue_views"):
            GLib.idle_add(app._refresh_queue_views)
    track_id = getattr(track, "id", None)
    if track_id is None:
        return None
    quality_key = str(getattr(app.backend, "quality", "unknown"))
    cached = (getattr(app, "stream_prefetch_cache", None) or {}).get(track_id)
    if cached and cached.get("quality") == quality_key and cached.get("url"):
        age = time.monotonic() - float(cached.get("fetched_at", 0) or 0)
        if age < playback.PREFETCH_URL_TTL_SECONDS:
            return cached.get("url")
    url = app.backend.get_stream_url(track)
    playback._apply_track_redirect(app, track)
    return url or None


def _resolve_and_hand_over(app, request_id, entry):
    try:
        url = resolve_stream(app, entry)
    except Exception as e:  # not retried for this track: _gapless_resolving stays on it
        logger.info("Gapless: could not resolve the next track (%s); it will load when this one ends", e)
        return
    if url:
        GLib.idle_add(_hand_over, app, request_id, entry, url)


def _hand_over(app, request_id, entry, url):
    """Main loop: queue the resolved track in the engine, if it is still the one to follow."""
    if request_id != getattr(app, "_play_request_id", 0) or getattr(app, "_gapless_due", None) != request_id:
        return False  # another track started meanwhile
    expected = expected_next(app)[1]
    if not _same_track(expected, entry):
        if getattr(app, "_gapless_resolving", None) is entry:
            app._gapless_resolving = None  # resolved again if it comes back
        return False  # what follows changed while the stream resolved; the re-check takes over
    rc = app.player.queue_next(url)
    if rc == 0:
        app._gapless_resolving = None
        app._gapless_armed = {"uri": url, "entry": expected, "request_id": request_id}
        logger.info("Gapless: '%s' will follow without a gap", getattr(expected, "name", "?"))
    else:  # not retried for this track: _gapless_resolving stays on it
        logger.info("Gapless: the engine declined the next track (rc=%s)", rc)
    return False


def on_gapless_advance(app, uri):
    """Main loop: the engine moved on to the handed-over track. Do the track change's
    bookkeeping without touching the engine, unless something else should play now."""
    armed = getattr(app, "_gapless_armed", None)
    app._gapless_armed = None
    app._gapless_due = None  # the track it was for has ended
    try:
        idx, expected = expected_next(app)
        current_request = getattr(app, "_play_request_id", 0)
        if (armed is None or not _same(armed.get("uri"), uri) or armed.get("request_id") != current_request
                or not _same_track(expected, armed.get("entry"))):
            logger.info("Gapless: the engine moved on to a track that no longer follows; loading the right one")
            app.on_next_track(auto=True)
            return False
        from actions import playback_actions, up_next

        if up_next.peek(app) is expected and playback_actions._shuffle_like(app):
            # As on_next_track() does for a queued track under shuffle: build the order now, so
            # the queued track is crossed off it as it starts.
            playback_actions._shuffle_order(
                app, playback_actions._active_queue(app), getattr(app, "current_track_index", -1))
        app.play_track(idx, engine_advanced=True)
    except Exception:
        logger.exception("Gapless: track change bookkeeping failed")
    return False
