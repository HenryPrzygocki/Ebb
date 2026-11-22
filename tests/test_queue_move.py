"""Fork #10: reorder the queue (app_queue.move_queue_entry)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_queue  # noqa: E402


class App(SimpleNamespace):
    def _get_active_queue(self):
        return list(self.play_queue)

    def _refresh_queue_views(self):
        return False


def _app(n=8, current=2, up=()):
    q = [SimpleNamespace(id=i) for i in range(n)]
    return App(play_queue=q, current_track_index=current, up_next=[q[i] for i in up]), q


def _ids(app):
    return [e.id for e in app.play_queue]


def test_a_move_keeps_the_playing_track_and_its_index_in_step():
    app, q = _app()
    assert app_queue.move_queue_entry(app, q[6], 0)  # above the playing track
    assert _ids(app) == [6, 0, 1, 2, 3, 4, 5, 7]
    assert app.play_queue[app.current_track_index] is q[2]
    assert app_queue.move_queue_entry(app, q[0], 8)  # to the bottom
    assert _ids(app) == [6, 1, 2, 3, 4, 5, 7, 0]
    assert app.play_queue[app.current_track_index] is q[2]


def test_no_op_drops_and_the_playing_track_itself():
    app, q = _app()
    assert not app_queue.move_queue_entry(app, q[5], 5)
    assert not app_queue.move_queue_entry(app, q[5], 6)
    assert not app_queue.move_queue_entry(app, q[2], 7)  # playing
    assert not app_queue.move_queue_entry(app, SimpleNamespace(id=99), 0)  # not queued
    assert _ids(app) == list(range(8))


def test_dropped_right_after_the_playing_track_it_plays_next_in_any_mode():
    app, q = _app()
    assert app_queue.move_queue_entry(app, q[6], 3)
    assert _ids(app)[:4] == [0, 1, 2, 6]
    assert app.up_next == [q[6]]


def test_up_next_follows_the_order_shown():
    app, q = _app(up=(3, 4))  # playing 2, then Up Next 3, 4
    assert app_queue.move_queue_entry(app, q[7], 4)  # between 3 and 4
    assert _ids(app)[:6] == [0, 1, 2, 3, 7, 4]
    assert app.up_next == [q[3], q[7], q[4]]
    assert app_queue.move_queue_entry(app, q[4], 3)  # to the front of Up Next
    assert app.up_next == [q[4], q[3], q[7]]


def test_a_track_dropped_after_the_up_next_block_joins_it_at_the_end():
    app, q = _app(up=(3, 4))
    assert app_queue.move_queue_entry(app, q[7], 5)
    assert _ids(app)[:6] == [0, 1, 2, 3, 4, 7]
    assert app.up_next == [q[3], q[4], q[7]]


def test_an_up_next_track_dragged_away_becomes_an_ordinary_one():
    app, q = _app(up=(3, 4))
    assert app_queue.move_queue_entry(app, q[3], 8)
    assert _ids(app) == [0, 1, 2, 4, 5, 6, 7, 3]
    assert app.up_next == [q[4]]
    assert app_queue.move_queue_entry(app, q[4], 0)  # above the playing track
    assert app.up_next == []


def test_with_nothing_playing_it_only_reorders():
    app, q = _app(current=-1)
    assert app_queue.move_queue_entry(app, q[0], 3)
    assert _ids(app)[:3] == [1, 2, 0]
    assert app.up_next == [] and app.current_track_index == -1


def test_the_playing_index_zero_is_not_nothing_playing():
    from ui import queue_dnd

    assert queue_dnd.current_index(SimpleNamespace(current_track_index=0)) == 0  # was `int(x or -1)`: -1
    assert queue_dnd.current_index(SimpleNamespace(current_track_index=None)) == -1
    assert queue_dnd.current_index(SimpleNamespace()) == -1
