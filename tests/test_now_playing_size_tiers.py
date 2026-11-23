"""Fork: how Now Playing shares its window. The cover panel is as wide as the cover can use and
the tabs (Queue/Album/Lyrics) get the rest; a window too narrow for both puts the track info
above the tabs; text grows with the room it gets.

The sizes below are Henry's niri tiles on a 1920 x 1080 output: columns at 0.3-0.7 of the width
and full width, 1030 px tall. The overlay's surface is 60 px narrower than the window and
about 957 px tall."""
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from app import app_now_playing as np  # noqa: E402
from ui import config as ui_config  # noqa: E402

Gtk = np.Gtk
H = 957  # the surface's height in a 1030 px tall tile
INFO = 297  # the track info's height with a one-line title


# --- the split -----------------------------------------------------------------------------

def test_the_cover_panel_is_only_as_wide_as_the_cover_can_use():
    # 0.7 of the screen. Upstream: a 915 px panel around a 576 px cover, 402 px for the tabs.
    left, right = np._now_playing_split_widths(1277, H, INFO)
    room = H - np._NOW_PLAYING_TOP_BAR_H - INFO - np._NOW_PLAYING_CONTENT_INSET
    assert room == 576
    assert left == room + 2 * (np._NOW_PLAYING_CONTENT_INSET + np._NOW_PLAYING_COVER_BREATH) == 660
    assert right == 595
    assert left + right + np._NOW_PLAYING_CONTENT_INSET == 1277


def test_tight_windows_share_the_width_instead_of_starving_the_tabs():
    assert np._now_playing_split_widths(1085, H, INFO) == (575, 488)  # 0.6: the tabs' 46 %
    assert np._now_playing_split_widths(894, H, INFO) == (452, 420)  # 0.5: the tabs' minimum


def test_past_what_the_tabs_can_use_the_width_goes_around_the_cover():
    left, right = np._now_playing_split_widths(1852, H, INFO)  # full width
    assert (left, right) == (870, np._NOW_PLAYING_RIGHT_CAP_W)
    # ... but only while the cover keeps its share of the panel: it is still stacked.
    assert np._now_playing_cover_box(left, H, INFO) == (147, 62, 576)


def test_a_window_too_short_for_a_stacked_cover_gets_the_compact_info_panel():
    # Half the screen's height: 71 px would be left for a cover above the info.
    assert np._now_playing_split_widths(1085, 452, INFO) == (np._NOW_PLAYING_COMPACT_LEFT_W, 603)
    assert np._now_playing_split_widths(1852, 452, INFO) == (np._NOW_PLAYING_COMPACT_LEFT_W, 1370)


def test_the_split_without_a_height_is_still_upstreams_ratio():
    assert np._now_playing_split_widths(1000) == (587, 391)


def test_narrow_is_when_the_two_panels_cannot_both_fit():
    assert np._now_playing_is_narrow(511)  # 0.3 of the screen, Henry's default column
    assert np._now_playing_is_narrow(703)  # 0.4
    assert not np._now_playing_is_narrow(894)  # 0.5
    edge = np._NOW_PLAYING_LEFT_MIN_W + np._NOW_PLAYING_RIGHT_MIN_W + np._NOW_PLAYING_CONTENT_INSET
    assert np._now_playing_is_narrow(edge - 1) and not np._now_playing_is_narrow(edge)


# --- the size tiers ------------------------------------------------------------------------

def _tiers_for_surface(w, h):
    _left, right = np._now_playing_split_widths(w, h)
    return np._now_playing_size_tiers(np._now_playing_cover_metric(w, h), right, h)


def test_tiers_on_a_1080p_screen():
    assert _tiers_for_surface(894, H) == ("", "")
    assert _tiers_for_surface(1085, H) == ("", "")
    assert _tiers_for_surface(1277, H) == ("np-right-m", "")
    assert _tiers_for_surface(1852, H) == ("np-right-l", "")


def test_the_default_window_keeps_the_base_sizes():
    assert _tiers_for_surface(1220, 977) == ("", "")  # 1280 x 1040


def test_a_1440p_window_gets_the_largest_sizes_on_both_sides():
    assert _tiers_for_surface(2500, 1377) == ("np-right-xl", "np-left-xl")


def test_a_wide_but_short_window_is_held_back_by_its_height():
    assert _tiers_for_surface(2000, 600) == ("np-right-m", "")


def test_the_left_tier_reads_only_the_window():
    # The measured cover would feed back: a bigger title makes the info taller and the cover
    # smaller, so at a threshold the tier would switch itself off and on again.
    import inspect

    assert list(inspect.signature(np._now_playing_cover_metric).parameters) == ["surface_w", "surface_h"]
    assert np._now_playing_cover_metric(1852, H) == H - np._NOW_PLAYING_TOP_BAR_H - 300 - 22 == 573
    assert np._now_playing_cover_metric(894, H) < 573  # a narrow window: the width limits it


class _Surface:
    def __init__(self):
        self.classes = {"now-playing-surface"}

    def has_css_class(self, name):
        return name in self.classes

    def add_css_class(self, name):
        self.classes.add(name)

    def remove_css_class(self, name):
        self.classes.discard(name)


def test_tier_classes_follow_resizes_and_report_changes():
    app = SimpleNamespace(now_playing_surface=_Surface())
    assert np._apply_now_playing_size_tiers(app, 993, 1101, 1377) is True
    assert {"np-right-xl", "np-left-xl"} <= app.now_playing_surface.classes
    assert np._apply_now_playing_size_tiers(app, 993, 1101, 1377) is False  # nothing to redo
    assert np._apply_now_playing_size_tiers(app, 573, 420, H) is True
    assert app.now_playing_surface.classes == {"now-playing-surface"}
    # Fakes without CSS-class methods (older tests) are left alone.
    assert np._apply_now_playing_size_tiers(SimpleNamespace(now_playing_surface=object()), 993, 1101, 1377) is False


def _px(selector):
    m = re.search(re.escape(selector) + r"\s*\{[^}]*font-size:\s*([\d.]+)(px|em)", ui_config.CSS_DATA)
    assert m, f"no font-size rule for {selector}"
    return float(m.group(1))


def test_every_tier_is_styled_and_each_step_is_bigger():
    lyric = [_px(f".{t} .now-playing-lyrics-box .lyric-line") for t in ("np-right-m", "np-right-l", "np-right-xl")]
    active = [_px(f".{t} .now-playing-lyrics-box .lyric-line.active") for t in ("np-right-m", "np-right-l", "np-right-xl")]
    rows = [_px(f".{t} .now-playing-track-row") for t in ("np-right-m", "np-right-l", "np-right-xl")]
    titles = [_px(f".{t} .now-playing-title") for t in ("np-left-l", "np-left-xl")]
    assert 16 < lyric[0] < lyric[1] < lyric[2]  # base .lyric-line is 16px
    assert 20 < active[0] < active[1] < active[2]  # base active line is 20px
    assert 1.0 < rows[0] < rows[1] < rows[2]
    assert 30 < titles[0] < titles[1]  # base .now-playing-title is 30px
    assert _px(".np-compact .now-playing-title") < 30  # beside the thumb the title has less room
    for name in np._NOW_PLAYING_TIER_CLASSES + ("np-narrow", "np-compact"):
        assert f".{name} " in ui_config.CSS_DATA


# --- the layout, on fake widgets -------------------------------------------------------------

class _W:
    """Records what the layout code sets. `heights` maps a card width to the info's height."""

    def __init__(self, heights=None):
        self.req, self.margins = (-1, -1), [0, 0]
        self.halign = self.hexpand = self.orientation = None
        self.vexpand = self.visible = True
        self.classes, self.draws, self.heights = set(), 0, heights

    def get_width_request(self):
        return self.req[0]

    def get_height_request(self):
        return self.req[1]

    def set_size_request(self, w, h):
        self.req = (w, h)

    def get_margin_start(self):
        return self.margins[0]

    def get_margin_end(self):
        return self.margins[1]

    def set_margin_start(self, v):
        self.margins[0] = v

    def set_margin_end(self, v):
        self.margins[1] = v

    def get_halign(self):
        return self.halign

    def set_halign(self, v):
        self.halign = v

    def set_hexpand(self, v):
        self.hexpand = v

    def get_vexpand(self):
        return self.vexpand

    def set_vexpand(self, v):
        self.vexpand = v

    def get_visible(self):
        return self.visible

    def set_visible(self, v):
        self.visible = v

    def has_css_class(self, name):
        return name in self.classes

    def add_css_class(self, name):
        self.classes.add(name)

    def remove_css_class(self, name):
        self.classes.discard(name)

    def set_orientation(self, v):
        self.orientation = v

    def queue_draw(self):
        self.draws += 1

    def measure(self, _orientation, for_size):
        # As GTK: the widget's own margins are inside the width it is measured for.
        return (0, self.heights(for_size - sum(self.margins)), -1, -1)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(np, "_now_playing_album_column", True)
    monkeypatch.setattr(np, "_now_playing_album_chars", 14)
    monkeypatch.setattr(np.GLib, "idle_add", lambda *_a: 0)
    return SimpleNamespace(
        now_playing_surface=_W(),
        now_playing_layout=_W(),
        now_playing_left_stage=_W(),
        now_playing_right_panel=_W(),
        now_playing_meta_panel=_W(heights=lambda _w: INFO),
        now_playing_progress_box=_W(),
        now_playing_art_img=_W(),
        now_playing_thumb=_W(),
        now_playing_queue_list=None,
        now_playing_track_list=None,
    )


def _layout(app, w, h):
    narrow = np._now_playing_is_narrow(w)
    np._set_now_playing_narrow(app, narrow)
    (np._sync_now_playing_narrow if narrow else np._sync_now_playing_wide)(app, w, h)


def test_wide_the_cover_stacks_and_the_card_lines_up_with_it(app):
    _layout(app, 1277, H)
    assert app.now_playing_layout.orientation == Gtk.Orientation.HORIZONTAL
    assert app.now_playing_left_stage.req == (660, -1) and app.now_playing_right_panel.req == (595, -1)
    assert app.now_playing_art_img._cover_box == (42, 62, 576)
    # The card is the cover's width: margins, not a size request.
    assert app.now_playing_meta_panel.margins == [42, 42] and app.now_playing_meta_panel.req == (-1, -1)
    assert app.now_playing_meta_panel.halign == Gtk.Align.FILL
    assert app.now_playing_progress_box.req == (-1, -1)  # it made the card 42 px wider than asked
    assert not app.now_playing_thumb.visible and not app.now_playing_art_img._cover_backdrop
    assert app.now_playing_surface.classes == {"np-right-m"}


def test_a_long_title_shrinks_the_cover_but_not_the_panels(app):
    # Three lines at the card's width; one line when nothing wraps.
    app.now_playing_meta_panel.heights = lambda w: INFO if w >= 2000 else 385
    _layout(app, 1277, H)
    assert app.now_playing_left_stage.req == (660, -1) and app.now_playing_right_panel.req == (595, -1)
    assert app.now_playing_art_img._cover_box == (86, 62, 488)
    assert app.now_playing_meta_panel.margins == [42, 42]


def test_the_info_is_measured_at_the_cards_width_whatever_margins_are_left(app):
    seen = []
    app.now_playing_meta_panel.heights = lambda w: seen.append(w) or INFO
    app.now_playing_meta_panel.margins = [205, 205]  # left by a 2560 px layout
    _layout(app, 1277, H)
    assert seen == [np._NOW_PLAYING_UNWRAPPED_W, 576]


def test_a_short_wide_window_shows_the_compact_card(app):
    _layout(app, 1085, 452)
    assert app.now_playing_left_stage.req == (460, -1) and app.now_playing_right_panel.req == (603, -1)
    assert getattr(app.now_playing_art_img, "_cover_box", None) is None  # no cover in the panel
    assert app.now_playing_art_img._cover_backdrop is True and app.now_playing_thumb.visible
    assert app.now_playing_meta_panel.margins == [22, 22]
    assert "np-compact" in app.now_playing_surface.classes and "np-narrow" not in app.now_playing_surface.classes


def test_narrow_puts_the_info_above_the_tabs(app):
    _layout(app, 511, H)  # the default 0.3 column: upstream clipped the card in a 149 px panel
    assert app.now_playing_layout.orientation == Gtk.Orientation.VERTICAL
    block = np._NOW_PLAYING_TOP_BAR_H + INFO
    assert app.now_playing_left_stage.req == (-1, block) and app.now_playing_left_stage.vexpand is False
    assert app.now_playing_left_stage.halign == Gtk.Align.FILL
    assert app.now_playing_right_panel.visible and app.now_playing_right_panel.req == (-1, -1)
    assert app.now_playing_thumb.visible and app.now_playing_art_img._cover_backdrop is True
    assert app.now_playing_art_img._cover_narrow is True  # both top corners round
    assert app.now_playing_meta_panel.margins == [22, 22]
    assert {"np-narrow", "np-compact"} <= app.now_playing_surface.classes


def test_narrow_and_wide_enough_for_bigger_lyrics(app):
    _layout(app, 703, H)  # 0.4 of the screen
    assert "np-right-m" in app.now_playing_surface.classes


def test_narrow_and_too_short_for_the_tabs_keeps_the_info(app):
    _layout(app, 511, 452)  # half the screen's height
    assert app.now_playing_right_panel.visible is False
    assert app.now_playing_left_stage.vexpand is True and app.now_playing_left_stage.req == (-1, -1)


def test_widening_again_restores_the_side_by_side_layout(app):
    _layout(app, 511, 452)
    _layout(app, 1277, H)
    assert app.now_playing_layout.orientation == Gtk.Orientation.HORIZONTAL
    assert app.now_playing_right_panel.visible and app.now_playing_left_stage.vexpand is True
    assert app.now_playing_left_stage.halign == Gtk.Align.CENTER
    assert not app.now_playing_thumb.visible and app.now_playing_art_img._cover_narrow is False
    assert app.now_playing_surface.classes == {"np-right-m"}


def test_the_queue_handle_hides_while_now_playing_is_open():
    anchor = _W()
    app = SimpleNamespace(queue_anchor=anchor)
    np._set_queue_handle_visible(app, False)
    assert anchor.visible is False
    np._set_queue_handle_visible(app, True)
    assert anchor.visible is True
    np._set_queue_handle_visible(SimpleNamespace(), False)  # no drawer built: nothing to do


def test_closing_now_playing_does_not_show_the_handle_when_signed_out():
    from app import app_auth

    anchor, viz = _W(), _W()
    app = SimpleNamespace(
        queue_anchor=anchor, viz_handle_box=viz, is_now_playing_overlay_open=lambda: False, close_queue_drawer=lambda: None
    )
    app_auth._set_overlay_handles_visible(app, False)  # signed out
    np._set_queue_handle_visible(app, True)  # the overlay's close
    assert anchor.visible is False
    app_auth._set_overlay_handles_visible(app, True)  # signed in again
    assert anchor.visible is True and viz.visible is True


def test_signing_in_under_an_open_overlay_keeps_the_handle_hidden():
    from app import app_auth

    anchor = _W()
    app = SimpleNamespace(queue_anchor=anchor, viz_handle_box=None, is_now_playing_overlay_open=lambda: True)
    anchor.visible = False
    app_auth._set_overlay_handles_visible(app, True)
    assert anchor.visible is False
    np._set_queue_handle_visible(app, True)  # the overlay closes
    assert anchor.visible is True


def test_q_with_now_playing_open_shows_its_queue_tab_not_the_hidden_drawer():
    from app import app_queue

    shown = []
    revealer = SimpleNamespace(get_reveal_child=lambda: False, set_reveal_child=lambda v: shown.append(("drawer", v)))
    app = SimpleNamespace(
        is_now_playing_overlay_open=lambda: True,
        now_playing_stack=SimpleNamespace(set_visible_child_name=lambda name: shown.append(("tab", name))),
        queue_revealer=revealer,
    )
    app_queue.toggle_queue_drawer(app)
    assert shown == [("tab", "queue")]


# --- the album column ------------------------------------------------------------------------

def test_the_album_column_widens_in_steps_with_the_panel():
    assert np._now_playing_album_chars_for(480) == 14  # the width every panel had
    assert np._now_playing_album_chars_for(600) == 18
    assert np._now_playing_album_chars_for(865) == 22
    assert np._now_playing_album_chars_for(1145) == 30
    assert np._now_playing_album_chars_for(3000) == 30


class _Node:
    def __init__(self, classes=(), children=()):
        self.classes, self.children = set(classes), list(children)
        self.visible, self.chars, self.max_chars, self.parent_next = True, 14, 14, None

    def has_css_class(self, name):
        return name in self.classes

    def get_first_child(self):
        return self.children[0] if self.children else None

    def get_next_sibling(self):
        return self.parent_next

    def set_visible(self, v):
        self.visible = v

    def set_width_chars(self, n):
        self.chars = n

    def set_max_width_chars(self, n):
        self.max_chars = n


def _tree(*children):
    root = _Node(children=children)
    for a, b in zip(children, children[1:]):
        a.parent_next = b
    return root


def test_rows_already_built_take_the_new_album_width(monkeypatch):
    monkeypatch.setattr(np, "_now_playing_album_column", True)
    monkeypatch.setattr(np, "_now_playing_album_chars", 14)
    album_a, album_b = _Node({"now-playing-track-album"}), _Node({"now-playing-track-album"})
    title = _Node({"track-title"})
    app = SimpleNamespace(now_playing_queue_list=_tree(_tree(title, album_a)), now_playing_track_list=_tree(album_b))

    np._set_now_playing_album_column(app, True, 30)
    assert (album_a.chars, album_a.max_chars, album_b.chars) == (30, 30, 30)
    assert title.chars == 14  # only the album cells
    np._set_now_playing_album_column(app, False)  # keeps the width, hides the column
    assert not album_a.visible and album_a.chars == 30 and np._now_playing_album_chars == 30
