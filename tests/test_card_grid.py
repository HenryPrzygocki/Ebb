"""Fork #17: cover grids that fill the row, at a chosen card size (ui/card_grid.py)."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from ui import card_grid  # noqa: E402


@pytest.fixture(autouse=True)
def _medium():
    card_grid._current = card_grid.DEFAULT
    yield
    card_grid._current = card_grid.DEFAULT


class DropDown:
    def __init__(self, selected):
        self.selected = selected

    def get_selected(self):
        return self.selected

    def set_selected(self, i):
        self.selected = i


def _app(**settings):
    app = SimpleNamespace(settings=dict(settings), saves=0, win=None, card_size_dd=DropDown(1))
    app.schedule_save_settings = lambda: setattr(app, "saves", app.saves + 1)
    return app


def test_sizes_scale_the_nominal_cover():
    assert card_grid.base(238) == 200  # medium, the default
    card_grid._current = "small"
    assert card_grid.base(238) == 157
    card_grid._current = "large"
    assert card_grid.base(238) == 262  # upstream drew 238 at every width
    assert card_grid.base(80) == 88
    card_grid._current = "small"
    assert card_grid.base(80) == 64  # floor


def test_covers_load_above_their_base_so_wide_columns_stay_sharp():
    assert card_grid.texture_size(238) == round(200 * card_grid.TEXTURE_SCALE)
    assert card_grid.texture_size(238) > card_grid.base(238)


def test_install_reads_the_setting_and_ignores_junk():
    card_grid.install(_app(card_size="large"))
    assert card_grid.current() == "large"
    card_grid.install(_app(card_size="huge"))
    assert card_grid.current() == card_grid.DEFAULT
    card_grid.install(SimpleNamespace())
    assert card_grid.current() == card_grid.DEFAULT


def test_set_size_saves_and_moves_the_settings_dropdown():
    app = _app()
    assert card_grid.set_size(app, "large")
    assert app.settings["card_size"] == "large" and app.saves == 1
    assert app.card_size_dd.selected == card_grid.SIZES.index("large")
    assert not card_grid.set_size(app, "large")  # no change, no save
    assert not card_grid.set_size(app, "huge")
    assert app.saves == 1


def test_steps_stop_at_the_ends():
    app = _app()
    assert card_grid.step(app, +1) and card_grid.current() == "large"
    assert not card_grid.step(app, +1)
    assert card_grid.step(app, -1) and card_grid.step(app, -1) and card_grid.current() == "small"
    assert not card_grid.step(app, -1)


def _display():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    from gi.repository import Gdk, Gtk

    return bool(Gtk.init_check()) and Gdk.Display.get_default() is not None


def test_the_cover_slot_is_square_at_any_width():
    if not _display():
        pytest.skip("needs a display")
    from gi.repository import Gtk

    slot = card_grid.CoverSlot(238)
    assert slot.get_request_mode() == Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH
    minimum, natural, _b1, _b2 = slot.measure(Gtk.Orientation.HORIZONTAL, -1)
    assert natural == 200 and minimum == card_grid.MIN_SIDE
    assert slot.measure(Gtk.Orientation.VERTICAL, 300)[:2] == (300, 300)
    card_grid._current = "large"
    slot.queue_resize()
    assert slot.measure(Gtk.Orientation.HORIZONTAL, -1)[1] == 262
