"""Fork: the Now Playing lyrics tab when there is nothing to follow line by line."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions.lyrics_playback_actions import NO_LYRICS_BOTTOM_HINT  # noqa: E402
from app import app_now_playing as np  # noqa: E402


class _Widget:
    def __init__(self, **kw):
        self.kw, self.children = kw, []
        self.classes = set(kw.get("css_classes", []))

    def append(self, child):
        self.children.append(child)

    def remove(self, child):
        self.children.remove(child)

    def get_first_child(self):
        return self.children[0] if self.children else None

    def add_css_class(self, name):
        self.classes.add(name)

    def __getattr__(self, name):
        if name.startswith("set_"):
            return lambda *_a, **_k: None
        raise AttributeError(name)


@pytest.fixture
def app(monkeypatch):
    real = np.Gtk
    monkeypatch.setattr(
        np,
        "Gtk",
        SimpleNamespace(
            Label=_Widget, Box=_Widget, Align=real.Align, Orientation=real.Orientation, Justification=real.Justification
        ),
    )
    monkeypatch.setattr(np, "_attach_lyric_seek_gesture", lambda *_a: None)
    return SimpleNamespace(
        now_playing_lyrics_vbox=_Widget(),
        player=SimpleNamespace(get_position=lambda: (0.0, 0.0)),
        _sync_now_playing_lyrics=lambda _pos: None,
    )


def _labels(widget):
    for child in widget.children:
        if "label" in child.kw:
            yield child
        yield from _labels(child)


def test_no_lyrics_is_an_empty_state_in_the_middle_of_the_tab(app):
    # It was the visualizer's hint: a small dim line at the bottom edge of a blank panel.
    np._render_now_playing_lyrics(app, None, NO_LYRICS_BOTTOM_HINT)
    [center] = app.now_playing_lyrics_vbox.children
    assert center.kw["valign"] == np.Gtk.Align.CENTER and center.kw["vexpand"] is True
    [label] = _labels(app.now_playing_lyrics_vbox)
    assert label.kw["label"] == np.NOW_PLAYING_NO_LYRICS == "No lyrics for this track"
    assert "dim-label" not in label.classes


def test_unsynced_lyrics_are_readable(app):
    # No line of unsynced lyrics ever becomes the active one: the whole text stayed in the
    # waiting lines' style (35 % white, weight 200).
    lyrics = SimpleNamespace(has_synced=False, raw_text="First line\nSecond line", time_points=[], lyrics_map={})
    np._render_now_playing_lyrics(app, lyrics, None)
    [label] = _labels(app.now_playing_lyrics_vbox)
    assert {"lyric-line", "lyric-static"} <= label.classes
    assert app.now_playing_lyric_widgets == []  # nothing to highlight or seek to


def test_synced_lines_keep_the_waiting_style_until_they_are_sung(app):
    lyrics = SimpleNamespace(has_synced=True, time_points=[0, 5], lyrics_map={0: "First line", 5: "Second line"})
    np._render_now_playing_lyrics(app, lyrics, None)
    labels = list(_labels(app.now_playing_lyrics_vbox))
    assert len(labels) == 2 and all("lyric-static" not in lbl.classes for lbl in labels)
    assert [entry["time"] for entry in app.now_playing_lyric_widgets] == [0, 5]


def test_the_static_style_is_brighter_than_a_waiting_line():
    from ui import config as ui_config

    css = ui_config.CSS_DATA
    assert ".lyric-line.lyric-static" in css and ".lyrics-theme-light .lyric-line.lyric-static" in css
