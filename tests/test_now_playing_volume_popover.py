"""Fork: Now Playing's volume popover fits above its button instead of flipping down over the controls.

In the narrow layout the button sits about 250 px below the window's top; the popover was 277 px
tall, so GTK opened it downward over the progress bar and the transport buttons."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_now_playing as np  # noqa: E402


def test_the_slider_keeps_its_full_height_where_it_fits():
    # Wide layouts: the button is ~860 px down the window (sandbox, 954 and 1912 px tiles).
    assert np._np_volume_scale_height(856, 249, 150) == 150


def test_the_narrow_layout_gives_up_slider_height_to_open_above():
    # Measured in the sandbox at 571 and 763: button at y 247, content 249 px with a 150 px slider.
    height = np._np_volume_scale_height(247, 249, 150)
    assert height == 112
    surface = 249 - 150 + height + np._NP_VOLUME_POPOVER_CHROME
    assert surface <= 247  # opened above, top edge on screen even with the window at the screen's top


def test_extra_content_comes_out_of_the_slider_but_never_below_the_floor():
    # Per-channel hardware sliders make the content taller; the slider shrinks, down to 90 px.
    assert np._np_volume_scale_height(400, 249 + 60, 150) == 150
    assert np._np_volume_scale_height(247, 249 + 60, 150) == np._NP_VOLUME_SCALE_MIN
    assert np._np_volume_scale_height(0, 249, 150) == np._NP_VOLUME_SCALE_MIN


class _Scale:
    def __init__(self, height=150, visible=True):
        self.height, self.visible = height, visible

    def get_visible(self):
        return self.visible

    def get_size_request(self):
        return (-1, self.height)

    def set_size_request(self, _w, h):
        self.height = h


def _app(button_y, scale):
    popped = []
    content = SimpleNamespace(measure=lambda _o, _f: (249 - 150 + scale.height, 249 - 150 + scale.height, -1, -1))
    pop = SimpleNamespace(get_child=lambda: content, popup=lambda: popped.append(True))
    bounds = SimpleNamespace(get_y=lambda: button_y)
    btn = SimpleNamespace(compute_bounds=lambda _w: (True, bounds))
    return SimpleNamespace(now_playing_vol_pop=pop, now_playing_vol_btn=btn, now_playing_vol_scale=scale, win=object()), popped


def test_a_click_fits_the_slider_then_opens_and_a_wide_layout_restores_it():
    scale = _Scale()
    app, popped = _app(247, scale)
    np._popup_now_playing_volume(app)
    assert scale.height == 112 and popped == [True]
    wide, popped = _app(856, scale)
    np._popup_now_playing_volume(wide)
    assert scale.height == 150 and popped == [True]


def test_bit_perfect_without_a_slider_just_opens():
    scale = _Scale(visible=False)
    app, popped = _app(247, scale)
    np._popup_now_playing_volume(app)
    assert scale.height == 150 and popped == [True]
