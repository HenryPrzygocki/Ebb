"""Fork #27: Home sections made of tracks show columns of compact rows."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
pytest.importorskip("gi")

from gi.repository import Gdk  # noqa: E402

from actions import ui_actions  # noqa: E402


def _items(n, typ="Track"):
    return [{"type": typ, "name": f"T{i}", "obj": SimpleNamespace(id=i, name=f"T{i}")} for i in range(n)]


def test_only_all_track_sections_become_columns():
    assert ui_actions._is_track_section(_items(5))
    assert not ui_actions._is_track_section(_items(1))
    assert not ui_actions._is_track_section(_items(3) + _items(1, "Album"))


def test_columns_fill_top_to_bottom_three_at_a_time():
    groups = ui_actions._track_columns(_items(7))
    assert [[i for i, _ in g] for g in groups] == [[0, 1, 2], [3, 4, 5], [6]]


def test_a_track_plays_its_section_from_there():
    calls = []
    app = SimpleNamespace(
        grid_title_label=SimpleNamespace(get_text=lambda: "Home"),
        _set_play_queue=lambda tracks: calls.append(("queue", [t.id for t in tracks])),
        play_track=lambda i: calls.append(("play", i)),
    )
    items = _items(4)
    items[1]["obj"] = None  # an item the backend couldn't parse is skipped, not played
    ui_actions._play_track_section(app, items, 2, "Recommended new tracks")
    assert calls == [("queue", [0, 2, 3]), ("play", 1)]
    assert app.playback_source == {"type": "Home", "name": "Recommended new tracks"}


class _Node:
    def __init__(self, parent=None, visible=True):
        self.parent, self.kids, self.visible = parent, [], visible
        if parent is not None:
            parent.kids.append(self)

    def get_parent(self):
        return self.parent

    def get_child(self):
        return self.kids[0] if self.kids else None

    def get_first_child(self):
        return self.kids[0] if self.kids else None

    def _sib(self, step):
        sibs = self.parent.kids
        i = sibs.index(self) + step
        return sibs[i] if 0 <= i < len(sibs) else None

    def get_next_sibling(self):
        return self._sib(1)

    def get_prev_sibling(self):
        return self._sib(-1)

    def get_child_visible(self):
        return self.visible

    def is_ancestor(self, _other):
        return False


def _shelf(*rows_per_column, hidden_from=None):
    flow = _Node()
    cols = []
    for n, rows in enumerate(rows_per_column):
        cell = _Node(flow, visible=hidden_from is None or n < hidden_from)
        col = _Node(cell)
        for _ in range(rows):
            _Node(col)
        cols.append(col)
    return cols


def test_up_down_stay_in_the_column_and_fall_through_at_its_ends():
    a, _b = _shelf(3, 3)
    t = a.kids
    assert ui_actions._track_column_step(a, t[0], Gdk.KEY_Down) is t[1]
    assert ui_actions._track_column_step(a, t[1], Gdk.KEY_Up) is t[0]
    assert ui_actions._track_column_step(a, t[2], Gdk.KEY_Down) is None
    assert ui_actions._track_column_step(a, t[0], Gdk.KEY_Up) is None


def test_left_right_keep_the_row_and_skip_folded_columns():
    a, b, c = _shelf(3, 2, 3, hidden_from=2)
    assert ui_actions._track_column_step(a, a.kids[2], Gdk.KEY_Right) is b.kids[1]  # clamped to b's last
    assert ui_actions._track_column_step(b, b.kids[0], Gdk.KEY_Left) is a.kids[0]
    assert ui_actions._track_column_step(b, b.kids[1], Gdk.KEY_Right) is None  # c is folded away
    assert ui_actions._track_column_step(a, a.kids[0], Gdk.KEY_Left) is None


# Fork #27: Liked Songs grows as you scroll instead of paging.
def _t(*ids):
    return [SimpleNamespace(id=i) for i in ids]


def test_an_unlike_is_recognised_as_a_pure_removal():
    assert ui_actions.liked_removed_ids(_t(1, 2, 3, 4), _t(1, 3, 4)) == {2}
    assert ui_actions.liked_removed_ids(_t(1, 2, 3, 4), _t(1, 4)) == {2, 3}
    assert ui_actions.liked_removed_ids(_t(1, 2, 3), _t(1, 2, 3)) is None  # nothing removed
    assert ui_actions.liked_removed_ids(_t(1, 2, 3), _t(1, 3, 2)) is None  # reordered: rebuild
    assert ui_actions.liked_removed_ids(_t(1, 2, 3), _t(1, 9)) is None  # something added: rebuild
    assert ui_actions.liked_removed_ids([], []) is None


def test_liked_list_grows_only_near_the_bottom_and_while_rows_remain():
    # 50 rows built of 205; a 900 px view over 2500 px of content
    assert not ui_actions.liked_wants_more(50, 205, value=0, page=900, upper=2500)
    assert ui_actions.liked_wants_more(50, 205, value=800, page=900, upper=2500)
    assert ui_actions.liked_wants_more(50, 205, value=0, page=1400, upper=1400)  # tall window, short list
    assert not ui_actions.liked_wants_more(205, 205, value=1600, page=900, upper=2500)
