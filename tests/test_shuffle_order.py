"""Fork #9: shuffle without replacement, Play Next honoured, prefetch agrees with Next, and
Previous/Next walk the history by queue entry across queue edits."""
import os
import random
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import playback_actions  # noqa: E402
from app import app_queue  # noqa: E402

SHUFFLE, NORMAL = 2, 4


def _track(i):
    return SimpleNamespace(id=i, name=f"t{i}")


def _app(n=10, mode=SHUFFLE):
    queue = [_track(i) for i in range(n)]
    seeks = []
    app = SimpleNamespace(
        play_queue=list(queue), current_track_list=list(queue), current_track_index=0,
        play_mode=mode, MODE_NORMAL=4, MODE_LOOP=0, MODE_ONE=1, MODE_SHUFFLE=2, MODE_SMART=3,
        shuffle_indices=[], _play_history=[], playing_track=None, seeks=seeks,
        player=SimpleNamespace(get_position=lambda: (1.0, 200.0), seek=lambda pos: seeks.append(pos)),
        _refresh_queue_views=lambda: None, _update_track_list_icon=lambda: None,
    )
    app._get_active_queue = lambda: app_queue._get_active_queue(app)
    app._set_play_queue = lambda tracks: app_queue._set_play_queue(app, tracks)

    def gen():
        idx = [i for i in range(len(app.play_queue)) if i != app.current_track_index]
        random.shuffle(idx)
        app.shuffle_indices = idx
        app._shuffle_order = None

    def play_track(index, from_history=False):
        q = app._get_active_queue()
        playback_actions.record_track_change(app, q, q[index], from_history=from_history)
        app.current_track_index = index
        app.playing_track = q[index]

    app._generate_shuffle_list = gen
    app.play_track = play_track
    play_track(0)
    return app


def _next(app):
    q = app._get_active_queue()
    app.play_track(playback_actions._choose_shuffle_index(app, app.current_track_index, len(q)))
    return app.playing_track


def test_shuffle_plays_every_track_once_per_cycle():
    app = _app(10)
    heard = [_next(app).id for _ in range(9)]
    assert sorted(heard) == list(range(1, 10))


def test_shuffle_keeps_going_after_a_cycle_without_immediate_repeats():
    app = _app(4)
    heard = [_next(app).id for _ in range(12)]
    assert all(a != b for a, b in zip(heard, heard[1:]))


def test_prefetch_prediction_matches_the_track_next_plays():
    app = _app(20)
    for _ in range(6):
        predicted = playback_actions.get_next_index(app, 1)
        assert playback_actions.get_next_index(app, 1) == predicted
        played = _next(app)
        assert app._get_active_queue()[predicted] is played


def test_play_next_plays_next_under_shuffle():
    app = _app(10)
    _next(app)
    _next(app)
    queued = _track(99)
    app_queue._insert_queue_next(app, [queued])
    assert _next(app) is queued


def test_add_to_queue_joins_the_shuffle_cycle():
    app = _app(5)
    queued = _track(99)
    app_queue._insert_queue_at(app, [queued], len(app.play_queue), event_reason="queue_appended")
    heard = sorted(_next(app).id for _ in range(5))
    assert heard == [1, 2, 3, 4, 99]


def test_previous_after_play_next_returns_to_the_track_heard():
    app = _app(10)
    first = _next(app)
    _next(app)
    app_queue._insert_queue_next(app, [_track(99)])  # shifts every index after the current one
    playback_actions.on_prev_track(app)
    assert app.playing_track is first


def test_previous_survives_removing_an_earlier_queue_item():
    app = _app(10)
    start = app.playing_track
    a = _next(app)
    b = _next(app)
    _next(app)
    app_queue.on_queue_remove_track_clicked(app, app.play_queue.index(start))
    playback_actions.on_prev_track(app)
    assert app.playing_track is b
    playback_actions.on_prev_track(app)
    assert app.playing_track is a
    playback_actions.on_prev_track(app)  # the start track is gone: restart instead
    assert app.playing_track is a
    assert app.seeks == [0.0]


def test_previous_then_next_returns_to_the_track_left():
    app = _app(10)
    _next(app)
    b = _next(app)
    c = _next(app)
    playback_actions.on_prev_track(app)
    assert app.playing_track is b
    assert _next(app) is c


def test_first_previous_in_a_new_queue_restarts_instead_of_jumping():
    app = _app(50)
    for _ in range(5):
        _next(app)
    fresh = [_track(1000 + i) for i in range(50)]
    app._set_play_queue(fresh)
    app.play_track(0)
    playback_actions.on_prev_track(app)
    assert app.playing_track is fresh[0]
    assert app.seeks == [0.0]


def test_previous_at_the_first_track_in_normal_mode_restarts_instead_of_wrapping():
    app = _app(5, mode=NORMAL)
    playback_actions.on_prev_track(app)
    assert app.current_track_index == 0
    assert app.seeks == [0.0]
