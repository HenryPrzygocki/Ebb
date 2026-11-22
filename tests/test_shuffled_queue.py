"""Fork: Shuffle reorders the queue itself, so the queue views show the order tracks will play in,
and turning Shuffle off brings the original order back (actions/play_modes.py)."""
import os
import random
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import play_modes, playback_actions, up_next  # noqa: E402
from app import app_queue  # noqa: E402

NORMAL, SHUFFLE, SHUFFLE_ONCE = 4, 2, 5


def _track(i):
    return SimpleNamespace(id=i, name=f"t{i}")


def _app(n=8, mode=NORMAL):
    tracks = [_track(i) for i in range(n)]
    app = SimpleNamespace(
        play_queue=[], current_track_list=list(tracks), current_track_index=-1, play_mode=mode,
        shuffle_indices=[], _play_history=[], up_next=[], settings={}, heard=[],
        player=SimpleNamespace(stops=0),
    )
    app.player.stop = lambda: setattr(app.player, "stops", app.player.stops + 1)
    app.schedule_save_settings = lambda: None
    app._get_active_queue = lambda: app_queue._get_active_queue(app)
    app._set_play_queue = lambda items: app_queue._set_play_queue(app, items)

    def play_track(index, from_history=False, engine_advanced=False):
        # The queue bookkeeping of lyrics_playback_actions.play_track, in its order.
        queue = app._get_active_queue()
        left = getattr(app, "_current_queue_entry", None)
        playback_actions.record_track_change(app, queue, queue[index], from_history=from_history)
        app.current_track_index = index
        play_modes.track_started(app, changed=left is not queue[index])
        up_next.settle(app)
        app.heard.append(app.play_queue[app.current_track_index].id)

    app.play_track = play_track
    return app, tracks


def _ids(app):
    return [e.id for e in app.play_queue]


def _next(app):
    playback_actions.on_next_track(app, auto=True)


def test_shuffle_on_puts_the_queue_in_the_order_it_will_play():
    random.seed(1)
    app, tracks = _app(8)
    app._set_play_queue(tracks)
    app.play_track(0)
    _next(app)
    _next(app)
    play_modes.toggle_shuffle(app)  # Repeat stays off
    assert app.play_mode == SHUFFLE_ONCE
    ids = _ids(app)
    assert ids[:3] == [0, 1, 2] and app.current_track_index == 2  # heard, then the playing track
    assert sorted(ids[3:]) == [3, 4, 5, 6, 7]
    for _ in range(5):
        _next(app)
    assert app.heard[3:] == ids[3:]  # exactly what the queue showed
    assert app.player.stops == 0
    _next(app)
    assert app.player.stops == 1  # each track once, then the end


def test_shuffle_off_restores_the_order_and_play_goes_on_from_the_playing_track():
    random.seed(2)
    app, tracks = _app(8)
    app._set_play_queue(tracks)
    app.play_track(0)
    play_modes.toggle_shuffle(app)
    _next(app)
    _next(app)
    playing = app.heard[-1]
    play_modes.toggle_shuffle(app)
    assert _ids(app) == list(range(8))
    assert app.current_track_index == playing
    if playing < 7:
        _next(app)
        assert app.heard[-1] == playing + 1


def test_a_page_shuffle_turns_shuffle_on_and_off_brings_the_list_order_back():
    random.seed(3)
    app, tracks = _app(8)
    app_queue.play_tracks_now(app, tracks, shuffle=True)
    assert play_modes.shuffle_on(app)
    assert app.current_track_index == 0 and _ids(app)[0] == app.heard[0]
    assert sorted(_ids(app)) == list(range(8))
    upcoming = _ids(app)[1:]
    for _ in range(7):
        _next(app)
    assert app.heard[1:] == upcoming
    play_modes.toggle_shuffle(app)
    assert _ids(app) == list(range(8))


def test_a_new_queue_under_shuffle_is_shuffled_around_the_track_played():
    random.seed(4)
    app, tracks = _app(8, mode=SHUFFLE)
    app._set_play_queue(tracks)
    app.play_track(5)
    assert app.current_track_index == 0 and _ids(app)[0] == 5
    assert sorted(_ids(app)) == list(range(8))
    play_modes.toggle_shuffle(app)
    assert _ids(app) == list(range(8)) and app.current_track_index == 5


def test_an_insert_keeps_the_shuffled_order_and_the_album_played_again_reshuffles():
    random.seed(5)
    app, tracks = _app(8, mode=SHUFFLE)
    app._set_play_queue(tracks)
    app.play_track(0)
    assert _ids(app) != list(range(8))
    shuffled = list(app.play_queue)
    edited = list(shuffled)
    extra = _track(99)
    edited.insert(1, extra)  # the other tracks keep their order: an edit
    app._set_play_queue(edited)
    assert play_modes.preshuffled(app) and _ids(app) == [e.id for e in edited]
    _next(app)
    assert app.heard[-1] == 99
    # The album page plays it again, in album order: a new queue, shuffled around the track.
    app._set_play_queue(tracks)
    assert not play_modes.preshuffled(app)
    app.play_track(3)
    assert _ids(app)[0] == 3 and play_modes.preshuffled(app)
    assert sorted(_ids(app)) == list(range(8))


def test_up_next_stays_next_when_shuffle_turns_on_and_off():
    random.seed(6)
    app, tracks = _app(8)
    app._set_play_queue(tracks)
    app.play_track(2)
    (queued,) = up_next.add(app, [_track(99)])
    play_modes.toggle_shuffle(app)
    assert app.play_queue[app.current_track_index].id == 2
    assert app.play_queue[app.current_track_index + 1] is queued
    play_modes.toggle_shuffle(app)
    assert app.play_queue[app.current_track_index + 1] is queued
    assert [e.id for e in app.play_queue if e is not queued] == list(range(8))
    _next(app)
    assert app.heard[-1] == 99


def test_repeat_all_plays_every_track_each_pass_and_off_still_restores():
    random.seed(7)
    app, tracks = _app(6, mode=SHUFFLE)
    app._set_play_queue(tracks)
    app.play_track(0)
    for _ in range(17):
        _next(app)
    passes = [app.heard[i:i + 6] for i in (0, 6, 12)]
    assert all(sorted(p) == list(range(6)) for p in passes)
    assert all(a != b for a, b in zip(app.heard, app.heard[1:]))
    play_modes.toggle_shuffle(app)
    assert _ids(app) == list(range(6))


def test_next_after_the_end_starts_a_new_shuffled_pass():
    random.seed(8)
    app, tracks = _app(5, mode=SHUFFLE_ONCE)
    app._set_play_queue(tracks)
    app.play_track(0)
    for _ in range(5):
        _next(app)
    assert app.player.stops == 1 and sorted(app.heard) == list(range(5))
    last = app.heard[-1]
    assert app.play_queue[app.current_track_index].id == last
    for _ in range(4):
        playback_actions.on_next_track(app)
    assert sorted(app.heard[5:]) == sorted(set(range(5)) - {last})


def test_repeat_one_on_the_first_track_of_a_pass_keeps_the_order():
    random.seed(9)
    app, tracks = _app(5, mode=SHUFFLE)
    app._set_play_queue(tracks)
    app.play_track(0)
    for _ in range(4):
        _next(app)  # the last track of the pass
    last = app.play_queue[-1]
    _next(app)  # round to the first track: the rest is shuffled again
    assert app.current_track_index == 0
    # As when the new order happens to end on the track heard last: the wrap test holds again.
    app.play_queue = [e for e in app.play_queue if e is not last] + [last]
    assert play_modes._wrapped(app)
    play_modes.cycle_repeat(app)  # Repeat All -> One
    order = _ids(app)
    for _ in range(3):
        _next(app)  # the track ends and plays again
    assert _ids(app) == order and app.current_track_index == 0


def test_removing_the_playing_track_keeps_the_shuffled_order():
    random.seed(10)
    app, tracks = _app(8, mode=SHUFFLE)
    app._set_play_queue(tracks)
    app.play_track(0)
    _next(app)
    playing = app.play_queue[app.current_track_index]
    rest = [e for e in app.play_queue if e is not playing]
    app._set_play_queue(rest)
    assert play_modes.preshuffled(app) and _ids(app) == [e.id for e in rest]
    play_modes.toggle_shuffle(app)
    assert _ids(app) == [i for i in range(8) if i != playing.id]
