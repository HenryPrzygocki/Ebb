"""Fork: the bottom panel is the Lyrics & DSP panel; the spectrum visualizer is opt-in.

Upstream floated a chevron handle above the middle of the player bar. It opened a panel with
three tabs, Spectrum first: a spectrum analyser and DR meter, the lyrics, and the DSP workspace.
The visualizer was the first thing the handle showed, and it isn't something most people
need on screen.

Now:
- The handle is gone. The panel opens from the DSP button (on its DSP tab) and with E, and has
  its own close button. Lyrics are also in Now Playing.
- The Spectrum tab appears only with Settings > General > Spectrum Visualizer, off by default.
  While its tab isn't showing, nothing is analysed (_sync_spectrum_stream_state).
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

SETTING = "show_spectrum"


def enabled(app):
    return bool((getattr(app, "settings", None) or {}).get(SETTING, False))


def _spectrum_page(app):
    stack, viz = getattr(app, "viz_stack", None), getattr(app, "viz", None)
    if stack is None or viz is None:
        return None
    return stack.get_page(viz)


def apply(app):
    """Show or hide the Spectrum tab per the setting; leave it if it is showing and now hidden."""
    page = _spectrum_page(app)
    if page is None:
        return
    on = enabled(app)
    page.set_visible(on)
    stack = app.viz_stack
    if not on and stack.get_visible_child_name() == "spectrum":
        stack.set_visible_child_name("lyrics")


def set_enabled(app, on):
    settings = getattr(app, "settings", None)
    if isinstance(settings, dict):
        settings[SETTING] = bool(on)
        save = getattr(app, "schedule_save_settings", None)
        if callable(save):
            save()
    apply(app)
    if on and getattr(app, "viz_stack", None) is not None:
        app.viz_stack.set_visible_child_name("spectrum")  # show what was just turned on


def close_button(app):
    """A close tab for the right end of the panel's tab row, styled as the tabs and dropdowns
    there (.viz-theme-dd button): a plain flat button would sit unseen on whatever page the
    row overlaps."""
    button = Gtk.Button(icon_name="hiresti-pan-down-symbolic", css_classes=["viz-close-btn"], tooltip_text="Close (E)")

    def _close(_button):
        revealer = getattr(app, "viz_revealer", None)
        if revealer is not None and revealer.get_reveal_child():
            app.toggle_visualizer(None)

    button.connect("clicked", _close)
    tab = Gtk.Box(css_classes=["viz-theme-dd", "viz-close-tab"], valign=Gtk.Align.END)
    tab.append(button)
    return tab


def settings_row(app):
    """The Settings > General row that turns the Spectrum tab on."""
    row = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
    info.append(Gtk.Label(label="Spectrum Visualizer", xalign=0, css_classes=["settings-label"]))
    info.append(
        Gtk.Label(
            label="Adds a Spectrum tab, with a dynamic-range meter, to the Lyrics & DSP panel (E).",
            xalign=0,
            wrap=True,
            css_classes=["dim-label"],
        )
    )
    row.append(info)
    switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=enabled(app))
    switch.connect("notify::active", lambda s, _p: set_enabled(app, s.get_active()))
    app.spectrum_switch = switch
    row.append(switch)
    return row
