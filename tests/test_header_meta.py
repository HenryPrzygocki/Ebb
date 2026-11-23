"""Fork: album and playlist headers give the running time, and "1 Track"."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("gi")

from ui import track_table as tt  # noqa: E402


@pytest.mark.parametrize("seconds, text", [
    (0, ""), (None, ""), (20, "1 min"), (2594, "43 min"), (3600, "1 hr"),
    (4320, "1 hr 12 min"), (3599, "1 hr"), (7290, "2 hr 2 min"),
])
def test_runtime(seconds, text):
    assert tt.runtime_text(seconds) == text


def test_the_owner_s_duration_wins_and_tracks_are_the_fallback():
    tracks = [SimpleNamespace(duration=200), {"duration": 100}, SimpleNamespace()]
    assert tt.total_seconds(SimpleNamespace(duration=2594), tracks) == 2594
    assert tt.total_seconds(SimpleNamespace(duration=None), tracks) == 300
    assert tt.total_seconds(None, None) == 0


def test_meta_line():
    assert tt.count_text(1) == "1 Track" and tt.count_text(10) == "10 Tracks" and tt.count_text(0) == ""
    assert tt.meta_line("1973", tt.count_text(10), tt.runtime_text(2594)) == "1973  •  10 Tracks  •  43 min"
    assert tt.meta_line("", tt.count_text(1), "") == "1 Track"


def test_count_phrase_drops_zero_counts():
    from actions import ui_actions
    f = ui_actions._count_phrase
    assert f(0, "folder", "folders", 20, "playlist", "playlists") == "20 playlists"
    assert f(2, "folder", "folders", 1, "playlist", "playlists") == "2 folders • 1 playlist"
    assert f(0, "folder", "folders", 0, "playlist", "playlists") == "0 playlists"
