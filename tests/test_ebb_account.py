"""Fork: browser sign-in for lossless (TIDAL blocks the embedded WebKit view) and the account UI."""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, "src")

from ui import account  # noqa: E402

REDIRECT = "https://tidal.com/android/login/auth?code=fresh&state=s"


@pytest.mark.parametrize("text, expected", [
    (REDIRECT, REDIRECT),
    ("tidal.com/android/login/auth?code=abc&state=1", "https://tidal.com/android/login/auth?code=abc&state=1"),
    ('copied "http://tidal.com/android/login/auth?state=1&code=z9" here',
     "https://tidal.com/android/login/auth?state=1&code=z9"),
    ("https://www.tidal.com/android/login/auth?code=Q", "https://www.tidal.com/android/login/auth?code=Q"),
    ("https://tidal.com/android/login/auth?state=1", None),  # no code
    ("https://xtidal.com/android/login/auth?code=x", None),
    ("https://listen.tidal.com/album/1", None),
    ("", None),
    (None, None),
])
def test_the_redirect_address_is_found_in_whatever_was_copied(text, expected):
    assert account.find_redirect_url(text) == expected


class _UI:
    def __init__(self):
        self.messages, self.errors, self.busy_states = [], [], []

    def status(self, text, error=False):
        (self.errors if error else self.messages).append(text)

    def busy(self, flag):
        self.busy_states.append(flag)


def _app(result=True, error="", raises=None, attempt=7):
    calls = SimpleNamespace(exchanged=[], succeeded=[], notices=[])

    def finish(url):
        calls.exchanged.append(url)
        if raises:
            raise raises
        return result

    backend = SimpleNamespace(finish_pkce_login=finish, get_last_login_error=lambda: error)
    app = SimpleNamespace(
        backend=backend,
        _login_attempt_id=attempt,
        _on_login_success_for_attempt=calls.succeeded.append,
        show_output_notice=lambda text, state, ms: calls.notices.append(text),
    )
    return app, calls


@pytest.fixture
def synchronous(monkeypatch):
    monkeypatch.setattr(account, "submit_daemon", lambda fn, *args: fn(*args))
    monkeypatch.setattr(account.GLib, "idle_add", lambda fn, *args: fn(*args))


def test_a_copied_address_signs_in_once(synchronous):
    app, calls = _app()
    signin = account.BrowserSignIn(app, 7, _UI())
    assert signin.offer("junk") is False and calls.exchanged == []
    assert signin.offer(REDIRECT) is True
    assert signin.offer(REDIRECT) is False  # the same code is never sent twice
    assert calls.exchanged == [REDIRECT] and calls.succeeded == [7]
    assert calls.notices == ["Signed in. Lossless is on."]


def test_a_rejected_code_keeps_the_dialog_open_for_another_try(synchronous):
    app, calls = _app(result=False, error="invalid_grant")
    ui = _UI()
    signin = account.BrowserSignIn(app, 7, ui)
    assert signin.offer(REDIRECT) is True
    assert calls.succeeded == [] and ui.busy_states == [True, False] and not signin.busy
    assert "step 1" in ui.errors[-1]
    app.backend.finish_pkce_login = lambda url: calls.exchanged.append(url) or True
    assert signin.offer(REDIRECT.replace("fresh", "second")) is True
    assert calls.succeeded == [7]


def test_an_exchange_that_raises_is_a_rejection_not_a_stuck_spinner(synchronous):
    app, calls = _app(raises=RuntimeError("network down"))
    ui = _UI()
    account.BrowserSignIn(app, 7, ui).offer(REDIRECT)
    assert ui.busy_states == [True, False] and calls.succeeded == []


def test_a_pasted_non_address_says_what_to_paste():
    app, calls = _app()
    ui = _UI()
    assert account.BrowserSignIn(app, 7, ui).offer("https://listen.tidal.com/", pasted=True) is False
    assert "tidal.com/android/login/auth?code=" in ui.errors[-1] and calls.exchanged == []


def test_a_cancelled_attempt_ignores_late_results(monkeypatch):
    app, calls = _app()
    pending = []
    monkeypatch.setattr(account, "submit_daemon", lambda fn, *args: fn(*args))
    monkeypatch.setattr(account.GLib, "idle_add", lambda fn, *args: pending.append((fn, args)))
    signin = account.BrowserSignIn(app, 7, _UI())
    signin.offer(REDIRECT)
    app._login_attempt_id = None  # dialog closed while TIDAL answered
    fn, args = pending.pop()
    fn(*args)
    assert calls.succeeded == []
    assert signin.offer(REDIRECT.replace("fresh", "other")) is False


def test_a_spent_address_already_on_the_clipboard_is_not_tried(synchronous):
    app, calls = _app()
    signin = account.BrowserSignIn(app, 7, _UI())
    clipboard = {"text": "https://tidal.com/android/login/auth?code=old"}
    watch = account.ClipboardWatch(signin, lambda callback: callback(clipboard["text"]))
    watch.poll()
    assert calls.exchanged == []  # nothing read before the baseline
    watch.start()
    watch.poll()  # Ebb active again, clipboard unchanged
    assert calls.exchanged == []
    clipboard["text"] = "some other text"
    watch.poll()
    clipboard["text"] = REDIRECT
    watch.poll()
    assert calls.exchanged == [REDIRECT] and calls.succeeded == [7]


def test_dont_show_again_hides_the_banner_for_good():
    shown, saved, flows = [], [], []
    app = SimpleNamespace(
        settings={},
        backend=SimpleNamespace(login_limits_lossless=lambda: True, quality="LOSSLESS"),
        lossless_banner=SimpleNamespace(set_revealed=shown.append),
        schedule_save_settings=lambda: saved.append(True),
        show_output_notice=lambda *a: None,
        _start_pkce_login_flow=lambda: flows.append(True),
    )
    account.on_explainer_response(app, "later")
    assert (shown, saved, flows) == ([], [], [])
    account.on_explainer_response(app, "browser")
    assert flows == [True]
    account.on_explainer_response(app, "hide")
    assert app.settings[account.DISMISS_KEY] is True and saved == [True] and shown == [False]


def test_the_account_menu_names_the_quality_this_login_gets():
    limited = SimpleNamespace(backend=SimpleNamespace(login_limits_lossless=lambda: True))
    hifi = SimpleNamespace(backend=SimpleNamespace(login_limits_lossless=lambda: False))
    assert account.account_quality_text(limited) == ("Most tracks stream as AAC 320 with this sign-in", True)
    assert account.account_quality_text(hifi) == ("Lossless and hi-res streaming", False)
    assert account.display_name(SimpleNamespace(account_name="Henry")) == "Henry"
    assert account.display_name(SimpleNamespace(account_name="")) == "TIDAL account"
    assert account.display_name(SimpleNamespace()) == "TIDAL account"


class _Window:
    def __init__(self):
        self.handlers = {}

    def connect(self, signal, fn):
        self.handlers.setdefault(signal, []).append(fn)

    def emit(self, signal):
        for fn in self.handlers.get(signal, []):
            fn(self)


def test_closing_a_dialog_runs_its_cleanup_once_without_waiting_for_destroy():
    # GTK 4 emits "destroy" only when the last reference goes; close() and destroy() both unrealize.
    window, calls = _Window(), []
    account.when_closed(window, calls.append)
    window.emit("unrealize")
    window.emit("destroy")
    assert calls == [window]


def test_hifi_sign_in_goes_to_the_browser_and_webkit_is_never_loaded(monkeypatch):
    from app import app_auth

    assert app_auth.WebKit is None and app_auth._WEBKIT_AVAILABLE is False
    assert "gi.repository.WebKit" not in sys.modules
    opened = []
    monkeypatch.setattr(app_auth.account, "show_browser_signin",
                        lambda app, url, attempt: opened.append((url, attempt)))
    app = SimpleNamespace(
        backend=SimpleNamespace(start_pkce_login=lambda: {"url": "https://login.tidal.com/authorize?x=1"}),
        record_diag_event=lambda *_a: None,
        show_output_notice=lambda *_a: None,
    )
    app_auth._start_pkce_login_flow(app)
    assert opened == [("https://login.tidal.com/authorize?x=1", app._login_attempt_id)]
    assert app._login_in_progress is True and app._login_mode == "pkce"
