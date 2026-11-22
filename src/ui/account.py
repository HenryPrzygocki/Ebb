"""Fork: the TIDAL account UI.

- HiFi (PKCE) sign-in happens in the user's own browser. TIDAL's bot wall blocks the embedded
  WebKit view ("You have been blocked"), and RFC 8252 recommends the system browser for native
  apps anyway: it passes TIDAL's checks, may already be signed in, and the app never sees the
  password. TIDAL's redirect target is fixed (tidal.com/android/login/auth), so the code comes
  back through the clipboard: Ebb reads it when its window is active again, or it is pasted.
- "Lossless is off" is explained, not nagged about: the banner is about quality (not about
  signing in), shows only while lossless is requested, and its explainer has Don't Show Again.
  The account menu keeps the way back.
- The account menu says who is signed in and what quality that login gets.
"""
import logging
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from core import brand
from core.executor import submit_daemon

logger = logging.getLogger(__name__)

DISMISS_KEY = "lossless_banner_dismissed"
_URL_CHARS = r"[^\s\"'<>]"
_REDIRECT_RE = re.compile(
    rf"(?<![\w.-])(?:https?://)?(?:www\.)?tidal\.com/android/login/auth\?{_URL_CHARS}*?\bcode=[^&\s\"'<>]+{_URL_CHARS}*"
)


def find_redirect_url(text):
    """The TIDAL sign-in redirect address in copied or pasted text (normalised to https), else None."""
    match = _REDIRECT_RE.search(str(text or ""))
    if not match:
        return None
    url = match.group(0)
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    elif not url.startswith("https://"):
        url = "https://" + url
    return url


def login_limits_lossless(app):
    check = getattr(getattr(app, "backend", None), "login_limits_lossless", None)
    return bool(callable(check) and check())


def lossless_requested(app):
    """Same test as the tech label's AAC warning: LOSSLESS or HI_RES_LOSSLESS is selected."""
    return "LOSSLESS" in str(getattr(getattr(app, "backend", None), "quality", "") or "").upper()


def banner_wanted(app):
    settings = getattr(app, "settings", None) or {}
    return login_limits_lossless(app) and lossless_requested(app) and not settings.get(DISMISS_KEY)


def _notice(app, text, state="ok", timeout_ms=2600):
    notice = getattr(app, "show_output_notice", None)
    if callable(notice):
        notice(text, state, timeout_ms)


def when_closed(window, callback):
    """Run `callback(window)` once when `window` is closed or destroyed.

    GTK 4 emits "destroy" only when the last reference to a window goes, and Python closures
    over a dialog keep it alive, so upstream's destroy handlers mostly never ran: closing a
    login dialog left "Login already in progress" stuck. close() and destroy() both unrealize."""
    done = []

    def _once(w, *_args):
        if not done:
            done.append(True)
            callback(w)

    window.connect("unrealize", _once)
    window.connect("destroy", _once)


# --- Browser sign-in -------------------------------------------------------------------------

class BrowserSignIn:
    """One browser sign-in attempt: which addresses were tried and whether one is being exchanged.

    `ui` needs status(text, error=False) and busy(flag). A rejected code keeps the attempt open:
    the pending PKCE session (and its verifier) survives a failed exchange, so signing in again
    from the same link works. Upstream's failure path closed the dialog instead."""

    def __init__(self, app, attempt_id, ui):
        self.app, self.attempt_id, self.ui = app, attempt_id, ui
        self.tried, self.busy = set(), False

    def current(self):
        return getattr(self.app, "_login_attempt_id", None) == self.attempt_id

    def offer(self, text, pasted=False):
        """Try `text` as the redirect address. True when an exchange started."""
        url = find_redirect_url(text)
        if url is None:
            if pasted and str(text or "").strip():
                self.ui.status("That isn't the address TIDAL lands on. It starts with "
                               "https://tidal.com/android/login/auth?code=", error=True)
            return False
        if self.busy or url in self.tried or not self.current():
            return False
        self.tried.add(url)
        self.busy = True
        self.ui.busy(True)
        self.ui.status("Signing in…")
        submit_daemon(self._exchange, url)
        return True

    def _exchange(self, url):
        backend = self.app.backend
        ok = False
        detail = ""
        try:
            ok = bool(backend.finish_pkce_login(url))
            if not ok:
                detail = str(backend.get_last_login_error() or "").strip()
        except Exception as e:  # never leave the dialog spinning
            detail = str(e)
        GLib.idle_add(self._done, ok, detail)

    def _done(self, ok, detail):
        self.busy = False
        if not self.current():
            return False
        if ok:
            self.app._on_login_success_for_attempt(self.attempt_id)
            _notice(self.app, "Signed in. Lossless is on.")
            return False
        logger.warning("Browser sign-in: TIDAL rejected the code (%s)", detail or "no detail")
        self.ui.busy(False)
        self.ui.status("TIDAL didn't accept that code. Open the page again (step 1), sign in, "
                       "and copy the new address.", error=True)
        return False


class _DialogUI:
    def __init__(self, status_label, spinner, entry_row):
        self.status_label, self.spinner, self.entry_row = status_label, spinner, entry_row

    def status(self, text, error=False):
        self.status_label.set_text(text)
        if error:
            self.status_label.add_css_class("error")
            self.status_label.remove_css_class("dim-label")
        else:
            self.status_label.remove_css_class("error")
            self.status_label.add_css_class("dim-label")

    def busy(self, flag):
        self.spinner.set_visible(flag)
        self.entry_row.set_sensitive(not flag)


class ClipboardWatch:
    """Feeds clipboard text to a BrowserSignIn whenever Ebb is active again.

    The clipboard is read once before the browser opens (Ebb has focus then, which Wayland
    requires). A redirect address already there is left over from an earlier sign-in: its code
    is spent, so it is marked tried instead of failing the new attempt on sight."""

    def __init__(self, signin, read_text):
        self.signin, self.read_text = signin, read_text
        self.ready = False

    def start(self):
        self.read_text(self._baseline)

    def _baseline(self, text):
        url = find_redirect_url(text)
        if url:
            self.signin.tried.add(url)
        self.ready = True

    def poll(self, *_args):
        if self.ready:
            self.read_text(self._take)

    def _take(self, text):
        if find_redirect_url(text):
            self.signin.offer(text)


def _step_row(number, title, subtitle):
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    row.add_prefix(Gtk.Label(label=str(number), valign=Gtk.Align.CENTER, css_classes=["ebb-step-badge"]))
    return row


def show_browser_signin(app, login_url, attempt_id):
    """Open TIDAL's sign-in page in the browser and wait for the address it lands on."""
    app._cleanup_login_dialog()
    win = Adw.Window(title="Sign In for Lossless", transient_for=app.win, modal=True,
                     default_width=480, resizable=False)
    view = Adw.ToolbarView()
    view.add_top_bar(Adw.HeaderBar())
    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                   margin_top=4, margin_bottom=22, margin_start=20, margin_end=20)
    view.set_content(Adw.Clamp(maximum_size=440, child=body))
    win.set_content(view)

    body.append(Gtk.Label(label="Finish in Your Browser", css_classes=["title-2"], wrap=True))
    lead = Gtk.Label(
        label="TIDAL's sign-in page is opening in your browser. You stay signed in here meanwhile.",
        wrap=True, justify=Gtk.Justification.CENTER, css_classes=["dim-label"])
    body.append(lead)

    steps = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    first = _step_row(1, "Sign in to TIDAL", "On the page that opened in your browser.")
    again = Gtk.Button(icon_name="web-browser-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                       tooltip_text="Open the sign-in page again")
    copy = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"],
                      tooltip_text="Copy the sign-in link")
    first.add_suffix(again)
    first.add_suffix(copy)
    steps.append(first)
    steps.append(_step_row(2, "Copy the address TIDAL lands on",
                           "TIDAL then shows an error page. That's expected: its address holds "
                           "the sign-in code. Press Ctrl+L, then Ctrl+C."))
    steps.append(_step_row(3, f"Come back to {brand.APP_NAME}",
                           f"{brand.APP_NAME} reads the address from the clipboard and signs you in."))
    body.append(steps)

    paste = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    entry = Adw.EntryRow(title="Or paste the address here", show_apply_button=True)
    paste.append(entry)
    body.append(paste)

    status_row = Gtk.Box(spacing=8)
    spinner = Adw.Spinner(visible=False, valign=Gtk.Align.CENTER)
    status = Gtk.Label(label="Waiting for the address…", wrap=True, hexpand=True,
                       justify=Gtk.Justification.CENTER, css_classes=["dim-label", "ebb-signin-status"])
    status_row.append(spinner)
    status_row.append(status)
    body.append(status_row)

    signin = BrowserSignIn(app, attempt_id, _DialogUI(status, spinner, entry))
    app._login_status_label = status
    clipboard = app.win.get_clipboard()

    def _read_text(callback):
        def _got(cb, result):
            try:
                text = cb.read_text_finish(result)
            except GLib.Error:
                text = None
            callback(text)
        clipboard.read_text_async(None, _got)

    watch = ClipboardWatch(signin, _read_text)
    hooks = [(clipboard, clipboard.connect("changed", watch.poll))]
    for window in (win, app.win):
        hooks.append((window, window.connect(
            "notify::is-active", lambda w, _p: w.get_property("is-active") and watch.poll())))

    def _open():
        if not app._open_login_url(login_url, attempt_id):
            lead.set_text("Your browser didn't open. Copy the sign-in link (step 1) "
                          "and open it in your browser.")

    again.connect("clicked", lambda _b: _open())
    copy.connect("clicked", lambda _b: (clipboard.set(login_url),
                                        signin.ui.status("Sign-in link copied.")))
    entry.connect("apply", lambda row: signin.offer(row.get_text(), pasted=True))
    entry.connect("changed", lambda row: signin.offer(row.get_text()) if find_redirect_url(row.get_text()) else None)

    keys = Gtk.ShortcutController()
    keys.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("Escape"),
                                       Gtk.CallbackAction.new(lambda *_a: win.close() or True)))
    win.add_controller(keys)

    def _teardown(_w):
        for obj, handler in hooks:
            if obj is not win:
                obj.disconnect(handler)
        hooks.clear()  # no clipboard reads once the dialog is gone
        if app._login_dialog is win:
            app._login_dialog = None
        if app._login_in_progress and attempt_id == app._login_attempt_id:
            app._cancel_login_attempt(attempt_id, reason="user-cancel")
            if getattr(app.backend, "user", None) is not None:
                _notice(app, "Sign-in canceled. You're still signed in.", "warn", 2600)

    when_closed(win, _teardown)
    app._login_dialog = win
    watch.start()  # before the browser takes focus
    win.present()
    _open()
    return win


# --- "Lossless is off" -----------------------------------------------------------------------

def on_explainer_response(app, response):
    if response == "browser":
        app._start_pkce_login_flow()
    elif response == "hide":
        settings = getattr(app, "settings", None)
        if isinstance(settings, dict):
            settings[DISMISS_KEY] = True
            saver = getattr(app, "schedule_save_settings", None)
            if callable(saver):
                saver()
        sync_banner(app)
        _notice(app, "Get Lossless stays in the account menu.", "ok", 3200)


def show_get_lossless(app, offer_hide=True):
    dialog = Adw.AlertDialog(
        heading="Get Lossless",
        body=("TIDAL sends AAC 320 instead of lossless to Web and QR sign-ins, even on paid plans. "
              "Only tracks with a hi-res master still arrive as FLAC.\n\n"
              "Signing in once more on TIDAL's website, in your browser, turns lossless on for "
              "everything. You stay signed in while you do it."),
    )
    if offer_hide:
        dialog.add_response("hide", "Don't Show Again")
    dialog.add_response("later", "Not Now" if offer_hide else "Cancel")
    dialog.add_response("browser", "Continue in Browser")
    dialog.set_response_appearance("browser", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("browser")
    dialog.set_close_response("later")
    dialog.connect("response", lambda _d, response: on_explainer_response(app, response))
    dialog.present(app.win)
    return dialog


def sync_banner(app):
    banner = getattr(app, "lossless_banner", None)
    if banner is not None:
        banner.set_revealed(banner_wanted(app))


# --- Account menu ----------------------------------------------------------------------------

def display_name(app):
    return str(getattr(app, "account_name", "") or "") or "TIDAL account"


def show_signed_in(app, name):
    """The header shows the account as an avatar with initials, not "Hi, <name>": that text
    made the header 451 px wide, wider than the narrowest layout (410 px of content)."""
    app.account_name = name
    button = app.login_btn
    button.set_child(Adw.Avatar(size=24, text=name, show_initials=True))
    button.set_tooltip_text(f"Signed in as {name}")
    button.update_property([Gtk.AccessibleProperty.LABEL], [f"Account: {name}"])


def show_signed_out(app):
    app.account_name = ""
    button = app.login_btn
    button.set_label("Sign In")
    button.set_tooltip_text(None)
    button.update_property([Gtk.AccessibleProperty.LABEL], ["Sign In"])


def account_quality_text(app):
    if login_limits_lossless(app):
        return "Most tracks stream as AAC 320 with this sign-in", True
    return "Lossless and hi-res streaming", False


def build_account_popover(app):
    pop = Gtk.Popover()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                  margin_top=8, margin_bottom=4, margin_start=4, margin_end=4)
    head = Gtk.Box(spacing=10, margin_start=8, margin_end=8, margin_bottom=8)
    avatar = Adw.Avatar(size=36, show_initials=True, valign=Gtk.Align.CENTER)
    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, valign=Gtk.Align.CENTER)
    name = Gtk.Label(xalign=0, css_classes=["heading"])
    quality = Gtk.Label(xalign=0, wrap=True, max_width_chars=28, css_classes=["caption"])
    text_box.append(name)
    text_box.append(quality)
    head.append(avatar)
    head.append(text_box)
    get = Gtk.Button(label="Get Lossless…", css_classes=["flat"])
    get.get_child().set_xalign(0)
    logout = Gtk.Button(label="Sign Out", css_classes=["flat"])
    logout.get_child().set_xalign(0)
    logout.get_child().add_css_class("error")
    for widget in (head, get, Gtk.Separator(margin_top=4, margin_bottom=4), logout):
        box.append(widget)
    pop.set_child(box)

    def _refresh(_pop):
        text, limited = account_quality_text(app)
        name.set_text(display_name(app))
        avatar.set_text(display_name(app))
        quality.set_text(text)
        for css, on in (("warning", limited), ("dim-label", not limited)):
            (quality.add_css_class if on else quality.remove_css_class)(css)
        get.set_visible(limited)

    pop.connect("show", _refresh)
    get.connect("clicked", lambda _b: (pop.popdown(), show_get_lossless(app, offer_hide=False)))
    logout.connect("clicked", app.on_logout_clicked)
    return pop
