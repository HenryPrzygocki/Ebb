"""Fork: Shuffle and Repeat are separate controls (actions/play_modes.py)."""
import os
import random
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from actions import play_modes, playback_actions  # noqa: E402
from actions.play_modes import REPEAT_ALL, REPEAT_OFF, REPEAT_ONE  # noqa: E402


class _Player:
    def __init__(self):
        self.stop_calls = 0

    def get_position(self):
        return (0.0, 180.0)

    def stop(self):
        self.stop_calls += 1


def _app(mode, n=5, current=0):
    app = SimpleNamespace(MODE_NORMAL=4, MODE_LOOP=0, MODE_ONE=1, MODE_SHUFFLE=2, MODE_SMART=3)
    app.play_mode = mode
    app.current_track_list = [SimpleNamespace(id=i) for i in range(n)]
    app.current_track_index = current
    app.shuffle_indices = []
    app.settings = {}
    app.saves = 0
    app.schedule_save_settings = lambda: setattr(app, "saves", app.saves + 1)
    app.player = _Player()
    app.played = []
    app._get_active_queue = lambda: app.current_track_list

    def generate():
        app._shuffle_order = None
        rest = [i for i in range(len(app.current_track_list)) if i != app.current_track_index]
        random.shuffle(rest)
        app.shuffle_indices = rest

    def play_track(index):  # what record_track_change does to the shuffle order
        entry = app.current_track_list[index]
        order = getattr(app, "_shuffle_order", None)
        if order is not None:
            app._shuffle_order = [e for e in order if e is not entry]
        app.current_track_index = index
        app.played.append(index)

    app._generate_shuffle_list = generate
    app.play_track = play_track
    return app


def test_every_shuffle_and_repeat_pair_has_one_mode():
    pairs = {play_modes.split(m) for m in (0, 1, 2, 4, 5, 6)}
    assert len(pairs) == 6
    for mode in (0, 1, 2, 4, 5, 6):
        assert play_modes.join(*play_modes.split(mode)) == mode
    assert play_modes.split(3) == (True, REPEAT_ALL)  # Smart Shuffle was Shuffle
    assert play_modes.normalize(3) == 2
    assert play_modes.normalize(999) == 4 and play_modes.normalize(None) == 4
    assert play_modes.normalize("5") == 5


def test_each_button_changes_only_its_own_half():
    app = _app(0)  # repeat all
    play_modes.toggle_shuffle(app)
    assert play_modes.split(app.play_mode) == (True, REPEAT_ALL)
    play_modes.cycle_repeat(app)
    assert play_modes.split(app.play_mode) == (True, REPEAT_ONE)
    play_modes.cycle_repeat(app)
    assert play_modes.split(app.play_mode) == (True, REPEAT_OFF)
    play_modes.cycle_repeat(app)
    assert play_modes.split(app.play_mode) == (True, REPEAT_ALL)
    play_modes.toggle_shuffle(app)
    assert play_modes.split(app.play_mode) == (False, REPEAT_ALL)
    assert app.settings["play_mode"] == app.play_mode == 0 and app.saves == 5


def test_changing_repeat_keeps_the_shuffled_order():
    app = _app(4)
    play_modes.set_mode(app, 2)
    nxt = playback_actions.get_next_index(app, 1)  # builds the order
    order = app._shuffle_order
    play_modes.cycle_repeat(app)
    assert app._shuffle_order is order and playback_actions.get_next_index(app, 1) == current_or(nxt, app)
    play_modes.toggle_shuffle(app)
    assert app._shuffle_order is None and app.shuffle_indices == []


def current_or(nxt, app):
    # Under Repeat One the track that follows at its end is itself.
    return app.current_track_index if play_modes.repeat(app) == REPEAT_ONE else nxt


def test_shuffle_without_repeat_plays_every_track_once_then_stops():
    app = _app(5, n=6, current=0)
    app._generate_shuffle_list()
    for _ in range(5):
        expected = playback_actions.get_next_index(app, 1)  # what gapless prefetch would queue
        playback_actions.on_next_track(app, auto=True)
        assert app.played[-1] == expected
    assert sorted(app.played) == [1, 2, 3, 4, 5]
    assert playback_actions.get_next_index(app, 1) == -1  # gapless queues nothing at the end
    playback_actions.on_next_track(app, auto=True)
    assert len(app.played) == 5 and app.player.stop_calls == 1
    playback_actions.on_next_track(app)  # after the stop, Next starts a new shuffled pass
    assert len(app.played) == 6


def test_shuffle_with_repeat_all_keeps_going():
    app = _app(2, n=4, current=0)
    app._generate_shuffle_list()
    for _ in range(10):
        playback_actions.on_next_track(app, auto=True)
    assert len(app.played) == 10 and app.player.stop_calls == 0
    assert all(a != b for a, b in zip(app.played, app.played[1:]))


def test_repeat_one_repeats_at_the_end_and_next_moves_on():
    app = _app(1, n=4, current=2)
    playback_actions.on_next_track(app, auto=True)
    assert app.played == [2]
    playback_actions.on_next_track(app)
    assert app.played == [2, 3]
    app = _app(6, n=4, current=2)  # with Shuffle: Next draws from the shuffled order
    app._generate_shuffle_list()
    playback_actions.on_next_track(app, auto=True)
    playback_actions.on_next_track(app)
    assert app.played[0] == 2 and app.played[1] != 2


def test_repeat_off_without_shuffle_stops_at_the_end():
    app = _app(4, n=3, current=2)
    assert playback_actions.get_next_index(app, 1) == -1
    playback_actions.on_next_track(app, auto=True)
    assert app.played == [] and app.player.stop_calls == 1
