"""Fork: "Hi-Res only", a discreet filter for track lists that mix qualities: playlists, mixes,
Liked Songs, search results.

The switch is a small chip in the list's toolbar, drawn like the Hi-Res badge on the rows it
keeps. It shows only where it can change something, a list with both Hi-Res and other tracks.
Album pages never get it: an album is one quality throughout. A list with no Hi-Res tracks
doesn't either, as the filter would empty it.

It is one switch for the session: turned on in one playlist, it applies to the next mixed list
as well, whose chip shows lit. Play all, Shuffle and playing a row queue the filtered list,
which is the list shown.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ui import track_table  # noqa: E402


def is_hires(track):
    return track_table.track_quality_tier(track) == "hires"


def count(tracks):
    """(Hi-Res tracks, all tracks)."""
    tracks = list(tracks or [])
    return sum(1 for t in tracks if is_hires(t)), len(tracks)


def mixed(tracks):
    hires, total = count(tracks)
    return 0 < hires < total


def active(app):
    return bool(getattr(app, "hires_only", False))


def apply(app, tracks, scope=None):
    """`tracks`, keeping only the Hi-Res ones while the filter is on. `scope` is the whole list
    `tracks` was narrowed from (a search within it, say); the filter applies when that whole
    list mixes qualities. By default, `tracks` is the whole list."""
    tracks = list(tracks or [])
    if active(app) and mixed(tracks if scope is None else scope):
        return [t for t in tracks if is_hires(t)]
    return tracks


def _ids(tracks):
    return [getattr(t, "id", None) for t in tracks]


def for_track_page(app, tracks, album_page):
    """The tracks the generic track page (playlists, mixes, search results) shows.

    The page re-renders what it shows (select mode, for one), so a list equal to the one shown
    keeps the full list it came from, and turning the filter off restores that."""
    tracks = list(tracks or [])
    source = tracks
    if getattr(app, "_hires_source", None) is not None and _ids(tracks) == getattr(app, "_hires_shown_ids", None):
        source = app._hires_source
    app._hires_source = source
    shown = source if album_page else apply(app, source)
    app._hires_shown_ids = _ids(shown)
    chip = getattr(app, "hires_chip", None)
    if chip is not None:
        chip.sync([] if album_page else source)
    return shown


class Chip(Gtk.ToggleButton):
    """The switch. `on_change` re-renders the list it sits on."""

    def __init__(self, app, on_change):
        super().__init__(css_classes=["hires-filter-chip"], valign=Gtk.Align.CENTER, visible=False)
        box = Gtk.Box(spacing=4)
        self._check = Gtk.Image(icon_name="object-select-symbolic", pixel_size=12, visible=False)
        box.append(self._check)
        box.append(Gtk.Label(label="Hi-Res"))
        self.set_child(box)
        self._app = app
        self._on_change = on_change
        self._syncing = False
        self.connect("toggled", self._toggled)

    def _toggled(self, _btn):
        self._check.set_visible(self.get_active())
        if self._syncing:
            return
        self._app.hires_only = self.get_active()
        self._on_change()

    def sync(self, tracks):
        """Show the chip for a mixed list, lit while the filter is on."""
        hires, total = count(tracks)
        self.set_visible(0 < hires < total)
        self._syncing = True
        try:
            self.set_active(active(self._app))
        finally:
            self._syncing = False
        self._check.set_visible(self.get_active())
        if self.get_active():
            self.set_tooltip_text(f"Showing the {hires} Hi-Res tracks of {total}. Click to show all.")
        else:
            self.set_tooltip_text(f"Show only the {hires} Hi-Res tracks of {total}")
