"""Fork: Shuffle and Repeat are two separate controls.

Upstream had one button that cycled through five modes: Normal (stop at the end), Loop All,
Loop One, Shuffle and Smart Shuffle. Its custom icons did not say which mode was on or what the
next click would do ("Normal" looked like Undo, "Smart" like a dark-mode moon). Shuffle could not
be combined with a repeat choice. Smart Shuffle ran exactly the code Shuffle ran.

Now the transport row has a Shuffle toggle left of Previous and a Repeat button right of Next
(Off, All, One), as in TIDAL and most players. They use the icon theme's standard
media-playlist-* icons, light up in the accent colour when on, and MPRIS's Shuffle and
LoopStatus map onto them one to one.

The pair is still one integer, app.play_mode (the "play_mode" setting; MPRIS and remote control
read it too). Two values are new, so that every pair has one:

                  Repeat off              Repeat all     Repeat one
    Shuffle off   NORMAL (4)              LOOP (0)       ONE (1)
    Shuffle on    SHUFFLE_NO_REPEAT (5)   SHUFFLE (2)    SHUFFLE_REPEAT_ONE (6)

SMART (3) reads as SHUFFLE.

Shuffle with Repeat off plays every queued track once in random order, then stops.
Repeat One repeats the track when it ends; Next still moves on (in shuffled order when Shuffle
is on).

Shuffle reorders the queue itself, as TIDAL and Spotify do: the tracks already heard, the
playing one, Up Next, then the rest in random order. Next walks the queue in order, so the queue
views show what plays next, and a track dragged there moves in the play order. Turning Shuffle
off puts back the order the queue had, and play goes on from the playing track. A page's
Shuffle button (album, playlist, Liked Songs, Uploads, a menu's Shuffle) turns Shuffle on and
starts on a random track. A new queue while Shuffle is on is shuffled around the first track
that plays, and each pass under Repeat gets a new order.

Upstream's page Shuffle shuffled a copy of the list and left the mode off, so the toggle said
Off and could not bring the order back, and its Shuffle mode picked tracks at random while the
queue views showed list order. That random walk (actions/playback_actions.py, fork #9) is still
the fallback for a queue that isn't in shuffled order.
"""
import random

from core.constants import PlayMode

REPEAT_OFF, REPEAT_ALL, REPEAT_ONE = "off", "all", "one"
REPEATS = (REPEAT_OFF, REPEAT_ALL, REPEAT_ONE)

_PAIR = {
    PlayMode.NORMAL: (False, REPEAT_OFF),
    PlayMode.LOOP: (False, REPEAT_ALL),
    PlayMode.ONE: (False, REPEAT_ONE),
    PlayMode.SHUFFLE: (True, REPEAT_ALL),
    PlayMode.SMART: (True, REPEAT_ALL),
    PlayMode.SHUFFLE_NO_REPEAT: (True, REPEAT_OFF),
    PlayMode.SHUFFLE_REPEAT_ONE: (True, REPEAT_ONE),
}
_MODE = {pair: mode for mode, pair in _PAIR.items() if mode != PlayMode.SMART}

SHUFFLE_ICON = "media-playlist-shuffle-symbolic"
REPEAT_ICON = {
    REPEAT_OFF: "media-playlist-repeat-symbolic",
    REPEAT_ALL: "media-playlist-repeat-symbolic",
    REPEAT_ONE: "media-playlist-repeat-song-symbolic",  # Papirus draws a "1", Adwaita a dot
}
_REPEAT_TIP = {
    REPEAT_OFF: "Repeat: Off",
    REPEAT_ALL: "Repeat: All",
    REPEAT_ONE: "Repeat: One",
}
SHUFFLE_KEYS, REPEAT_KEYS = "Ctrl+S", "Ctrl+R"
# Every Shuffle and Repeat button, by app attribute: the player bar's and Now Playing's.
SHUFFLE_BUTTONS = ("shuffle_btn", "now_playing_shuffle_btn")
REPEAT_BUTTONS = ("repeat_btn", "now_playing_repeat_btn")


def normalize(mode):
    """A valid play mode for `mode` (an int, or anything else from a settings file)."""
    try:
        mode = int(mode)
    except (TypeError, ValueError):
        return PlayMode.NORMAL
    if mode == PlayMode.SMART:
        return PlayMode.SHUFFLE
    return mode if mode in _PAIR else PlayMode.NORMAL


def split(mode):
    """(shuffle on, repeat) for a play mode."""
    return _PAIR[normalize(mode)]


def join(shuffle, repeat):
    """The play mode for a (shuffle on, repeat) pair."""
    return _MODE[(bool(shuffle), repeat if repeat in REPEATS else REPEAT_OFF)]


def shuffle_on(app):
    return split(getattr(app, "play_mode", PlayMode.NORMAL))[0]


def repeat(app):
    return split(getattr(app, "play_mode", PlayMode.NORMAL))[1]


def set_mode(app, mode, announce=True, reorder=True):
    """Make `mode` the play mode: queue order, buttons, setting and (with `announce`) MPRIS.

    Turning Shuffle on shuffles the queue around the playing track; with `reorder` False (a
    page's Shuffle, about to start a new queue) that waits until a track starts. Turning it off
    restores the order. Changing only Repeat leaves the queue alone, so the track lined up next
    (and handed to the engine for gapless playback) stays the same."""
    mode = normalize(mode)
    was_shuffled = shuffle_on(app)
    app.play_mode = mode
    shuffled = split(mode)[0]
    if shuffled and not was_shuffled:
        generate = getattr(app, "_generate_shuffle_list", None)
        if callable(generate):
            generate()
        if reorder and not preshuffled(app):
            preshuffle(app)
    elif not shuffled:
        app.shuffle_indices = []
        app._shuffle_order = None
        if was_shuffled:
            unshuffle(app)
    sync_buttons(app)
    settings = getattr(app, "settings", None)
    if isinstance(settings, dict):
        settings["play_mode"] = mode
        save = getattr(app, "schedule_save_settings", None)
        if callable(save):
            save()
    sync = getattr(app, "_mpris_sync_metadata", None)
    if announce and callable(sync):
        sync()
    return mode


def turn_shuffle_on(app):
    """Shuffle on, for a new queue about to start: it is shuffled once its first track does."""
    shuffled, rep = split(getattr(app, "play_mode", PlayMode.NORMAL))
    if not shuffled:
        set_mode(app, join(True, rep), reorder=False)


def shuffled_start(app, count):
    """For a page's or a menu's Shuffle: Shuffle on, and which of the `count` tracks to start on.

    The caller sets the queue in list order and plays that track; the queue is shuffled around
    it as it starts, and turning Shuffle off brings the list order back."""
    turn_shuffle_on(app)
    app._unshuffled_order = None  # shuffled afresh, even if it's the queue that is playing
    return random.randrange(count) if count > 0 else 0


# The shuffled queue ---------------------------------------------------------------------------


def preshuffled(app):
    """True when the queue is in shuffled play order, so Next walks it in order."""
    if getattr(app, "_unshuffled_order", None) is not None:
        return True
    from actions.playlist_playback import uses_shuffled_playlist_order

    return uses_shuffled_playlist_order(app)


def _index(app):
    try:
        return int(getattr(app, "current_track_index", -1))
    except (TypeError, ValueError):
        return -1


def _current(app, queue):
    """The playing entry of `queue`, or None (a queue set but not started yet)."""
    entry = getattr(app, "_current_queue_entry", None)
    if entry is not None:
        return entry if any(e is entry for e in queue) else None
    index = _index(app)
    return queue[index] if 0 <= index < len(queue) else None


def preshuffle(app, fresh=False):
    """Shuffle the queue itself: the tracks already heard, the playing one, Up Next, then the
    rest in random order. `fresh`: a new pass, so none of the others count as heard.

    Needs a playing entry: a queue that hasn't started is shuffled when its first track does."""
    queue = list(getattr(app, "play_queue", None) or [])
    current = _current(app, queue) if queue else None
    if current is None:
        return False
    from actions import up_next

    ids = {id(e) for e in queue}
    taken = {id(current)}
    pend = []
    for e in up_next.pending(app):
        if id(e) in ids and id(e) not in taken:
            pend.append(e)
            taken.add(id(e))
    heard = []
    if not fresh:
        for e in reversed(list(getattr(app, "_play_history", None) or [])):
            if id(e) in ids and id(e) not in taken:
                heard.append(e)
                taken.add(id(e))
        heard.reverse()
    rest = [e for e in queue if id(e) not in taken]
    random.shuffle(rest)
    if getattr(app, "_unshuffled_order", None) is None:
        app._unshuffled_order = _original_order(queue)
    _put(app, heard + [current] + pend + rest, current)
    return True


def unshuffle(app):
    """Shuffle off: put back the order the queue had. Play goes on from the playing track; tracks
    queued meanwhile keep their place in the play order (Up Next right after the playing track,
    the ones already heard before it)."""
    original = getattr(app, "_unshuffled_order", None)
    app._unshuffled_order = None
    if original is None:
        _restore_playlist_order(app)
        _unmark_playlists(app)
        return False
    queue = list(getattr(app, "play_queue", None) or [])
    if not queue:
        return False
    from actions import up_next

    current = _current(app, queue)
    ids = {id(e) for e in queue}
    pend = [e for e in up_next.pending(app) if id(e) in ids and e is not current]
    skip = {id(e) for e in pend}
    if current is not None:
        skip.add(id(current))
    place = {id(e): i for i, e in enumerate(original)}
    base = [e for e in original if id(e) in ids and id(e) not in skip]
    extras = [e for e in queue if id(e) not in place and id(e) not in skip]
    if current is None:
        new = pend + base + extras
    else:
        at = _slot(app, base, place, current)
        new = base[:at] + extras + [current] + pend + base[at:]
    _unmark_playlists(app)
    _put(app, new, current)
    return True


def _slot(app, base, place, current):
    """Where the playing track goes among `base` (in the original order): its own place, or, for
    a track queued while shuffled, right after the last track heard that has one."""
    mark = place.get(id(current))
    if mark is None:
        in_base = {id(e) for e in base}
        for e in reversed(list(getattr(app, "_play_history", None) or [])):
            if id(e) in in_base:
                mark = place[id(e)] + 0.5
                break
    if mark is None:
        return 0
    return sum(1 for e in base if place[id(e)] < mark)


def track_started(app, changed=True):
    """play_track calls this once the new track is current, before Up Next settles. Under
    Shuffle, a queue not in shuffled order yet (a new one) is shuffled around the track, and a
    shuffled queue that Repeat took round to its start is shuffled again for the new pass.
    `changed`: another track than before (not Repeat One playing the same one again)."""
    if shuffle_on(app) and (not preshuffled(app) or (changed and _wrapped(app))):
        preshuffle(app, fresh=True)


def _wrapped(app):
    """The first track of a shuffled queue started right after its last one: Repeat went round."""
    if repeat(app) == REPEAT_OFF or _index(app) != 0:
        return False
    queue = list(getattr(app, "play_queue", None) or [])
    history = getattr(app, "_play_history", None) or []
    return len(queue) > 2 and bool(history) and history[-1] is queue[-1]


def new_pass(app):
    """A shuffled queue ran out under Repeat off: shuffle it again, so Play or Next after the
    stop starts a new pass."""
    if shuffle_on(app) and preshuffled(app):
        preshuffle(app, fresh=True)


def queue_replaced(app, old, new):
    """_set_play_queue calls this. An edit (tracks inserted or removed, the others still in the
    order they were) keeps the shuffled order and the order to go back to. Anything else is a
    new queue, which Shuffle reorders when its first track starts."""
    if not _is_edit(app, old, new):
        app._unshuffled_order = None


def _is_edit(app, old, new):
    """The tracks `new` shares with `old` keep their order, and it still holds the playing track
    or only lost tracks. The album played again in album order is not an edit of its shuffled
    queue; an unrelated list has no playing track in it."""
    pos = {id(e): i for i, e in enumerate(old)}
    shared = [pos[id(e)] for e in new if id(e) in pos]
    if not shared or any(b < a for a, b in zip(shared, shared[1:])):
        return False
    current = getattr(app, "_current_queue_entry", None)
    return len(shared) == len(new) or (current is not None and any(e is current for e in new))


def _original_order(queue):
    """The order to go back to: the queue as it is, or for a playlist that started shuffled
    (actions/playlist_playback.py) the playlist's own order."""
    try:
        from models.playlist_queue import PlaylistQueueTrack
    except Exception:
        return list(queue)
    first = next((e for e in queue if isinstance(e, PlaylistQueueTrack)), None)
    if first is None or not getattr(first.source, "shuffled", False):
        return list(queue)
    return sorted(
        (e for e in queue if isinstance(e, PlaylistQueueTrack) and e.source is first.source),
        key=lambda e: e.position,
    )


def _unmark_playlists(app):
    """A playlist that started shuffled is in its own order now: Shuffle on again reorders it
    like any queue (uses_shuffled_playlist_order would keep it in place)."""
    try:
        from models.playlist_queue import PlaylistQueueTrack
    except Exception:
        return
    for e in list(getattr(app, "play_queue", None) or []):
        if isinstance(e, PlaylistQueueTrack) and getattr(e.source, "shuffled", False):
            e.source.shuffled = False


def _put(app, new, current):
    app.play_queue = new
    if current is not None:
        app.current_track_index = next(i for i, e in enumerate(new) if e is current)
    app._shuffle_order = None
    app.shuffle_indices = []
    _hydrate(app, new)
    refresh = getattr(app, "_refresh_queue_views", None)
    if callable(refresh):
        try:
            from gi.repository import GLib

            GLib.idle_add(lambda: (refresh(), False)[1])
        except Exception:
            refresh()
    sync = getattr(app, "_mpris_sync_metadata", None)
    if callable(sync):
        sync()
    publish = getattr(app, "_remote_publish_queue_event", None)
    if callable(publish):
        publish("queue_moved")


def _hydrate(app, queue):
    """Fill in titles for the playlist entries now coming up (they load page by page)."""
    try:
        from actions.playlist_playback import hydrate_queue_metadata
        from models.playlist_queue import PlaylistQueueTrack
    except Exception:
        return
    if not queue or not all(isinstance(e, PlaylistQueueTrack) for e in queue):
        return
    if any(e.source is not queue[0].source for e in queue):
        return
    try:
        hydrate_queue_metadata(app, queue, max(0, _index(app)))
    except Exception:
        pass


def _restore_playlist_order(app):
    """Shuffle turned off on a playlist started with its Shuffle button: that queue is a shuffled
    copy of the playlist (actions/playlist_playback.py), so put it back in playlist order and
    go on from the playing track. Left alone if anything else was queued into it."""
    try:
        from models.playlist_queue import PlaylistQueueTrack
    except Exception:
        return
    queue = getattr(app, "play_queue", None)
    if not queue or not all(isinstance(e, PlaylistQueueTrack) for e in queue):
        return
    source = queue[0].source
    if not getattr(source, "shuffled", False) or any(e.source is not source for e in queue):
        return
    try:
        current = int(getattr(app, "current_track_index", -1))
    except (TypeError, ValueError):
        current = -1
    playing = queue[current] if 0 <= current < len(queue) else None
    queue.sort(key=lambda e: e.position)
    source.shuffled = False
    if playing is not None:
        app.current_track_index = next(i for i, e in enumerate(queue) if e is playing)
    try:
        from actions.playlist_playback import hydrate_queue_metadata

        hydrate_queue_metadata(app, queue, max(0, app.current_track_index))
    except Exception:
        pass
    refresh = getattr(app, "_refresh_queue_views", None)
    if callable(refresh):
        refresh()


def toggle_shuffle(app, *_args, notify=False):
    shuffled, rep = split(getattr(app, "play_mode", PlayMode.NORMAL))
    set_mode(app, join(not shuffled, rep))
    if notify:
        _notice(app, "Shuffle on" if not shuffled else "Shuffle off")


def cycle_repeat(app, *_args, notify=False):
    """Off, then All, then One, then Off."""
    shuffled, rep = split(getattr(app, "play_mode", PlayMode.NORMAL))
    rep = REPEATS[(REPEATS.index(rep) + 1) % len(REPEATS)]
    set_mode(app, join(shuffled, rep))
    if notify:
        _notice(app, {REPEAT_OFF: "Repeat off", REPEAT_ALL: "Repeating the queue",
                      REPEAT_ONE: "Repeating this track"}[rep])


def _notice(app, text):
    show = getattr(app, "show_output_notice", None)
    if callable(show):
        show(text, "info", 1600)


def _set_on(button, on):
    if on:
        button.add_css_class("on")
    else:
        button.remove_css_class("on")


def _show_shuffle(button, shuffled):
    _set_on(button, shuffled)
    button.set_tooltip_text(f"Shuffle: {'On' if shuffled else 'Off'} ({SHUFFLE_KEYS})")


def _show_repeat(button, rep):
    _set_on(button, rep != REPEAT_OFF)
    if button.get_icon_name() != REPEAT_ICON[rep]:
        button.set_icon_name(REPEAT_ICON[rep])
    button.set_tooltip_text(f"{_REPEAT_TIP[rep]} ({REPEAT_KEYS})")


def sync_buttons(app):
    """Show the current mode on every Shuffle and Repeat button."""
    shuffled, rep = split(getattr(app, "play_mode", PlayMode.NORMAL))
    for name in SHUFFLE_BUTTONS:
        button = getattr(app, name, None)
        if button is not None:
            _show_shuffle(button, shuffled)
    for name in REPEAT_BUTTONS:
        button = getattr(app, name, None)
        if button is not None:
            _show_repeat(button, rep)


def buttons(app, css_class="transport-mode-btn"):
    """A new (Shuffle, Repeat) button pair for a transport row, showing the current mode."""
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    shuffle = Gtk.Button(icon_name=SHUFFLE_ICON, css_classes=["flat", "circular", css_class], valign=Gtk.Align.CENTER)
    shuffle.connect("clicked", lambda _b: toggle_shuffle(app))
    rep = Gtk.Button(icon_name=REPEAT_ICON[REPEAT_OFF], css_classes=["flat", "circular", css_class], valign=Gtk.Align.CENTER)
    rep.connect("clicked", lambda _b: cycle_repeat(app))
    shuffled, mode_repeat = split(getattr(app, "play_mode", PlayMode.NORMAL))
    _show_shuffle(shuffle, shuffled)
    _show_repeat(rep, mode_repeat)
    return shuffle, rep
