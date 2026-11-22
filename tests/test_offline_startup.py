"""Fork: starting without a network keeps the login and retries (ui/offline.py), and only a
login TIDAL refused counts as signed out (backend.restore_failure_kind)."""
import json
import os
import sys
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from backend import tidal as tidal_mod  # noqa: E402
from ui import offline  # noqa: E402
from test_tidal_session_recovery import _FakeSession, _make_backend  # noqa: E402


def _http_error(status):
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(str(status), response=response)


@pytest.mark.parametrize("exc, kind", [
    # The keyword classifier calls this "auth": the refresh URL contains "token".
    (requests.ConnectionError("Max retries exceeded with url: /v1/oauth2/token (Failed to resolve)"), "offline"),
    (requests.Timeout("read timed out"), "offline"),
    (_http_error(503), "offline"),
    (ValueError("Expecting value: line 1 column 1 (char 0)"), "offline"),  # a captive portal's page
    (_http_error(401), "auth"),
    (_http_error(400), "auth"),
    (tidal_mod._TidalAuthError("Authentication failed with error 'invalid_grant'"), "auth"),
])
def test_only_a_refusal_counts_as_signed_out(exc, kind):
    assert tidal_mod.restore_failure_kind(exc) == kind


def _saved_login(backend, tmp_path):
    backend.token_file = str(tmp_path / "token.json")
    backend.legacy_token_file = str(tmp_path / "token.pkl")
    with open(backend.token_file, "w", encoding="utf-8") as f:
        json.dump({"token_type": "Bearer", "access_token": "a", "refresh_token": "r",
                   "expiry_time": "2025-01-01T00:00:00"}, f)


def test_a_restore_without_network_is_offline_not_signed_out(tmp_path, monkeypatch):
    class _NoNetwork(_FakeSession):
        def load_oauth_session(self, *args, **kwargs):
            raise requests.ConnectionError("Max retries exceeded with url: /v1/sessions")

    backend = _make_backend()
    _saved_login(backend, tmp_path)
    monkeypatch.setattr(tidal_mod.tidalapi, "Session", _NoNetwork)
    assert backend.try_load_session() is False
    assert backend.restore_failure == "offline"


def test_a_refused_login_is_signed_out(tmp_path, monkeypatch):
    class _Refused(_FakeSession):
        def check_login(self):
            return False

    backend = _make_backend()
    _saved_login(backend, tmp_path)
    monkeypatch.setattr(tidal_mod.tidalapi, "Session", _Refused)
    assert backend.try_load_session() is False
    assert backend.restore_failure == "auth"


def test_no_saved_login_is_plainly_signed_out(tmp_path):
    backend = _make_backend()
    backend.token_file = str(tmp_path / "none.json")
    backend.legacy_token_file = str(tmp_path / "none.pkl")
    assert backend.try_load_session() is False
    assert backend.restore_failure is None


def test_retries_back_off_and_the_last_delay_repeats():
    assert [offline.delay(n) for n in range(7)] == [5, 10, 20, 30, 60, 60, 60]


class _Label:
    text = ""

    def set_text(self, text):
        self.text = text


class _Button:
    def __init__(self):
        self.visible, self.sensitive, self.label = True, True, ""

    def set_visible(self, value):
        self.visible = bool(value)

    def set_sensitive(self, value):
        self.sensitive = bool(value)

    def set_label(self, text):
        self.label = text


class _Monitor:
    def __init__(self):
        self.handlers, self.disconnected = {}, []

    def connect(self, signal, handler):
        self.handlers[signal] = handler
        return 7

    def disconnect(self, handler_id):
        self.disconnected.append(handler_id)


@pytest.fixture
def timers(monkeypatch):
    """GLib timers are recorded, not run; idle callbacks and the retry thread run at once."""
    pending, ids = {}, iter(range(1, 1000))

    def timeout_add_seconds(seconds, fn):
        tid = next(ids)
        pending[tid] = (seconds, fn)
        return tid

    class _Now:
        def __init__(self, target=None, daemon=None, name=None):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(offline.GLib, "timeout_add_seconds", timeout_add_seconds)
    monkeypatch.setattr(offline.GLib, "source_remove", lambda tid: pending.pop(tid, None))
    monkeypatch.setattr(offline.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.setattr(offline, "Thread", _Now)
    monkeypatch.setattr(offline, "MIN_BUSY", 0)
    return pending


def _fire(timers):
    (_seconds, fn), = timers.values()
    timers.clear()
    fn()


def _app(results):
    """`results`: what each try_load_session gives, as (ok, restore_failure), or a function
    called during the try that returns it."""
    backend = SimpleNamespace(restore_failure=None)

    def try_load_session():
        result = results.pop(0)
        ok, backend.restore_failure = result() if callable(result) else result
        return ok

    backend.try_load_session = try_load_session
    app = SimpleNamespace(backend=backend, login_prompt_title=_Label(), login_prompt_text=_Label(),
                          login_prompt_btn=_Button(), login_retry_btn=_Button(),
                          login_again_btn=_Button(), login_btn=_Button(), grid_subtitle_label=_Label(),
                          views=[], signed_in=[])
    app._toggle_login_view = lambda logged_in: app.views.append(logged_in)
    app.on_login_success = lambda: app.signed_in.append(True)
    return app


def test_offline_at_startup_keeps_the_login_and_retries_until_tidal_answers(timers):
    app, monitor = _app([(False, "offline"), (True, None)]), _Monitor()
    offline.show(app, monitor=monitor)
    assert app.login_prompt_title.text == offline.OFFLINE_TITLE
    assert app.login_retry_btn.visible and app.login_again_btn.visible
    assert not app.login_prompt_btn.visible and not app.login_btn.visible  # nothing offers to sign in
    assert app.grid_subtitle_label.text == offline.page_subtitle(app) == offline.OFFLINE_PAGE
    assert [s for s, _ in timers.values()] == [5]

    _fire(timers)  # still offline: the next try waits longer
    assert [s for s, _ in timers.values()] == [10]
    assert app.login_retry_btn.sensitive and app.login_retry_btn.label == "Try Again"

    monitor.handlers["network-changed"](monitor, True)  # the network is back: soon, not in 10 s
    assert [s for s, _ in timers.values()] == [offline.NETWORK_BACK_DELAY]
    _fire(timers)
    assert app.signed_in == [True]
    assert app.login_prompt_title.text == offline.SIGN_IN_TITLE  # the sign-in card, for later
    assert app.login_btn.visible and not app.login_retry_btn.visible
    assert monitor.disconnected == [7] and timers == {}


def test_a_login_refused_on_retry_asks_to_sign_in(timers):
    app = _app([(False, "auth")])
    offline.show(app, monitor=_Monitor())
    offline.retry(app)  # Try Again
    assert app.views == [False, False]  # the offline card, then the sign-in card
    assert app.login_prompt_title.text == offline.SIGN_IN_TITLE
    assert app.grid_subtitle_label.text == offline.page_subtitle(app) == offline.SIGN_IN_PAGE
    assert app.signed_in == [] and timers == {}


def test_the_network_back_during_a_try_brings_the_next_one_forward(timers):
    monitor = _Monitor()

    def network_back_meanwhile():  # this try started before the network was up, and fails
        assert app.login_retry_btn.label == "Connecting…" and not app.login_retry_btn.sensitive
        monitor.handlers["network-changed"](monitor, True)
        return False, "offline"

    app = _app([network_back_meanwhile])
    offline.show(app, monitor=monitor)
    _fire(timers)
    assert [s for s, _ in timers.values()] == [offline.NETWORK_BACK_DELAY]  # not the 10 s backoff
