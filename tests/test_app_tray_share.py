import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_tray


class _Clipboard:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class _Display:
    def __init__(self):
        self.clipboard = _Clipboard()

    def get_clipboard(self):
        return self.clipboard


class _Window:
    def __init__(self, display):
        self._display = display

    def get_display(self):
        return self._display


def test_tray_copies_the_playing_tracks_tidal_link(monkeypatch):
    display = _Display()
    app = SimpleNamespace(win=_Window(display), playing_track=SimpleNamespace(id=123))

    monkeypatch.setattr(app_tray.GLib, "idle_add", lambda func: func())

    app_tray._copy_track_link_from_tray(app)

    assert display.clipboard.value == "https://tidal.com/browse/track/123"


def test_tray_copy_does_nothing_when_nothing_is_playing():
    display = _Display()
    app = SimpleNamespace(win=_Window(display), playing_track=None)

    assert app_tray._copy_current_track_link(app) is False
    assert display.clipboard.value is None
