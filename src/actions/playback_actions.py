import math
import os
import random
import time

from actions import audio_settings_actions

_PREV_RESTART_THRESHOLD_S = 3.0
_PREV_DOUBLE_TAP_WINDOW_S = 2.0


def _stop_after_queue_end(app):
    player = getattr(app, "player", None)
    if player is not None and hasattr(player, "stop"):
        try:
            player.stop()
        except Exception:
            pass
    play_btn = getattr(app, "play_btn", None)
    if play_btn is not None and hasattr(play_btn, "set_icon_name"):
        try:
            play_btn.set_icon_name("media-playback-start-symbolic")
        except Exception:
            pass
    if hasattr(app, "_sync_playback_status_icon"):
        try:
            app._sync_playback_status_icon()
        except Exception:
            pass
    if hasattr(app, "_mpris_sync_playback"):
        app._mpris_sync_playback()
    if hasattr(app, "_mpris_sync_position"):
        app._mpris_sync_position(force=True)
    if hasattr(app, "_remote_publish_playback_event"):
        app._remote_publish_playback_event("stopped")


_MAX_PLAY_HISTORY = 500


def _active_queue(app):
    if hasattr(app, "_get_active_queue"):
        return app._get_active_queue()
    return list(getattr(app, "current_track_list", []) or [])


def _index_of(queue, entry):
    """Position of `entry` in `queue` by identity: queue entries are the objects themselves."""
    for i, item in enumerate(queue):
        if item is entry:
            return i
    return -1


def _shuffle_like(app):
    from actions import play_modes

    return play_modes.shuffle_on(app)


def _shuffle_order(app, queue, current):
    """Remaining shuffle play order as queue entries, next first; built on demand.

    Fork #9: upstream drew random.choice() over every other index on each call, i.e. with
    replacement. Tracks repeated, Play Next was ignored under shuffle, and the gapless prefetch
    drew a different track than Next then played.
    """
    order = getattr(app, "_shuffle_order", None)
    if order is None:
        gen = getattr(app, "_generate_shuffle_list", None)
        if callable(gen):
            gen()
            src = list(getattr(app, "shuffle_indices", None) or [])
        else:
            src = list(range(len(queue)))
            random.shuffle(src)
        order = [queue[i] for i in src if isinstance(i, int) and 0 <= i < len(queue) and i != current]
        app._shuffle_order = order
    return order


def _choose_shuffle_index(app, current, total, wrap=True):
    """Next index under shuffle. Stable until that track starts, so prefetch and Next agree.

    `wrap`: once every track has had its turn, start a new shuffled pass (Repeat All or One);
    otherwise -1 (Repeat off: the end)."""
    from actions.playlist_playback import uses_shuffled_playlist_order
    if uses_shuffled_playlist_order(app):
        if current + 1 < total:
            return current + 1
        return 0 if wrap else -1
    queue = _active_queue(app)
    current_entry = queue[current] if 0 <= current < len(queue) else None
    for _cycle in range(2 if wrap else 1):
        order = _shuffle_order(app, queue, current)
        while order:
            idx = _index_of(queue, order[0])
            if idx >= 0 and order[0] is not current_entry:
                return idx
            del order[0]  # removed from the queue meanwhile, or it's the current track
        if not wrap:
            return -1  # every track had its turn; on_next_track stops and resets the order
        app._shuffle_order = None  # every track had its turn: start a new cycle
    fallback = [idx for idx in range(total) if idx != current]
    return random.choice(fallback) if fallback else current


def record_track_change(app, queue, entry, from_history=False):
    """Bookkeeping when `entry` (a queue item) starts playing.

    Pushes the entry being left onto the Previous back-stack, unless this is a Previous step or
    that entry is no longer queued, and drops the new entry from the remaining shuffle order.
    The stack holds entries rather than indices, so Play Next, Add to Queue, moves and
    removals don't make Previous land on a neighbour (fork #9).
    """
    prev_entry = getattr(app, "_current_queue_entry", None)
    if (not from_history and prev_entry is not None and prev_entry is not entry
            and _index_of(queue, prev_entry) >= 0):
        history = getattr(app, "_play_history", None)
        if history is None:
            history = app._play_history = []
        history.append(prev_entry)
        if len(history) > _MAX_PLAY_HISTORY:
            del history[:-_MAX_PLAY_HISTORY]
    app._current_queue_entry = entry
    order = getattr(app, "_shuffle_order", None)
    if order:
        order[:] = [e for e in order if e is not entry]


def shuffle_order_add(app, entries, play_next):
    """Fold newly queued entries into the shuffle order.

    Play Next puts them first in line; anything else goes to random positions.
    """
    entries = [e for e in (entries or []) if e is not None]
    if not entries or not _shuffle_like(app):
        return
    from actions.playlist_playback import uses_shuffled_playlist_order
    if uses_shuffled_playlist_order(app):
        return  # that queue already plays in queue order
    queue = _active_queue(app)
    current = getattr(app, "current_track_index", -1)
    order = _shuffle_order(app, queue, current if isinstance(current, int) else -1)
    added = {id(e) for e in entries}
    order[:] = [e for e in order if id(e) not in added]
    if play_next:
        order[0:0] = entries
    else:
        for e in entries:
            order.insert(random.randint(0, len(order)), e)


def on_play_pause(app, btn):
    from actions.playlist_playback import cancel_pending_playlist
    cancel_pending_playlist(app)
    if app.player.is_playing():
        app.player.pause()
        if btn is not None:
            btn.set_icon_name("media-playback-start-symbolic")
        if hasattr(app, "_mpris_sync_playback"):
            app._mpris_sync_playback()
        if hasattr(app, "_mpris_sync_position"):
            app._mpris_sync_position(force=True)
        if hasattr(app, "_remote_publish_playback_event"):
            app._remote_publish_playback_event("paused")
    else:
        local_override = os.environ.get("HIRESTI_LOCAL_URI", "").strip()
        if local_override:
            if not local_override.startswith("file://"):
                local_override = "file://" + os.path.abspath(os.path.expanduser(local_override))
            current_uri = str(getattr(app.player, "_last_loaded_uri", "") or "")
            if current_uri != local_override:
                app.player.load(local_override)
        app.player.play()
        audio_settings_actions.update_output_status_ui(app)
        state = str(getattr(app.player, "output_state", "idle") or "idle")
        err = str(getattr(app.player, "output_error", "") or "").strip()
        blocked = bool(getattr(app.player, "_pipewire_rate_blocked", False))
        if blocked or state == "error":
            if btn is not None:
                btn.set_icon_name("media-playback-start-symbolic")
            msg = err or "Audio output error."
            if hasattr(app, "show_output_notice"):
                app.show_output_notice(f"Output error: {msg}", "error", 4200)
            if blocked and hasattr(app, "_show_simple_dialog"):
                app._show_simple_dialog("Playback blocked", msg)
            if hasattr(app, "_mpris_sync_playback"):
                app._mpris_sync_playback()
            if hasattr(app, "_mpris_sync_position"):
                app._mpris_sync_position(force=True)
            if hasattr(app, "_remote_publish_playback_event"):
                app._remote_publish_playback_event("playback_error")
            return
        if btn is not None:
            btn.set_icon_name("media-playback-pause-symbolic")
        if hasattr(app, "_mpris_sync_playback"):
            app._mpris_sync_playback()
        if hasattr(app, "_mpris_sync_position"):
            app._mpris_sync_position(force=True)
        if hasattr(app, "_remote_publish_playback_event"):
            app._remote_publish_playback_event("resumed")


def on_next_track(app, btn=None, auto=False):
    """Play the next track. `auto`: the previous one ended (only then does repeat-one repeat)."""
    queue = app._get_active_queue() if hasattr(app, "_get_active_queue") else list(getattr(app, "current_track_list", []) or [])
    if not queue:
        return

    total = len(queue)
    if total == 0:
        return

    current = getattr(app, "current_track_index", 0)
    if current is None:
        current = 0

    next_idx = -1

    from actions import play_modes  # fork: Shuffle and Repeat are separate controls

    repeat = play_modes.repeat(app)
    shuffled = play_modes.shuffle_on(app)

    # Fork #25: queued tracks play first in every mode; repeat-one repeats until Next is pressed.
    if not (repeat == play_modes.REPEAT_ONE and auto):
        from actions import up_next
        queued = up_next.next_index(app)
        if queued >= 0:
            if _shuffle_like(app):
                # Build the shuffle order now, so the queued track is crossed off it as it starts.
                # Built later, it would include the track and play it a second time this cycle.
                _shuffle_order(app, _active_queue(app), getattr(app, "current_track_index", -1))
            app.play_track(queued)
            return

    if repeat == play_modes.REPEAT_ONE and auto:
        # Fork: only the end of a track repeats it. Every Next button, Ctrl+Right and MPRIS call
        # this without `btn`, so upstream's "btn is None" test made Next restart the track.
        next_idx = current
    elif shuffled:
        if total <= 1:
            next_idx = 0 if repeat != play_modes.REPEAT_OFF else -1
        else:
            next_idx = _choose_shuffle_index(app, current, total, wrap=repeat != play_modes.REPEAT_OFF)
    elif repeat == play_modes.REPEAT_OFF:
        if current + 1 < total:
            next_idx = current + 1
    else:  # Repeat All, or Next pressed under Repeat One
        next_idx = (current + 1) % total

    if 0 <= next_idx < total:
        app.play_track(next_idx)
    elif repeat == play_modes.REPEAT_OFF:
        if shuffled:
            app._shuffle_order = None  # every track had its turn: the next play starts a new pass
        _stop_after_queue_end(app)


def _restart_current(app, player, now, current, arm=True):
    player.seek(0.0)
    if arm:
        app._prev_track_rewind_armed_until = now + _PREV_DOUBLE_TAP_WINDOW_S
        app._prev_track_rewind_armed_index = current
    if hasattr(app, "_mpris_emit_seeked"):
        app._mpris_emit_seeked(0.0)
    if hasattr(app, "_mpris_sync_position"):
        app._mpris_sync_position(force=True)
    if hasattr(app, "_remote_publish_playback_event"):
        app._remote_publish_playback_event("seek")


def on_prev_track(app, btn=None):
    queue = _active_queue(app)
    if not queue:
        return

    total = len(queue)
    current = getattr(app, "current_track_index", 0)
    if current is None:
        current = 0

    now = time.monotonic()
    rewind_armed_until = float(getattr(app, "_prev_track_rewind_armed_until", 0.0) or 0.0)
    rewind_armed_index = getattr(app, "_prev_track_rewind_armed_index", None)
    rewind_to_start_armed = rewind_armed_index == current and now <= rewind_armed_until

    player = getattr(app, "player", None)
    can_seek = player is not None and hasattr(player, "get_position") and hasattr(player, "seek")
    if can_seek:
        try:
            pos_s, _dur_s = player.get_position()
            pos_s = float(pos_s or 0.0)
        except Exception:
            pos_s = None
        # Standard player behaviour, as upstream #50 asked: a few seconds in, Previous restarts
        # the track, and near its start it steps back. Upstream implemented it inverted. The arm
        # lets a quick second press step back even while the reported position still lags the seek.
        if (pos_s is not None and math.isfinite(pos_s) and pos_s > _PREV_RESTART_THRESHOLD_S
                and not rewind_to_start_armed):
            _restart_current(app, player, now, current)
            return

    app._prev_track_rewind_armed_until = 0.0
    app._prev_track_rewind_armed_index = None

    shuffle_like = _shuffle_like(app)
    if shuffle_like:
        # Shuffle play order isn't queue order: walk the back-stack of entries actually heard.
        history = getattr(app, "_play_history", None)
        current_entry = queue[current] if 0 <= current < total else None
        while history:
            target = history.pop()
            idx = _index_of(queue, target)
            if idx >= 0 and target is not current_entry:
                order = getattr(app, "_shuffle_order", None)
                if order is not None and current_entry is not None:
                    order.insert(0, current_entry)  # so Next comes back to the track we left
                app.play_track(idx, from_history=True)
                return

    from actions import play_modes

    at_start = shuffle_like or (play_modes.repeat(app) == play_modes.REPEAT_OFF and current == 0)
    if at_start and can_seek:
        # Nothing to step back to: restart rather than jump to an arbitrary or wrapped track.
        _restart_current(app, player, now, current, arm=False)
        return

    prev_idx = (current - 1) % total
    if 0 <= prev_idx < total:
        app.play_track(prev_idx)


def get_next_index(app, direction=1):
    queue = app._get_active_queue() if hasattr(app, "_get_active_queue") else list(getattr(app, "current_track_list", []) or [])
    if not queue:
        return -1

    total = len(queue)
    if total == 0:
        return -1

    current = getattr(app, "current_track_index", 0)
    if current is None or current < 0 or current >= total:
        current = 0

    from actions import play_modes  # fork: Shuffle and Repeat are separate controls

    repeat = play_modes.repeat(app)
    if repeat == play_modes.REPEAT_ONE:
        return current

    if direction == 1:  # fork #25: a queued track plays next (read-only: no settle here)
        from actions import up_next
        queued = up_next.peek(app)
        if queued is not None:
            for i, entry in enumerate(queue):
                if entry is queued:
                    return i

    if play_modes.shuffle_on(app):
        if direction == 1:
            # Use the same selection logic as on_next_track so that prefetch
            # actually predicts the track that will be played next.
            return _choose_shuffle_index(app, current, total, wrap=repeat != play_modes.REPEAT_OFF)
        return (current - 1) % total

    if repeat == play_modes.REPEAT_OFF:
        if direction == 1:
            return current + 1 if (current + 1) < total else -1
        return current - 1 if current > 0 else -1

    return (current + direction) % total
