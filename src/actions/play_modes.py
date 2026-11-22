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
"""
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


def set_mode(app, mode, announce=True):
    """Make `mode` the play mode: shuffle order, buttons, setting and (with `announce`) MPRIS.

    Turning Shuffle on draws a new order; changing only Repeat keeps the order, so the track
    lined up next (and handed to the engine for gapless playback) stays the same."""
    mode = normalize(mode)
    was_shuffled = shuffle_on(app)
    app.play_mode = mode
    shuffled = split(mode)[0]
    if shuffled and not was_shuffled:
        generate = getattr(app, "_generate_shuffle_list", None)
        if callable(generate):
            generate()
    elif not shuffled:
        app.shuffle_indices = []
        app._shuffle_order = None
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
