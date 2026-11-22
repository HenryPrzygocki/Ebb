"""Fork: device-code logins get AAC for most tracks; say so, and make the HiFi re-login safe."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import audio_settings_actions as asa  # noqa: E402
from backend import tidal as tidal_mod  # noqa: E402
from backend.tidal import TidalBackend  # noqa: E402
from ui import views_builders  # noqa: E402


class _FakeSession:
    def __init__(self, ok=True, is_pkce=False):
        self.ok, self.is_pkce, self.user = ok, is_pkce, SimpleNamespace(id=1)
        self.config = SimpleNamespace()

    def pkce_login_url(self):
        return "https://login.tidal.example/authorize"

    def pkce_get_auth_token(self, _url):
        return {"access_token": "x"}

    def process_auth_token(self, _token, is_pkce_token=False):
        self.is_pkce = is_pkce_token

    def check_login(self):
        return self.ok


def _backend(session):
    b = object.__new__(TidalBackend)
    b.session, b.user, b.quality = session, SimpleNamespace(id=1), "HI_RES_LOSSLESS"
    for name in ("_normalize_tls_ca_env", "_tune_http_pool", "save_session", "refresh_favorite_ids"):
        setattr(b, name, lambda *a, **k: None)
    b._last_login_error = ""
    return b


@pytest.mark.parametrize("ok", [True, False])
def test_a_hifi_re_login_replaces_the_session_only_when_it_succeeds(monkeypatch, ok):
    old = _FakeSession(is_pkce=False)
    new = _FakeSession(ok=ok)
    monkeypatch.setattr(tidal_mod.tidalapi, "Session", lambda: new)
    b = _backend(old)
    assert b.start_pkce_login()["url"].startswith("https://")
    assert b.session is old  # cancelling here keeps you signed in
    assert b.finish_pkce_login("https://tidal.com/android/login/auth?code=abc") is ok
    assert b.session is (new if ok else old)
    assert b.login_limits_lossless() is (not ok)


def test_only_signed_in_device_code_logins_are_limited():
    b = _backend(_FakeSession(is_pkce=False))
    assert b.login_limits_lossless() is True
    b.session.is_pkce = True
    assert b.login_limits_lossless() is False
    b.session.is_pkce, b.user = False, None
    assert b.login_limits_lossless() is False


class _Label:
    def __init__(self):
        self.text, self.tooltip, self.css, self.visible = "", None, set(), True

    def set_text(self, text):
        self.text = text

    def set_tooltip_text(self, text):
        self.tooltip = text

    def add_css_class(self, name):
        self.css.add(name)

    def remove_css_class(self, name):
        self.css.discard(name)

    def set_visible(self, value):
        self.visible = value


def _label_app(quality="HI_RES_LOSSLESS", limited=True):
    return SimpleNamespace(
        lbl_tech=_Label(),
        player=SimpleNamespace(bit_perfect_mode=False, exclusive_lock_mode=False, output_state="active"),
        backend=SimpleNamespace(quality=quality, login_limits_lossless=lambda: limited),
        current_device_name="DAC",
    )


def test_aac_instead_of_lossless_is_flagged_and_explained():
    app = _label_app()
    asa.update_tech_label(app, {"codec": "AAC", "source_rate": 44100, "source_depth": 16})
    assert app.lbl_tech.text == "MIX/SHR • 44.1kHz • AAC"  # no "16-bit" on a lossy stream
    assert "tech-state-warn" in app.lbl_tech.css
    assert app.lbl_tech.tooltip.startswith("AAC instead of lossless. TIDAL limits this login type")
    app = _label_app(limited=False)
    asa.update_tech_label(app, {"codec": "AAC", "source_rate": 44100, "source_depth": 16})
    assert "no lossless version of this track" in app.lbl_tech.tooltip


def test_lossless_streams_and_chosen_aac_are_not_flagged():
    app = _label_app()
    asa.update_tech_label(app, {"codec": "FLAC", "source_rate": 192000, "source_depth": 24})
    assert app.lbl_tech.text == "MIX/SHR • 24-bit/192kHz • FLAC"
    assert "tech-state-warn" not in app.lbl_tech.css
    app = _label_app(quality="HIGH")
    asa.update_tech_label(app, {"codec": "AAC", "source_rate": 44100, "source_depth": 16})
    assert "tech-state-warn" not in app.lbl_tech.css and not app.lbl_tech.tooltip.startswith("AAC instead")


def test_the_banner_follows_the_login_type():
    shown = []
    banner = SimpleNamespace(set_revealed=shown.append)
    app = SimpleNamespace(lossless_banner=banner, backend=SimpleNamespace(login_limits_lossless=lambda: True))
    views_builders.sync_lossless_banner(app)
    app.backend.login_limits_lossless = lambda: False
    views_builders.sync_lossless_banner(app)
    views_builders.sync_lossless_banner(SimpleNamespace(lossless_banner=banner, backend=None))
    assert shown == [True, False, False]
