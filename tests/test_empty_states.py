"""Fork: an empty album/playlist list explains itself instead of showing nothing."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import ui_actions  # noqa: E402
from ui import track_table  # noqa: E402


class _Text:
    def __init__(self):
        self.text = None
        self.visible = None

    def set_text(self, value):
        self.text = value

    def set_visible(self, value):
        self.visible = bool(value)


class Mix:  # the renderer tells mixes from albums by type name
    pass


class Album:
    pass


def _app(**kw):
    return SimpleNamespace(
        track_list_placeholder_label=_Text(),
        track_list_placeholder_retry=_Text(),
        current_remote_playlist=None,
        current_album=None,
        **kw,
    )


@pytest.mark.parametrize(
    "setup, text, retry",
    [
        (dict(current_remote_playlist=SimpleNamespace(num_tracks=30)), "Couldn't load this playlist's tracks.", True),
        (dict(current_remote_playlist=SimpleNamespace(num_tracks=0)), "This playlist is empty.", False),
        (dict(current_album=Mix()), "Couldn't load this mix.", True),
        (dict(current_album=Album()), "Couldn't load this album's tracks.", True),
    ],
)
def test_empty_list_says_why(setup, text, retry):
    app = _app()
    for k, v in setup.items():
        setattr(app, k, v)
    ui_actions._update_track_list_placeholder(app, [])
    assert app.track_list_placeholder_label.text.startswith(text)
    assert app.track_list_placeholder_retry.visible is retry


def test_a_filled_list_clears_the_message():
    app = _app(current_album=Album())
    ui_actions._update_track_list_placeholder(app, [])
    ui_actions._update_track_list_placeholder(app, [object()])
    assert app.track_list_placeholder_label.text == ""
    assert app.track_list_placeholder_retry.visible is False


def test_retry_reopens_what_failed():
    calls = []
    pl = SimpleNamespace(num_tracks=3)
    app = _app(current_remote_playlist=pl, current_album=Album())
    app.on_remote_playlist_card_clicked = lambda p: calls.append(("playlist", p))
    app.show_album_details = lambda a: calls.append(("album", a))
    ui_actions.retry_track_view(app)
    app.current_remote_playlist = None
    ui_actions.retry_track_view(app)
    assert calls == [("playlist", pl), ("album", app.current_album)]


def test_clearing_rows_leaves_the_placeholder_attached():
    placeholder = object()
    rows = ["r1", "r2", "r3"]
    removed = []

    class _List:
        def get_row_at_index(self, i):
            return rows[i] if i < len(rows) else None

        def remove(self, w):
            assert w is not placeholder
            rows.remove(w)
            removed.append(w)

    track_table.clear_track_rows(_List())
    assert removed == ["r1", "r2", "r3"] and rows == []
