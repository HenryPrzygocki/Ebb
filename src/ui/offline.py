"""Fork: starting without a network no longer looks like being signed out.

Restoring the saved login asks TIDAL to confirm it. With no network (Wi-Fi still coming up
after boot, a flaky connection) the restore failed, and Ebb said "Please login to access your
TIDAL collection". Clicking that could only fail, and nothing retried once the network was
back: Ebb had to be restarted.

Now a restore that couldn't reach TIDAL (backend.restore_failure == "offline") keeps the login
and says so on the same card: "Can't reach TIDAL", with Try Again. Ebb retries by itself on a
backoff, and soon after the system reports the network back (Gio.NetworkMonitor). Only a
login TIDAL refused shows the sign-in prompt. The offline card also offers "Sign In Again", so
a failure that isn't the network can't leave you stuck.
"""
import time
from threading import Thread

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib  # noqa: E402

SIGN_IN_TITLE = "Sign in to TIDAL"
SIGN_IN_TEXT = "Your home, library and mixes appear once you're signed in."
OFFLINE_TITLE = "Can't reach TIDAL"
OFFLINE_TEXT = "You're still signed in. Ebb connects as soon as the network is back."
SIGN_IN_PAGE = "Sign in to load your personalized mixes and library picks"  # the page, above the card
OFFLINE_PAGE = "Your mixes and library load once Ebb reaches TIDAL"
BACKOFF = (5, 10, 20, 30, 60)  # seconds before each automatic retry; the last one repeats
NETWORK_BACK_DELAY = 2  # seconds: let a new connection settle (DNS, routes)
MIN_BUSY = 0.8  # seconds "Connecting…" stays up: with no network a try fails at once


def delay(attempt):
    """Seconds before automatic retry number `attempt` (from 0)."""
    return BACKOFF[min(max(0, int(attempt)), len(BACKOFF) - 1)]


def page_subtitle(app):
    """The signed-out page's subtitle (ui.views_builders.toggle_login_view): offline, the
    login is kept, so the page mustn't ask to sign in."""
    return OFFLINE_PAGE if getattr(app, "_offline", None) is not None else SIGN_IN_PAGE


def show(app, monitor=None):
    """The signed-out layout with the offline card, and retries until TIDAL answers."""
    state = getattr(app, "_offline", None)
    if state is None:
        state = app._offline = {"attempt": 0, "timer": 0, "busy": False, "kick": False,
                                "monitor": None, "handler": 0}
        monitor = monitor if monitor is not None else Gio.NetworkMonitor.get_default()
        if monitor is not None:
            state["monitor"] = monitor
            state["handler"] = monitor.connect(
                "network-changed", lambda _m, available: _network_changed(app, available))
    app._toggle_login_view(False)  # after the state exists: page_subtitle reads it
    _card(app, offline=True)
    _retry_in(app, delay(state["attempt"]))
    return False


def retry(app):
    """Try the saved login again now (Try Again, the timer, the network coming back)."""
    state = getattr(app, "_offline", None)
    if state is None or state["busy"]:
        return False
    _cancel_timer(state)
    state["busy"], state["kick"] = True, False
    _busy(app, True)
    started = time.monotonic()

    def task():
        ok = bool(app.backend.try_load_session())
        failure = getattr(app.backend, "restore_failure", None)
        if not ok:  # long enough to be seen, or a click on Try Again looks like it did nothing
            time.sleep(max(0.0, MIN_BUSY - (time.monotonic() - started)))
        GLib.idle_add(_done, app, ok, failure)

    Thread(target=task, daemon=True, name="offline-retry").start()
    return False


def sign_in_again(app, button=None):
    stop(app)
    app.on_login_clicked(button)


def stop(app):
    """Back to the plain sign-in card; no more retries."""
    state = getattr(app, "_offline", None)
    if state is None:
        return
    _cancel_timer(state)
    if state["monitor"] is not None and state["handler"]:
        state["monitor"].disconnect(state["handler"])
    app._offline = None
    _busy(app, False)
    _card(app, offline=False)


def _network_changed(app, available):
    state = getattr(app, "_offline", None)
    if state is None or not available:
        return
    if state["busy"]:
        state["kick"] = True  # the try in flight may have started before the network was up
    else:
        _retry_in(app, NETWORK_BACK_DELAY)


def _done(app, ok, failure):
    if ok:  # signed in, even if Sign In Again was clicked while this try was out
        stop(app)
        app.on_login_success()
        return False
    state = getattr(app, "_offline", None)
    if state is None:
        return False
    state["busy"] = False
    _busy(app, False)
    if failure == "offline":
        state["attempt"] += 1
        _retry_in(app, NETWORK_BACK_DELAY if state["kick"] else delay(state["attempt"]))
    else:  # TIDAL refused the saved login: it has to be signed in again
        stop(app)
        app._toggle_login_view(False)
    return False


def _retry_in(app, seconds):
    state = getattr(app, "_offline", None)
    if state is None or state["busy"]:
        return False
    _cancel_timer(state)

    def fire():
        state["timer"] = 0
        retry(app)
        return False

    state["timer"] = GLib.timeout_add_seconds(int(seconds), fire)
    return False


def _cancel_timer(state):
    if state["timer"]:
        GLib.source_remove(state["timer"])
        state["timer"] = 0


def _busy(app, busy):
    button = getattr(app, "login_retry_btn", None)
    if button is not None:
        button.set_sensitive(not busy)
        button.set_label("Connecting…" if busy else "Try Again")


def _card(app, offline):
    for name, text in (("login_prompt_title", OFFLINE_TITLE if offline else SIGN_IN_TITLE),
                       ("login_prompt_text", OFFLINE_TEXT if offline else SIGN_IN_TEXT)):
        label = getattr(app, name, None)
        if label is not None:
            label.set_text(text)
    page = getattr(app, "grid_subtitle_label", None)
    if page is not None:
        page.set_text(OFFLINE_PAGE if offline else SIGN_IN_PAGE)
    for name, visible in (("login_prompt_btn", not offline), ("login_retry_btn", offline),
                          ("login_again_btn", offline), ("login_btn", not offline)):
        widget = getattr(app, name, None)
        if widget is not None:
            widget.set_visible(visible)
