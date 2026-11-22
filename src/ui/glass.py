"""Fork: Ebb's own window translucency ("glass").

The window's backgrounds turn translucent, so the compositor's blur behind the window shows
through (niri: `background-effect { blur true }`). Everything drawn on those backgrounds stays
solid: text, icons, album covers, artist pictures. A compositor `opacity` window rule fades
all of those as well, which is why Ebb does this itself; exempt Ebb from any such rule (niri:
`opacity 1.0` for its app-id).

One layer carries the translucency: the window background. Large surfaces inside the window
(lists, grids, header bars) become transparent so that one layer shows through evenly;
stacked translucent layers would make some regions murkier than others. The player bar gets
a light extra tint of its own, so it reads slightly more solid than the content.

Anything that floats over Ebb's own content stays opaque: the floating sidebar, the queue
drawers, popovers, menus, dialogs, Now Playing. The compositor blurs only what is behind the
window; Ebb's own content under a translucent panel would show through sharp, text over text.

Light mode gets less transparency than dark: a light surface over a darker wallpaper turns
grey quickly.

The setting is `window_transparency`, from 0 (off) to MAX.
"""
import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk  # noqa: E402

logger = logging.getLogger(__name__)

SETTING = "window_transparency"
DEFAULT = 0.25
MAX = 0.6
LIGHT_SHARE = 0.6  # light mode uses this share of the transparency
BAR_TINT = 0.35  # the player bar's own fill, over the window's
CSS_CLASS = "ebb-glass"
PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2  # above Ebb's stylesheet and scale overrides


def amount(settings):
    """The transparency setting, clamped to [0, MAX]."""
    try:
        value = float((settings or {}).get(SETTING, DEFAULT))
    except (TypeError, ValueError):
        value = DEFAULT
    return max(0.0, min(MAX, value))


def opacity(transparency, dark):
    """The window background's opacity for a transparency setting, in the given mode."""
    return 1.0 - transparency * (1.0 if dark else LIGHT_SHARE)


def css(transparency, dark):
    """The stylesheet for one transparency and mode: empty when off. Every rule is scoped to
    the main window (it alone carries CSS_CLASS), so other windows and dialogs are untouched."""
    if transparency <= 0:
        return ""
    base = opacity(transparency, dark)
    card = 0.06 if dark else 0.45  # a lift of white, as cards are lighter than the window
    w = f"window.{CSS_CLASS}"
    # Cards: libadwaita's variable, not a background override, so Ebb's hover and checked
    # styles on cards still apply (this provider's priority would beat them).
    return f"""
{w}.background {{ background-color: alpha(@window_bg_color, {base:.3f}); --card-bg-color: alpha(white, {card}); }}

{w} banner > revealer > widget {{ background-color: alpha(currentColor, 0.08); }}

{w} headerbar,
{w} toolbarview > .top-bar,
{w} toolbarview > .bottom-bar,
{w} .view,
{w} listview,
{w} gridview,
{w} columnview,
{w} list,
{w} textview > text {{ background-color: transparent; }}

{w} .card-bar {{ background-color: alpha(@headerbar_bg_color, {BAR_TINT:.3f}); }}
"""


class _Glass:
    def __init__(self, app):
        self.app = app
        self.loaded = None
        self.provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), self.provider, PRIORITY)
        self.style = Adw.StyleManager.get_default()
        self.style.connect("notify::dark", lambda *_a: self.refresh())

    def refresh(self):
        transparency = amount(getattr(self.app, "settings", None))
        text = css(transparency, bool(self.style.get_dark()))
        if text != self.loaded:
            self.provider.load_from_string(text)
            self.loaded = text
        win = getattr(self.app, "win", None)
        if win is not None:
            if transparency > 0:
                win.add_css_class(CSS_CLASS)
            else:
                win.remove_css_class(CSS_CLASS)


def install(app):
    """Call once the main window exists."""
    try:
        app._glass = _Glass(app)
        app._glass.refresh()
    except Exception:
        logger.exception("Window transparency could not be set up")


def set_amount(app, value):
    """Settings slider: apply a new transparency now, save it shortly after."""
    app.settings[SETTING] = max(0.0, min(MAX, float(value)))
    glass = getattr(app, "_glass", None)
    if glass is not None:
        glass.refresh()
    if hasattr(app, "schedule_save_settings"):
        app.schedule_save_settings()
