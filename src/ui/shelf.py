"""Fork: Home and Top sections are shelves: one row of cards, and "Show all" for the rest.

Each section was a full grid of its cards (about ten). At half a 1920 px screen Home was nine
screens tall, and its first screen showed nothing but the first section. A shelf shows the
row the window has room for; "Show all" opens the rest in place and "Show less" folds it.

The row follows the window and the card size (Ctrl+= / Ctrl+-): whenever the shelf's width,
its first card's natural width or its card count changes, it counts the cards that fit and
pins the grid to that many columns, so the expanded grid starts with the same row.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

SPACING = 16
MAX_PER_LINE = 16


def fit(width, card_width, spacing=SPACING):
    """How many cards of `card_width` fit in `width`, `spacing` apart: at least one."""
    if card_width <= 0:
        return 1
    return max(1, min(MAX_PER_LINE, (int(width) + spacing) // (int(card_width) + spacing)))


def shows(index, columns, expanded):
    """Whether the card at `index` is on show. Before the first count only the first card is,
    so a section never flashes as a full grid."""
    return bool(expanded) or index < max(1, int(columns or 0))


def button_state(count, columns, expanded, pending=0):
    """(visible, label) for the "Show all" button: there only when one row doesn't hold them.
    `pending`: cards not built yet (see Shelf.reset)."""
    visible = columns > 0 and count + max(0, int(pending or 0)) > columns
    return visible, ("Show less" if expanded else "Show all")


class Shelf(Gtk.FlowBox):
    """A section's cards: one row, or all of them once `button` ("Show all") is clicked."""

    __gtype_name__ = "EbbShelf"

    def __init__(self, button=None):
        super().__init__(
            homogeneous=False,
            min_children_per_line=1,
            max_children_per_line=MAX_PER_LINE,
            column_spacing=SPACING,
            row_spacing=SPACING,
            selection_mode=Gtk.SelectionMode.NONE,
        )
        self.expanded = False
        self.columns = 0  # unknown until the first card is measured
        self._seen = None
        self._idle = 0
        self._button = button
        self._pending, self._fill = 0, None
        self.set_filter_func(lambda child: shows(child.get_index(), self.columns, self.expanded))
        if button is not None:
            button.connect("clicked", lambda _b: self.toggle())
        self._sync_button()

    def count(self):
        n, child = 0, self.get_first_child()
        while child is not None:
            n += 1
            child = child.get_next_sibling()
        return n

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded and self._fill is not None:
            fill, self._fill, self._pending = self._fill, None, 0
            fill(self)  # the cards past the first ones are built on the first "Show all"
        self.invalidate_filter()
        self._sync_button()

    def reset(self, pending=0, fill=None):
        """For a shelf that is refilled (the album page's "More by"): folded again. `fill(shelf)`
        appends the `pending` cards not built yet, on the first "Show all"."""
        self.expanded = False
        self._pending, self._fill = (max(0, int(pending)), fill) if fill is not None else (0, None)
        self._seen = None
        self.invalidate_filter()
        self.queue_resize()
        self._sync_button()

    def do_size_allocate(self, width, height, baseline):
        Gtk.FlowBox.do_size_allocate(self, width, height, baseline)
        first = self.get_child_at_index(0)
        if first is None:
            return
        seen = (width, first.measure(Gtk.Orientation.HORIZONTAL, -1)[1], self.count())
        if seen != self._seen:
            self._seen = seen
            # Changing the layout while it is being allocated would re-enter it; next idle.
            if not self._idle:
                self._idle = GLib.idle_add(self._recount)

    def _recount(self):
        self._idle = 0
        if self._seen is None:  # reset() since this was queued: the next allocation re-measures
            return False
        width, card, _count = self._seen
        columns = fit(width, card, self.get_column_spacing())
        if columns != self.columns:
            self.columns = columns
            self.set_max_children_per_line(columns)
            self.invalidate_filter()
        self._sync_button()
        return False

    def _sync_button(self):
        if self._button is None:
            return
        visible, label = button_state(self.count(), self.columns, self.expanded, self._pending)
        self._button.set_visible(visible)
        self._button.set_label(label)


def heading(title):
    """A section heading with its "Show all" button: (row, button) for Shelf(button=)."""
    head = Gtk.Box(spacing=8, margin_top=4)
    head.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["home-section-title"]))
    more = Gtk.Button(label="Show all", css_classes=["flat", "home-section-more"], valign=Gtk.Align.CENTER)
    head.append(more)
    return head, more
