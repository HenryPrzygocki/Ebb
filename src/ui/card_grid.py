"""Fork (#17): card grids whose covers fill the row, at a chosen card size.

A grid card's cover is a square as wide as its column. Each cover asks for a base width, set by
the card size (Small, Medium, Large: Settings > General, or Ctrl+= / Ctrl+- / Ctrl+0 anywhere).
The grid fits as many columns of that width as the row has room for and shares out the rest, so
every row ends flush with the page. Upstream drew fixed 238 px covers (at scale 1) centred in
whatever width the column had, which left loose gaps around them on wide windows, and offered
no way to see more of a library at once.

Covers load somewhat above their base width, so they stay sharp in the widest column. Their
rounded corners come from CSS (the shape class: `album-cover-img`, `circular-avatar`) instead of
being baked into the bitmap, so the radius stays the same at any width.

Track cards, list rows and search carousels keep their fixed covers.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

SETTING = "card_size"
SIZES = ("small", "medium", "large")
LABELS = ("Small", "Medium", "Large")
DEFAULT = "medium"
# Spread so that each step changes the column count at common widths (743, 1007, 1396 px of
# content: 4/5/8, 3/4/6 and 2/3/5 columns of album covers).
_FACTOR = {"small": 0.66, "medium": 0.84, "large": 1.1}
# Covers load this much above their base width: sharp up to the widest column of three or more.
TEXTURE_SCALE = 1.3
# A column narrower than its base width (a window too narrow for one) shrinks the cover this far.
MIN_SIDE = 96

_current = DEFAULT


def current():
    return _current


def factor():
    return _FACTOR.get(_current, 1.0)


def base(size):
    """The width a cover of nominal `size` asks for at the current card size."""
    return max(64, int(round(int(size) * factor())))


def texture_size(size):
    return int(round(base(size) * TEXTURE_SCALE))


class CoverSlot(Gtk.Widget):
    """The cover's square: asks for its base width and is as tall as it is wide."""

    __gtype_name__ = "EbbCoverSlot"

    def __init__(self, size):
        super().__init__()
        self.size = int(size)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        side = base(self.size)
        if orientation == Gtk.Orientation.HORIZONTAL:
            return min(side, MIN_SIDE), side, -1, -1
        if for_size >= 0:
            side = for_size
        return side, side, -1, -1


def cover(url, cache_dir, size, shape="album-cover-img", icon="audio-x-generic-symbolic"):
    """A grid card's cover. `url` is a URL, a cached file or a callable giving one, or None.

    The icon shows while the artwork loads, and stays when there is none."""
    import utils.helpers as utils

    overlay = Gtk.Overlay(css_classes=["home-feed-media", "card-cover", shape], valign=Gtk.Align.START)
    overlay.set_child(CoverSlot(size))
    if icon:
        overlay.add_overlay(
            Gtk.Image(
                icon_name=icon,
                pixel_size=max(16, min(48, base(size) // 3)),
                halign=Gtk.Align.CENTER,
                valign=Gtk.Align.CENTER,
                css_classes=["card-cover-icon"],
            )
        )
    picture = Gtk.Picture(css_classes=[shape], can_shrink=True, content_fit=Gtk.ContentFit.COVER)
    picture.set_overflow(Gtk.Overflow.HIDDEN)  # clips to the shape's border-radius
    overlay.add_overlay(picture)
    tint = Gtk.Box(css_classes=["home-feed-tint", shape], can_target=False)
    overlay.add_overlay(tint)
    picture.cache_dir = cache_dir
    if url:
        utils.load_img(picture, url, cache_dir, texture_size(size), fit=True)
    overlay.picture = picture
    return overlay


def _sharpen(slot):
    """After a step up, reload a cover whose bitmap is now below its texture size (from the
    disk cache: load_img resolved and fetched it the first time)."""
    picture = getattr(slot.get_parent(), "picture", None)
    url = getattr(picture, "_target_url", None)
    loaded = getattr(picture, "_loaded_pixbuf", None)
    want = texture_size(slot.size)
    if not url or loaded is None or loaded.get_width() >= want:
        return
    import utils.helpers as utils

    utils.load_img(picture, url, picture.cache_dir, want, fit=True)


def _walk(widget):
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _walk(child)
        child = child.get_next_sibling()


def fit_labels(card):
    """Let a card's title and subtitle span the card (ellipsized at its edge) without widening
    the column: their natural width stays under any base width."""
    for widget in _walk(card):
        if isinstance(widget, Gtk.Label) and (
            widget.has_css_class("home-card-title") or widget.has_css_class("home-card-subtitle")
        ):
            widget.set_halign(Gtk.Align.FILL)
            widget.set_xalign(0.5)
            widget.set_width_chars(-1)
            widget.set_max_width_chars(6)


def install(app):
    global _current
    name = str((getattr(app, "settings", None) or {}).get(SETTING) or DEFAULT)
    _current = name if name in SIZES else DEFAULT


def set_size(app, name):
    """Switch the card size; open grids reflow at once. True when it changed."""
    global _current
    if name not in SIZES or name == _current:
        return False
    _current = name
    settings = getattr(app, "settings", None)
    if isinstance(settings, dict):
        settings[SETTING] = name
        save = getattr(app, "schedule_save_settings", None)
        if callable(save):
            save()
    win = getattr(app, "win", None)
    if win is not None:
        for widget in _walk(win):
            if isinstance(widget, CoverSlot):
                widget.queue_resize()
                _sharpen(widget)
    dropdown = getattr(app, "card_size_dd", None)
    if dropdown is not None and dropdown.get_selected() != SIZES.index(name):
        dropdown.set_selected(SIZES.index(name))
    return True


def step(app, delta):
    """One size bigger (+1) or smaller (-1), stopping at the ends."""
    i = max(0, min(len(SIZES) - 1, SIZES.index(_current) + int(delta)))
    return set_size(app, SIZES[i])
