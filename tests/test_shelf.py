"""Fork #27: Home and Top sections show one row of cards, "Show all" for the rest (ui/shelf.py)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui import shelf  # noqa: E402


def test_the_row_holds_as_many_cards_as_fit():
    # 3 cards of 230 px and two 16 px gaps need 722 px.
    assert shelf.fit(722, 230) == 3
    assert shelf.fit(721, 230) == 2
    assert shelf.fit(100, 230) == 1  # a window too narrow for one still shows one
    assert shelf.fit(10_000, 100) == shelf.MAX_PER_LINE
    assert shelf.fit(800, 0) == 1  # nothing measured yet


def test_a_lone_card_per_row_becomes_two_smaller_ones():
    # 420 px window: a 402 px search shelf of 199 px album cards (minimum 96), 24 apart.
    assert shelf.fit(402, 199, 24, card_min=96) == 2
    # Home's track columns: their minimum is their width, so one stays one.
    assert shelf.fit(402, 260, 16, card_min=260) == 1
    # Not below SHRINK of the natural width.
    assert shelf.fit(250, 199, 24, card_min=96) == 1


def test_one_row_until_shown_all():
    assert [shelf.shows(i, 3, False) for i in range(5)] == [True, True, True, False, False]
    assert all(shelf.shows(i, 3, True) for i in range(5))
    # Before the first count only the first card shows: no flash of the full grid.
    assert [shelf.shows(i, 0, False) for i in range(3)] == [True, False, False]


def test_the_button_is_there_only_when_one_row_does_not_hold_them():
    assert shelf.button_state(10, 3, False) == (True, "Show all")
    assert shelf.button_state(10, 3, True) == (True, "Show less")
    assert shelf.button_state(3, 3, False)[0] is False
    assert shelf.button_state(3, 3, False, pending=5) == (True, "Show all")  # cards not built yet count
    assert shelf.button_state(10, 0, False)[0] is False  # not counted yet


def test_a_recount_queued_before_a_reset_does_nothing():
    """reset() clears the measurement; a recount already queued must not unpack it."""
    from types import SimpleNamespace
    stand_in = SimpleNamespace(_idle=7, _seen=None)  # no real widget: GTK needs a display
    assert shelf.Shelf._recount(stand_in) is False
    assert stand_in._idle == 0
