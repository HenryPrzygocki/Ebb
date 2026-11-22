"""Fork: page controls for the paged lists (Liked Songs, Artists, History, search results).

Upstream put "Prev" and "Next" text buttons in the toolbars, on Liked Songs right after
"Play all" and "Shuffle", where they read as previous / next track. Nothing showed which page
was open or how many there were, and the controls stayed (greyed out) when everything fit on
one page.

Now a pager is two arrows around "2 / 5", hidden when there is a single page. Liked Songs has
one above and one below its list, so the end of a page is not a dead end.
"""
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


class Pager(Gtk.Box):
    """"‹ 2 / 5 ›". `on_prev` and `on_next` are called with the clicked button."""

    def __init__(self, on_prev, on_next, **kwargs):
        super().__init__(spacing=2, valign=Gtk.Align.CENTER, css_classes=["ebb-pager"], visible=False, **kwargs)
        self.prev = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat", "circular"], tooltip_text="Previous page")
        self.label = Gtk.Label(css_classes=["dim-label", "ebb-pager-label"])
        self.next = Gtk.Button(icon_name="go-next-symbolic", css_classes=["flat", "circular"], tooltip_text="Next page")
        self.prev.connect("clicked", lambda button: on_prev(button))
        self.next.connect("clicked", lambda button: on_next(button))
        self.append(self.prev)
        self.append(self.label)
        self.append(self.next)

    def update(self, page, pages):
        """Show page `page` (from 0) of `pages`."""
        pages = max(1, int(pages or 1))
        page = max(0, min(int(page or 0), pages - 1))
        self.set_visible(pages > 1)
        self.label.set_text(f"{page + 1} / {pages}")
        self.label.set_tooltip_text(f"Page {page + 1} of {pages}")
        self.prev.set_sensitive(page > 0)
        self.next.set_sensitive(page < pages - 1)


def arrows(prev_btn, next_btn):
    """Make an upstream pair of "Prev" / "Next" text buttons page arrows."""
    for button, icon in ((prev_btn, "go-previous-symbolic"), (next_btn, "go-next-symbolic")):
        button.set_icon_name(icon)
        button.remove_css_class("liked-action-btn")
        button.add_css_class("circular")
        button.set_valign(Gtk.Align.CENTER)


def sync(prev_btn, next_btn, page, pages):
    """Sensitivity and "2 / 5", all hidden when everything fits on one page."""
    pages = max(0, int(pages or 0))
    for button in (prev_btn, next_btn):
        button.set_visible(pages > 1)
    prev_btn.set_sensitive(page > 0)
    next_btn.set_sensitive(page < pages - 1)
    show_page(prev_btn, page, pages)


def show_page(prev_btn, page, pages):
    """"2 / 5" between a pair of arrows (arrows()), as on Liked Songs: the Albums and Artists
    pagers were two bare arrows. The label goes in once the arrows are in their box, and shows
    only when there are several pages."""
    get_parent = getattr(prev_btn, "get_parent", None)
    parent = get_parent() if callable(get_parent) else None
    if parent is None or not hasattr(parent, "insert_child_after"):
        return
    label = getattr(prev_btn, "_ebb_pager_label", None)
    if label is None:
        label = Gtk.Label(css_classes=["dim-label", "ebb-pager-label"], valign=Gtk.Align.CENTER)
        prev_btn._ebb_pager_label = label
        parent.insert_child_after(label, prev_btn)
    pages = max(0, int(pages or 0))
    label.set_visible(pages > 1)
    if pages > 1:
        label.set_text(f"{page + 1} / {pages}")
        label.set_tooltip_text(f"Page {page + 1} of {pages}")
