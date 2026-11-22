"""Fork #25: Add to Queue / Play Next form an "Up Next" queue that plays right after the current track."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import playback_actions, up_next  # noqa: E402
from app import app_queue  # noqa: E402


class Track:
    def __init__(self, name):
        self.name = name
        self.id = name


class FakeApp:
    MODE_LOOP, MODE_ONE, MODE_SHUFFLE, MODE_SMART, MODE_NORMAL = 0, 1, 2, 3, 4

    def __init__(self, names=("t0", "t1", "t2", "t3", "t4"), mode=4):
        self.play_queue = [Track(n) for n in names]
        self.play_mode = mode
        self.played = []
        self.current_track_index = -1
        self.playing_track = None
        self._refresh_queue_views = lambda: None
        self._update_track_list_icon = lambda: None
        self.play_track(0)

    def _get_active_queue(self):
        return list(self.play_queue)

    def play_track(self, index, from_history=False):  # the real one's bookkeeping, minus audio
        queue = self._get_active_queue()
        entry = queue[index]
        playback_actions.record_track_change(self, queue, entry, from_history=from_history)
        self.current_track_index = index
        self.playing_track = entry
        self.played.append(entry.name)
        up_next.settle(self)

    def next(self, auto=False):
        playback_actions.on_next_track(self, auto=auto)
        return self.played[-1]

    def names(self):
        return [t.name for t in self.play_queue]

    def index_of(self, name):
        return next(i for i, t in enumerate(self.play_queue) if t.name == name)


def test_add_to_queue_plays_after_the_current_track_not_after_the_whole_list():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app_queue.add_tracks_to_queue(app, [Track("Y")])
    assert app.names() == ["t0", "X", "Y", "t1", "t2", "t3", "t4"]
    assert [app.next(), app.next(), app.next()] == ["X", "Y", "t1"]
    assert up_next.pending(app) == []


def test_play_next_goes_before_earlier_queued_tracks():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app_queue.play_tracks_next(app, [Track("Y")])
    assert [app.next(), app.next(), app.next()] == ["Y", "X", "t1"]


def test_after_a_jump_queued_tracks_follow_the_new_track_and_the_list_continues_from_there():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app.play_track(app.index_of("t3"))  # clicked further down the list
    assert app.names() == ["t0", "t1", "t2", "t3", "X", "t4"]
    assert [app.next(), app.next()] == ["X", "t4"]


def test_queued_tracks_survive_starting_another_album():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app.play_queue = [Track("a0"), Track("a1")]  # a new album replaced the queue
    app.play_track(0)
    assert [app.next(), app.next()] == ["X", "a1"]


def test_queued_tracks_come_first_under_shuffle():
    app = FakeApp(names=[f"t{i}" for i in range(30)], mode=FakeApp.MODE_SHUFFLE)
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app_queue.add_tracks_to_queue(app, [Track("Y")])
    assert [app.next(), app.next()] == ["X", "Y"]
    rest = [app.next() for _ in range(29)]
    assert "X" not in rest and "Y" not in rest  # each played once
    assert sorted(rest) == sorted(f"t{i}" for i in range(1, 30))


def test_repeat_one_repeats_at_the_end_of_a_track_and_next_moves_on():
    app = FakeApp(mode=FakeApp.MODE_ONE)
    assert app.next(auto=True) == "t0"  # the track ended: repeat it
    assert app.next() == "t1"  # Next pressed (upstream restarted the track here)
    app_queue.add_tracks_to_queue(app, [Track("X")])
    assert app.next(auto=True) == "t1"  # repeat-one still repeats
    assert app.next() == "X"


def test_removing_a_queued_row_drops_it_from_up_next():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app_queue.on_queue_remove_track_clicked(app, app.index_of("X"))
    assert up_next.pending(app) == []
    app.play_track(app.index_of("t2"))
    assert "X" not in app.names() and app.next() == "t3"


def test_queue_entries_are_copies_so_a_track_can_be_queued_from_the_playing_album():
    app = FakeApp()
    playing = app.play_queue[0]
    app_queue.play_tracks_next(app, [playing])
    assert app.play_queue[1] is not playing and app.play_queue[1].name == "t0"
    assert app.next() == "t0" and app.current_track_index == 1


def test_prefetch_and_next_agree_on_the_queued_track():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    assert up_next.peek(app).name == "X"
    assert app.play_queue[playback_actions.get_next_index(app)].name == "X"
    assert app.next() == "X" and up_next.peek(app) is None


def test_rows_of_queued_tracks_are_marked():
    app = FakeApp()
    entry = up_next.add(app, [Track("X")])[0]

    class Row:
        css = []

        def add_css_class(self, name):
            self.css.append(name)

    row = Row()
    assert up_next.mark_row(app, row, entry) is True and row.css == ["queue-up-next"]
    assert up_next.mark_row(app, Row(), app.play_queue[0]) is False
