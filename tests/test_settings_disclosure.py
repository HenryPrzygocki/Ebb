"""Fork: Settings shows what applies (driver-specific rows, Last.fm's one action) and says
what the selected driver does (ui/views_builders.py)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from _rust import audio as rust_audio  # noqa: E402
from actions import scrobble_actions  # noqa: E402
from ui import views_builders  # noqa: E402


def test_every_driver_the_player_offers_has_a_summary():
    for driver in rust_audio.RustAudioPlayerAdapter.get_drivers(None):
        assert views_builders._driver_summary(driver) != views_builders._DRIVER_SUMMARY_FALLBACK, driver
    assert views_builders._driver_summary(None) == views_builders._DRIVER_SUMMARY_FALLBACK


class _Control:
    def __init__(self, sensitive):
        self.sensitive = sensitive
        self.handlers = []

    def get_sensitive(self):
        return self.sensitive

    def connect(self, signal, handler):
        assert signal == "notify::sensitive"
        self.handlers.append(handler)

    def set_sensitive(self, value):
        self.sensitive = value
        for handler in self.handlers:
            handler(self, None)


class _Row:
    visible = None

    def set_visible(self, value):
        self.visible = value


def test_a_driver_specific_row_shows_only_while_its_control_applies():
    control, row = _Control(sensitive=False), _Row()
    views_builders._row_follows(row, control)
    assert row.visible is False  # under the default driver
    control.set_sensitive(True)  # ALSA picked: on_driver_changed enables the control
    assert row.visible is True
    control.set_sensitive(False)
    assert row.visible is False


class _Widget:
    def __init__(self):
        self.visible = True
        self.sensitive = True
        self.text = ""
        self.classes = set()

    def set_visible(self, value):
        self.visible = bool(value)

    def set_sensitive(self, value):
        self.sensitive = bool(value)

    def set_text(self, value):
        self.text = value

    def add_css_class(self, name):
        self.classes.add(name)

    def remove_css_class(self, name):
        self.classes.discard(name)


@pytest.mark.parametrize("session_key, connected", [("", False), ("a-session-key", True)])
def test_lastfm_shows_the_one_action_that_applies(session_key, connected):
    app = SimpleNamespace(
        settings={"scrobble_lastfm_session_key": session_key, "scrobble_lastfm_enabled": True},
        scrobble_lastfm_status_label=_Widget(),
        scrobble_lastfm_disconnect_btn=_Widget(),
        scrobble_lastfm_connect_btn=_Widget(),
    )
    scrobble_actions._refresh_lastfm_status_ui(app)
    assert app.scrobble_lastfm_disconnect_btn.visible is connected
    assert app.scrobble_lastfm_connect_btn.visible is (not connected)
