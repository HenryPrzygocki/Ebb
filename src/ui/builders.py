import gi
import logging
import os
import subprocess
import sys
import time

_viz_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'viz')
if _viz_dir not in sys.path:
    sys.path.insert(0, _viz_dir)

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Adw, Pango, GLib, Gdk
from core import brand  # fork
from ui import dialogs  # fork

from background_viz import BackgroundVisualizer
from visualizer import HybridVisualizer as _HybridVisualizer
from dr_meter import LevelMonitor
from ui import config as ui_config
from ui import context_menu

logger = logging.getLogger(__name__)
_SEARCH_HEADER_DRAG_THRESHOLD_PX = 6.0


def _hide_dr_meter_debug() -> bool:
    return str(os.getenv("HIRESTI_VIZ_HIDE_DR_METER", "0")).strip().lower() in ("1", "true", "yes", "on")


def _sidebar_nav_sections():
    return [
        (
            "DISCOVER",
            [
                ("home", "hiresti-home-symbolic", "Home"),
                ("new", "hiresti-new-symbolic", "New"),
                ("top", "hiresti-top-symbolic", "Top"),
                ("hires", "hiresti-hires-symbolic", "Hi-Res"),
                ("genres", "hiresti-genres-symbolic", "Genres"),
                ("decades", "hiresti-decades-symbolic", "Decades"),
                ("moods", "hiresti-moods-symbolic", "Moods"),
            ],
        ),
        (
            "YOUR LIBRARY",
            [
                ("collection", "hiresti-albums-symbolic", "Albums"),
                ("liked_songs", "hiresti-favorite-symbolic", "Tracks"),
                ("artists", "hiresti-artists-symbolic", "Artists"),
                ("playlists", "hiresti-playlists-symbolic", "Playlists"),
                ("mixes", "hiresti-mixes-symbolic", "Mixes & Radio"),
                ("uploads", "hiresti-uploads-symbolic", "Uploads"),
            ],
        ),
        (
            "RECENT",
            [
                ("history", "hiresti-history-symbolic", "History"),
            ],
        ),
    ]


def _open_external_url(url: str):
    subprocess.Popen(["xdg-open", url])


def _build_community_action_row(icon_name: str, title: str, subtitle: str, button_label: str, url: str):
    row = Adw.ActionRow(title=title, subtitle=subtitle)
    row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
    button = Gtk.Button(label=button_label, valign=Gtk.Align.CENTER)
    button.connect("clicked", lambda _btn: _open_external_url(url))
    row.add_suffix(button)
    row.set_activatable_widget(button)
    return row


def _present_community_window(app):
    win = Adw.Window(transient_for=getattr(app, "win", None), modal=True)
    dialogs.close_on_escape(win)  # fork
    win.set_title("Community")
    win.set_default_size(520, 520)

    content = Adw.ToolbarView()
    win.set_content(content)

    header = Adw.HeaderBar()
    content.add_top_bar(header)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    content.set_content(scroll)

    clamp = Adw.Clamp(maximum_size=520, tightening_threshold=480, margin_top=24, margin_bottom=24, margin_start=16, margin_end=16)
    scroll.set_child(clamp)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    clamp.set_child(root)

    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    title_icon = Gtk.Image.new_from_icon_name("network-workgroup-symbolic")
    title_icon.set_halign(Gtk.Align.START)
    title_icon.set_pixel_size(24)
    title_box.append(title_icon)
    title_label = Gtk.Label(label="Community", xalign=0, css_classes=["album-title-large"])
    subtitle_label = Gtk.Label(
        label=f"{brand.APP_NAME} is built on {brand.UPSTREAM_NAME} by {brand.UPSTREAM_AUTHOR}.",
        xalign=0,
        wrap=True,
        wrap_mode=Pango.WrapMode.WORD_CHAR,
    )
    subtitle_label.add_css_class("dim-label")
    title_box.append(title_label)
    title_box.append(subtitle_label)
    root.append(title_box)

    links_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    links_list.append(
        _build_community_action_row(
            "dialog-warning-symbolic",
            "Report a Problem",
            f"Bugs and ideas for {brand.APP_NAME} go to its own issue tracker.",
            "Open",
            brand.ISSUES_URL,
        )
    )
    links_list.append(
        _build_community_action_row(
            "emblem-favorite-symbolic",
            f"Sponsor {brand.UPSTREAM_AUTHOR}",
            f"{brand.APP_NAME} runs on {brand.UPSTREAM_NAME}'s playback engine; sponsoring its author funds that work.",
            "Sponsor",
            brand.UPSTREAM_SPONSOR_URL,
        )
    )
    links_list.append(
        _build_community_action_row(
            "starred-symbolic",
            f"Star {brand.UPSTREAM_NAME} on GitHub",
            f"A star helps more people find the project {brand.APP_NAME} is built on.",
            "Star",
            brand.UPSTREAM_URL,
        )
    )
    root.append(links_list)

    note_label = Gtk.Label(
        label=f"Please report {brand.APP_NAME} problems here rather than to {brand.UPSTREAM_NAME}: "
              f"its author can't fix what {brand.APP_NAME} changed.",
        xalign=0,
        wrap=True,
        wrap_mode=Pango.WrapMode.WORD_CHAR,
    )
    note_label.add_css_class("dim-label")
    root.append(note_label)

    win.present()


def _build_update_meta_row(title: str, value: str):
    row = Adw.ActionRow(title=title, subtitle=value or "—")
    row.set_activatable(False)
    return row


def present_update_window(app):
    state = dict(getattr(app, "_update_check_state", {}) or {})
    current_version = str(state.get("current_version") or getattr(app, "app_version", "dev") or "dev").strip()
    latest_version = str(state.get("latest_version") or "").strip()
    latest_name = str(state.get("latest_name") or latest_version or "").strip()
    latest_url = str(state.get("latest_url") or brand.RELEASES_URL).strip()
    published_at = str(state.get("latest_published_at") or "").strip()
    latest_notes = str(state.get("latest_notes") or "").strip()
    error_text = str(state.get("error") or "").strip()
    available = bool(state.get("update_available"))

    no_feed = bool(state.get("no_feed"))
    win = Adw.Window(transient_for=getattr(app, "win", None), modal=True)
    dialogs.close_on_escape(win)  # fork
    win.set_title("Software Update")
    win.set_default_size(520, 440)

    content = Adw.ToolbarView()
    win.set_content(content)

    header = Adw.HeaderBar()
    content.add_top_bar(header)

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    content.set_content(scroll)

    clamp = Adw.Clamp(maximum_size=520, tightening_threshold=480, margin_top=24, margin_bottom=24, margin_start=16, margin_end=16)
    scroll.set_child(clamp)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    clamp.set_child(root)

    title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    title_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
    title_icon.set_halign(Gtk.Align.START)
    title_icon.set_pixel_size(24)
    title_box.append(title_icon)

    if no_feed:
        # Fork: a private repository has no public releases. This said "Update Check Failed".
        heading = "No Release Feed"
        subtitle = (
            f"This build of {brand.APP_NAME} comes as a package built from its repository, which "
            "publishes no releases. A newer build arrives as a new package."
        )
    elif error_text:
        heading = "Update Check Failed"
        subtitle = "GitHub releases could not be reached just now. You can still open the releases page manually."
    elif available:
        heading = "Update Available"
        subtitle = f"{latest_name or latest_version} is newer than your current build."
    else:
        heading = "Up to Date"
        subtitle = "No newer GitHub release was found for this build."

    title_label = Gtk.Label(label=heading, xalign=0, css_classes=["album-title-large"])
    subtitle_label = Gtk.Label(
        label=subtitle,
        xalign=0,
        wrap=True,
        wrap_mode=Pango.WrapMode.WORD_CHAR,
    )
    subtitle_label.add_css_class("dim-label")
    title_box.append(title_label)
    title_box.append(subtitle_label)
    root.append(title_box)

    meta_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
    meta_list.append(_build_update_meta_row("Current Version", current_version))
    if not no_feed:
        meta_list.append(_build_update_meta_row("Latest Release", latest_name or latest_version or "No newer release"))
        meta_list.append(_build_update_meta_row("Published", published_at or "Unknown"))
    if error_text and not no_feed:
        meta_list.append(_build_update_meta_row("Status", error_text))
    root.append(meta_list)

    if latest_notes:
        notes_title = Gtk.Label(label="Release Notes", xalign=0)
        notes_title.add_css_class("caption")
        notes_title.add_css_class("dim-label")
        root.append(notes_title)

        notes_label = Gtk.Label(
            label=latest_notes,
            xalign=0,
            wrap=True,
            selectable=True,
            wrap_mode=Pango.WrapMode.WORD_CHAR,
        )
        notes_label.add_css_class("dim-label")
        root.append(notes_label)

    actions = Gtk.Box(spacing=10)
    if not no_feed:
        open_release_btn = Gtk.Button(label="Open Release Page")
        open_release_btn.connect("clicked", lambda _btn: _open_external_url(latest_url))
        actions.append(open_release_btn)

    close_btn = Gtk.Button(label="Close")
    close_btn.connect("clicked", lambda _btn: win.close())
    actions.append(close_btn)
    root.append(actions)

    win.present()


def refresh_update_widgets(app):
    state = dict(getattr(app, "_update_check_state", {}) or {})
    available = bool(state.get("update_available"))
    inflight = bool(getattr(app, "_update_check_inflight", False))
    latest_version = str(state.get("latest_version") or "").strip()

    tools_btn = getattr(app, "tools_btn", None)
    if tools_btn is not None:
        tooltip = "Tools & Settings"
        if inflight:
            tooltip = "Tools & Settings • Checking GitHub releases"
        elif available and latest_version:
            tooltip = f"Tools & Settings • Update available: {latest_version}"
        tools_btn.set_tooltip_text(tooltip)

    tools_update_badge = getattr(app, "tools_update_badge", None)
    if tools_update_badge is not None:
        tools_update_badge.set_visible(bool(available and not inflight))

    row_btn = getattr(app, "tools_update_row_btn", None)
    row_label = getattr(app, "tools_update_row_label", None)
    row_badge = getattr(app, "tools_update_row_badge", None)
    if row_label is not None:
        if inflight:
            row_label.set_text("Checking for Updates...")
        elif available:
            row_label.set_text("Update Available")
        else:
            row_label.set_text("Check for Updates")
    if row_btn is not None:
        row_btn.set_sensitive(not inflight)
        row_btn.set_tooltip_text(
            f"Latest release: {latest_version}" if available and latest_version else "Check GitHub releases for a newer version"
        )
    if row_badge is not None:
        row_badge.set_visible(bool(available and not inflight))


def _on_global_context_menu_pressed(app, gesture, x, y):
    """Right-click: open the menu for the item under the pointer (fork #7).

    Upstream opened one window-wide "Share… / Close" popover here, and it copied the upstream
    repo URL. Now the click is claimed only when it lands on a tagged item, so entries and
    labels keep GTK's own menus.
    """
    try:
        surface = gesture.get_widget()
    except Exception:
        surface = None
    if surface is None:
        surface = getattr(app, "win", None)
    if surface is None:
        return
    try:
        # The gesture's coordinates are relative to its own widget, so pick on that widget.
        # Upstream picked on the window, which is offset by CSD shadows when floating.
        hit = surface.pick(x, y, Gtk.PickFlags.DEFAULT)
    except Exception:
        hit = None
    header = getattr(app, "header", None)
    if hit is None or (header is not None and _widget_is_descendant(hit, header)):
        return
    item = context_menu.resolve(hit)
    rows = context_menu.actions_for(app, *item, origin=hit) if item else []
    if not rows:
        return
    try:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
    except Exception:
        pass
    _clear_search_focus(app)
    context_menu.popup(app, surface, x, y, rows, on_closed=lambda: _after_context_menu_closed(app))


def _after_context_menu_closed(app):
    _suppress_search_focus(app)
    GLib.idle_add(lambda: _clear_search_focus(app))


def _setup_global_context_menu(app, parent):
    gesture = Gtk.GestureClick()
    gesture.set_button(Gdk.BUTTON_SECONDARY)
    gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    gesture.connect("pressed", lambda gest, _n, x, y: _on_global_context_menu_pressed(app, gest, x, y))
    parent.add_controller(gesture)
    app._context_menu_gesture = gesture


def _close_search_suggestions(app):
    pop = getattr(app, "search_suggest_popover", None)
    if pop is not None:
        pop.popdown()


def _on_search_entry_key(app, keyval, state):
    """Fork: Tab leaves the search box for the next control, closing Recent Searches, instead of
    walking every recent-search chip first; Down enters the chips (browser address-bar style)."""
    pop = getattr(app, "search_suggest_popover", None)
    if pop is None or not pop.get_visible():
        return False
    if keyval == Gdk.KEY_Tab and not (state & Gdk.ModifierType.SHIFT_MASK):
        _close_search_suggestions(app)
        return False  # GTK moves focus on; the chips are gone from the chain now
    if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
        flow = getattr(app, "search_history_flow", None)
        first = flow.get_child_at_index(0) if flow is not None else None
        return bool(first is not None and first.child_focus(Gtk.DirectionType.TAB_FORWARD))
    return False


def _clear_search_focus(app):
    _close_search_suggestions(app)
    win = getattr(app, "win", None)
    if win is not None:
        try:
            win.set_focus(None)
        except Exception:
            pass
    return False


def _widget_is_descendant(widget, ancestor):
    cur = widget
    while cur is not None:
        if cur is ancestor:
            return True
        try:
            cur = cur.get_parent()
        except Exception:
            return False
    return False


def _widget_chain_preserves_search_focus(widget):
    cur = widget
    interactive_types = tuple(
        cls for cls in (
            getattr(Gtk, "Button", None),
            getattr(Gtk, "ToggleButton", None),
            getattr(Gtk, "CheckButton", None),
            getattr(Gtk, "Switch", None),
            getattr(Gtk, "DropDown", None),
            getattr(Gtk, "ComboBox", None),
            getattr(Gtk, "ComboBoxText", None),
            getattr(Gtk, "Entry", None),
            getattr(Gtk, "SearchEntry", None),
            getattr(Gtk, "SpinButton", None),
            getattr(Gtk, "Scale", None),
            getattr(Gtk, "TextView", None),
        )
        if cls is not None
    )
    while cur is not None:
        if interactive_types and isinstance(cur, interactive_types):
            return True
        if not isinstance(cur, Gtk.Widget):
            getter = getattr(cur, "get_focusable", None)
            if getter is not None:
                try:
                    if getter():
                        return True
                except Exception:
                    pass
        try:
            cur = cur.get_parent()
        except Exception:
            return False
    return False


def _suppress_search_focus(app, duration_ms=220):
    try:
        now_us = GLib.get_monotonic_time()
    except Exception:
        now_us = 0
    app._search_focus_suppressed_until_us = int(now_us) + (int(duration_ms) * 1000)


def _search_focus_is_suppressed(app):
    try:
        now_us = GLib.get_monotonic_time()
    except Exception:
        now_us = 0
    return int(getattr(app, "_search_focus_suppressed_until_us", 0) or 0) > int(now_us)


def _search_focus_is_blocked(app):
    return bool(
        getattr(app, "_dsp_order_drag_active", False)
        or getattr(app, "_dsp_order_editing", False)
    )


def _reset_search_press_state(app):
    app._search_press_active = False
    app._search_press_start_x = 0.0
    app._search_press_start_y = 0.0
    app._search_press_in_header = False
    app._search_header_dragging = False


def _check_search_suggestions_focus(app):
    app._search_suggest_focus_check_source = 0
    pop = getattr(app, "search_suggest_popover", None)
    entry = getattr(app, "search_entry", None)
    win = getattr(app, "win", None)
    if pop is None or entry is None or win is None or not pop.get_visible():
        return False
    try:
        focus = win.get_focus()
    except Exception:
        focus = None
    if focus is not None and (_widget_is_descendant(focus, entry) or _widget_is_descendant(focus, pop)):
        return False
    _close_search_suggestions(app)
    return False


def _queue_search_suggestions_focus_check(app, delay_ms=0):
    pending = int(getattr(app, "_search_suggest_focus_check_source", 0) or 0)
    if pending:
        GLib.source_remove(pending)
        app._search_suggest_focus_check_source = 0

    def _run():
        return _check_search_suggestions_focus(app)

    if int(delay_ms or 0) > 0:
        app._search_suggest_focus_check_source = GLib.timeout_add(int(delay_ms), _run)
    else:
        app._search_suggest_focus_check_source = GLib.idle_add(_run)


def _maybe_show_search_suggestions(app):
    entry = getattr(app, "search_entry", None)
    pop = getattr(app, "search_suggest_popover", None)
    if entry is None or pop is None:
        return
    if _search_focus_is_blocked(app):
        pop.popdown()
        return
    if _search_focus_is_suppressed(app):
        return
    pending = int(getattr(app, "_search_suggest_focus_check_source", 0) or 0)
    if pending:
        GLib.source_remove(pending)
        app._search_suggest_focus_check_source = 0
    if not entry.get_visible() or not entry.get_sensitive():
        pop.popdown()
        return
    if not list(getattr(app, "search_history", [])):
        pop.popdown()
        return
    if hasattr(app, "render_search_history"):
        app.render_search_history()
    pop.popup()



def _on_search_entry_changed_for_suggestions(app, entry):
    if str(entry.get_text() or "").strip():
        _close_search_suggestions(app)
        return
    if entry.has_focus():
        _maybe_show_search_suggestions(app)


def _on_search_entry_focus_enter(app):
    if _search_focus_is_blocked(app):
        GLib.idle_add(lambda: _clear_search_focus(app))
        return
    if _search_focus_is_suppressed(app):
        GLib.idle_add(lambda: _clear_search_focus(app))
        return
    _maybe_show_search_suggestions(app)


def _click_is_on_entry(entry, win, x, y):
    try:
        ok, rect = entry.compute_bounds(win)
        if not ok or rect is None:
            return False
        return (rect.get_x() <= x <= rect.get_x() + rect.get_width() and
                rect.get_y() <= y <= rect.get_y() + rect.get_height())
    except Exception:
        hit = win.pick(x, y, Gtk.PickFlags.DEFAULT)
        return hit is not None and _widget_is_descendant(hit, entry)


def _should_track_header_drag(app, hit):
    if hit is None:
        return False
    header = getattr(app, "header", None)
    if header is None:
        return False
    if not _widget_is_descendant(hit, header):
        return False
    if _widget_chain_preserves_search_focus(hit):
        return False
    return True


def _on_window_pressed_for_dismiss(app, x, y, gesture=None):
    if _search_focus_is_blocked(app):
        return
    pop = getattr(app, "search_suggest_popover", None)
    entry = getattr(app, "search_entry", None)
    win = getattr(app, "win", None)
    if win is None:
        return
    hit = None
    try:
        hit = win.pick(x, y, Gtk.PickFlags.DEFAULT)
    except Exception:
        hit = None
    if pop is None or entry is None:
        return
    app._search_press_active = True
    app._search_press_start_x = float(x)
    app._search_press_start_y = float(y)
    app._search_press_in_header = _should_track_header_drag(app, hit)
    app._search_header_dragging = False
    if _click_is_on_entry(entry, win, x, y):
        if not pop.get_visible():
            GLib.idle_add(lambda: (_maybe_show_search_suggestions(app), False)[1])
        return
    if hit is not None and _widget_is_descendant(hit, pop):
        return
    if pop.get_visible():
        _close_search_suggestions(app)
    if not _widget_chain_preserves_search_focus(hit):
        GLib.idle_add(lambda: _clear_search_focus(app))


def _on_window_motion_for_search_focus(app, x, y):
    if _search_focus_is_blocked(app):
        return
    if not bool(getattr(app, "_search_press_active", False)):
        return
    if not bool(getattr(app, "_search_press_in_header", False)):
        return
    if bool(getattr(app, "_search_header_dragging", False)):
        return
    dx = abs(float(x) - float(getattr(app, "_search_press_start_x", 0.0) or 0.0))
    dy = abs(float(y) - float(getattr(app, "_search_press_start_y", 0.0) or 0.0))
    if dx >= _SEARCH_HEADER_DRAG_THRESHOLD_PX or dy >= _SEARCH_HEADER_DRAG_THRESHOLD_PX:
        app._search_header_dragging = True


def _on_window_released_for_search_focus(app):
    if _search_focus_is_blocked(app):
        _reset_search_press_state(app)
        return
    dragged = bool(getattr(app, "_search_header_dragging", False))
    _reset_search_press_state(app)
    if not dragged:
        return
    _suppress_search_focus(app)
    GLib.idle_add(lambda: _clear_search_focus(app))


def _on_window_focus_widget_changed(app):
    if _search_focus_is_blocked(app):
        _close_search_suggestions(app)
        GLib.idle_add(lambda: _clear_search_focus(app))
        return
    if _search_focus_is_suppressed(app):
        win = getattr(app, "win", None)
        entry = getattr(app, "search_entry", None)
        if win is not None and entry is not None:
            try:
                focus = win.get_focus()
            except Exception:
                focus = None
            if focus is not None and _widget_is_descendant(focus, entry):
                GLib.idle_add(lambda: _clear_search_focus(app))
                return
    _queue_search_suggestions_focus_check(app, delay_ms=10)


def _setup_window_click_dismiss(app):
    win = getattr(app, "win", None)
    if win is None:
        return
    win_click = Gtk.GestureClick()
    win_click.set_button(Gdk.BUTTON_PRIMARY)
    win_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    win_click.connect("pressed", lambda gest, _n, x, y: _on_window_pressed_for_dismiss(app, x, y, gesture=gest))
    win_click.connect("released", lambda *_args: _on_window_released_for_search_focus(app))
    win_click.connect("stopped", lambda *_args: _reset_search_press_state(app))
    win.add_controller(win_click)
    motion = Gtk.EventControllerMotion()
    motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    motion.connect("motion", lambda _ctrl, x, y: _on_window_motion_for_search_focus(app, x, y))
    win.add_controller(motion)
    app._search_dismiss_gesture = win_click
    app._search_focus_motion = motion


def _build_search_suggestions_popover(app):
    pop = Gtk.Popover()
    pop.set_parent(app.search_entry)
    pop.set_has_arrow(False)
    pop.set_autohide(False)
    pop.add_css_class("search-suggest-popover")

    try:
        pop.set_position(Gtk.PositionType.BOTTOM)
    except Exception:
        pass
    try:
        pop.set_offset(0, 8)
    except Exception:
        pass

    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_propagate_natural_height(True)
    scroll.set_min_content_width(600)
    scroll.set_max_content_height(480)
    scroll.add_css_class("search-suggest-scroll")

    content = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=12,
        margin_top=0,
        margin_bottom=14,
        margin_start=14,
        margin_end=14,
        css_classes=["search-suggest-content"],
    )

    history_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["search-suggest-section"])
    history_head = Gtk.Box(spacing=8)
    history_head.append(Gtk.Label(label="Recent Searches", xalign=0, css_classes=["search-suggest-title"], hexpand=True))
    clear_btn = Gtk.Button(label="Clear", css_classes=["flat"])
    clear_btn.connect("clicked", lambda _b: app.clear_search_history())
    history_head.append(clear_btn)
    history_section.append(history_head)

    history_flow = Gtk.FlowBox(
        selection_mode=Gtk.SelectionMode.NONE,
        column_spacing=4,
        row_spacing=6,
        css_classes=["search-suggest-flow"],
    )
    history_flow.set_min_children_per_line(1)
    history_flow.set_max_children_per_line(100)
    history_flow.set_homogeneous(False)
    history_flow.set_hexpand(True)
    history_flow.set_halign(Gtk.Align.FILL)
    history_section.append(history_flow)
    content.append(history_section)

    app.search_history_section = history_section
    app.search_history_flow = history_flow
    app.clear_history_btn = clear_btn

    scroll.set_child(content)
    pop.set_child(scroll)
    return pop


def build_header(app, container):
    app.window_handle = Gtk.WindowHandle()
    container.append(app.window_handle)

    app.header = Adw.HeaderBar()
    app.window_handle.set_child(app.header)

    # Fork: Back steps out of the top layer (Now Playing, the queue, Settings), else goes back a
    # page; see actions/layers.py. (Upstream's "Back" tooltip also overwrote this one.)
    from actions import layers

    app.back_btn = layers.BackButton(icon_name="go-previous-symbolic", sensitive=False)
    app.back_btn.connect("clicked", lambda _b: layers.step_back(app))
    app.back_btn.set_tooltip_text("Back (Alt+←, Esc)")
    app.header.pack_start(app.back_btn)
    # Fork: only shown when the window is too narrow to dock the sidebar.
    app.sidebar_toggle_btn = Gtk.Button(icon_name="sidebar-show-symbolic", visible=False)
    app.sidebar_toggle_btn.set_tooltip_text("Browse and Search (Ctrl+F)")
    app.sidebar_toggle_btn.connect("clicked", lambda _b: toggle_sidebar_overlay(app))
    app.header.pack_start(app.sidebar_toggle_btn)

    app.search_entry = Gtk.Entry(
        placeholder_text="Search...",
        width_request=200,
        valign=Gtk.Align.CENTER,
    )
    app.search_entry.connect("activate", app.on_search)
    app.search_entry.connect("changed", app.on_search_changed)
    # Search lives at the top of the sidebar (added in build_body),
    # not in the header title.
    app.search_suggest_popover = _build_search_suggestions_popover(app)

    app.search_entry.connect("activate", lambda _entry: _close_search_suggestions(app))
    app.search_entry.connect("activate", lambda _entry: hide_sidebar_overlay(app))
    app.search_entry.connect("changed", lambda entry: _on_search_entry_changed_for_suggestions(app, entry))

    focus_controller = Gtk.EventControllerFocus()
    focus_controller.connect("enter", lambda *_args: _on_search_entry_focus_enter(app))
    focus_controller.connect("leave", lambda *_args: _queue_search_suggestions_focus_check(app))
    app.search_entry.add_controller(focus_controller)
    search_keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)  # fork
    search_keys.connect("key-pressed", lambda _c, kv, _kc, st: _on_search_entry_key(app, kv, st))
    app.search_entry.add_controller(search_keys)

    if getattr(app, "win", None) is not None:
        app.win.connect("notify::focus-widget", lambda *_args: _on_window_focus_widget_changed(app))
        _setup_window_click_dismiss(app)

    box_right = Gtk.Box(spacing=6)

    app.login_btn = Gtk.Button(label="Login", css_classes=["flat"])
    app.login_btn.connect("clicked", app.on_login_clicked)
    app.user_popover = app._build_user_popover()
    app.user_popover.set_parent(app.login_btn)

    app.mini_btn = Gtk.Button(icon_name="ebb-pip-symbolic", css_classes=["flat"])
    app.mini_btn.set_tooltip_text("Mini Player")  # fork: PiP icon; the arrows read as "minimize"
    app.mini_btn.connect("clicked", app.toggle_mini_mode)

    app.tools_btn = Gtk.Button(css_classes=["flat"])
    gear_image = Gtk.Image.new_from_icon_name("hiresti-gear-symbolic")
    gear_image.set_pixel_size(18)
    gear_overlay = Gtk.Overlay()
    gear_overlay.set_child(gear_image)
    app.tools_update_badge = Gtk.Box(css_classes=["tools-update-dot"])
    app.tools_update_badge.set_size_request(9, 9)
    app.tools_update_badge.set_halign(Gtk.Align.END)
    app.tools_update_badge.set_valign(Gtk.Align.START)
    app.tools_update_badge.set_margin_top(1)
    app.tools_update_badge.set_margin_start(12)
    app.tools_update_badge.set_visible(False)
    gear_overlay.add_overlay(app.tools_update_badge)
    app.tools_btn.set_child(gear_overlay)
    app.tools_btn.set_tooltip_text("Tools & Settings")
    app.tools_pop = Gtk.Popover()
    app.tools_pop.set_parent(app.tools_btn)
    tools_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=4,
        margin_top=8,
        margin_bottom=8,
        margin_start=8,
        margin_end=8,
    )

    def _tool_row(icon_name, label, callback, with_badge=False):
        btn = Gtk.Button(css_classes=["flat"])
        row = Gtk.Box(spacing=8, hexpand=True)
        row.append(Gtk.Image.new_from_icon_name(icon_name))
        text = Gtk.Label(label=label, xalign=0, hexpand=True)
        row.append(text)
        badge = None
        if with_badge:
            badge = Gtk.Box(css_classes=["tools-update-dot"])
            badge.set_size_request(9, 9)
            badge.set_valign(Gtk.Align.CENTER)
            badge.set_visible(False)
            row.append(badge)
        btn.set_child(row)
        btn.connect("clicked", callback)
        return btn, text, badge

    def _on_shortcuts_clicked(_btn):
        app.tools_pop.popdown()
        app.show_shortcuts_dialog()  # fork: the full list (Ctrl+?), not upstream's stale popover

    def _on_signal_path_clicked(_btn):
        app.tools_pop.popdown()
        app.on_tech_info_clicked(_btn)

    def _on_settings_clicked(_btn):
        app.tools_pop.popdown()
        app.on_settings_clicked(_btn)

    def _on_about_clicked(_btn):
        app.tools_pop.popdown()
        app.on_about_clicked(_btn)

    def _on_community_clicked(_btn):
        app.tools_pop.popdown()
        _present_community_window(app)

    def _on_update_clicked(_btn):
        app.tools_pop.popdown()
        app.on_check_for_updates_clicked(_btn)

    row_btn, _row_label, _row_badge = _tool_row("hiresti-shortcuts-symbolic", "Keyboard Shortcuts", _on_shortcuts_clicked)
    tools_box.append(row_btn)
    row_btn, _row_label, _row_badge = _tool_row("hiresti-tech-symbolic", "Signal Path / Tech Info", _on_signal_path_clicked)
    tools_box.append(row_btn)
    row_btn, _row_label, _row_badge = _tool_row("hiresti-gear-symbolic", "Settings", _on_settings_clicked)
    tools_box.append(row_btn)
    row_btn, _row_label, _row_badge = _tool_row("view-refresh-symbolic", "Check for Updates", _on_update_clicked, with_badge=True)
    app.tools_update_row_btn = row_btn
    app.tools_update_row_label = _row_label
    app.tools_update_row_badge = _row_badge
    tools_box.append(row_btn)
    row_btn, _row_label, _row_badge = _tool_row("network-workgroup-symbolic", "Community", _on_community_clicked)
    tools_box.append(row_btn)
    row_btn, _row_label, _row_badge = _tool_row("help-about-symbolic", "About", _on_about_clicked)
    tools_box.append(row_btn)
    app.tools_pop.set_child(tools_box)
    refresh_update_widgets(app)
    app.tools_btn.connect("clicked", lambda _b: app.tools_pop.popup())

    box_right.append(app.login_btn)
    box_right.append(app.mini_btn)
    box_right.append(app.tools_btn)
    app.header.pack_end(box_right)


def build_body(app, container):
    body_t0 = time.monotonic()

    def _body_mark(stage):
        logger.info(
            "STARTUP TIMING build-body %s +%.1fms",
            str(stage),
            (time.monotonic() - body_t0) * 1000.0,
        )

    _setup_global_context_menu(app, container)
    _body_mark("context-menu")

    app.body_overlay = Gtk.Overlay()
    app.body_overlay.set_vexpand(True)
    container.append(app.body_overlay)

    app.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
    app.body_overlay.set_child(app.paned)

    app.queue_backdrop = Gtk.Box(css_classes=["queue-backdrop"])
    app.queue_backdrop.set_hexpand(True)
    app.queue_backdrop.set_vexpand(True)
    app.queue_backdrop.set_visible(False)
    backdrop_click = Gtk.GestureClick()
    backdrop_click.connect("released", lambda *_args: app.close_queue_drawer())
    app.queue_backdrop.add_controller(backdrop_click)
    app.body_overlay.add_overlay(app.queue_backdrop)

    app.queue_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_LEFT)
    app.queue_revealer.set_transition_duration(180)
    app.queue_revealer.set_reveal_child(False)
    app.queue_revealer.set_halign(Gtk.Align.END)
    app.queue_revealer.set_valign(Gtk.Align.FILL)
    app.queue_revealer.set_hexpand(False)
    app.queue_revealer.set_vexpand(True)

    app.queue_drawer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0, css_classes=["queue-drawer"])
    app.queue_drawer_box.set_size_request(240, -1)
    app.queue_drawer_box.set_vexpand(True)

    q_head = Gtk.Box(spacing=8, margin_start=12, margin_end=12, margin_top=10, margin_bottom=10)
    q_head.append(Gtk.Label(label="Queue", xalign=0, hexpand=True, css_classes=["home-section-title"]))
    app.queue_count_label = Gtk.Label(label="0 tracks", css_classes=["home-section-count"])
    q_head.append(app.queue_count_label)
    from actions.ui_actions import _queue_save_button  # fork #10

    app.queue_save_btn = _queue_save_button(app, False)
    q_head.append(app.queue_save_btn)
    app.queue_clear_btn = None
    app.queue_drawer_box.append(q_head)

    app.queue_drawer_list = Gtk.ListBox(css_classes=["tracks-list", "queue-drawer-list"])
    app.queue_drawer_list.connect("row-activated", app.on_queue_track_selected)
    q_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    q_scroll.add_css_class("queue-drawer-scroll")
    q_scroll.set_margin_start(8)
    q_scroll.set_margin_end(8)
    q_scroll.set_margin_bottom(8)
    q_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    q_scroll.set_child(app.queue_drawer_list)
    app.queue_drawer_box.append(q_scroll)

    app.queue_revealer.set_child(app.queue_drawer_box)

    app.queue_btn = Gtk.Button(icon_name="hiresti-queue-handle-left-symbolic", css_classes=["queue-handle-btn"])
    app.queue_btn.set_tooltip_text("Open Queue")
    app.queue_btn.set_size_request(23, 50)
    app.queue_btn.set_valign(Gtk.Align.CENTER)
    app.queue_btn.set_vexpand(False)
    app.queue_btn.connect("clicked", app.toggle_queue_drawer)

    app.queue_handle_shell = Gtk.Box(css_classes=["queue-handle-shell"])
    app.queue_handle_shell.set_size_request(23, 50)
    app.queue_handle_shell.set_valign(Gtk.Align.CENTER)
    app.queue_handle_shell.set_vexpand(False)
    app.queue_handle_shell.append(app.queue_btn)

    app.queue_anchor = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=0,
        halign=Gtk.Align.END,
        valign=Gtk.Align.FILL,
        hexpand=True,
        vexpand=True,
        css_classes=["queue-anchor"],
    )
    queue_gap = int(max(0, ui_config.WINDOW_HEIGHT * 0.10))
    app.queue_anchor.set_margin_top(queue_gap)
    app.queue_anchor.set_margin_bottom(queue_gap)
    app.queue_anchor.append(app.queue_handle_shell)
    app.queue_anchor.append(app.queue_revealer)
    app.body_overlay.add_overlay(app.queue_anchor)
    _body_mark("queue-shell")

    app.output_notice_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
    app.output_notice_revealer.set_transition_duration(180)
    app.output_notice_revealer.set_reveal_child(False)
    app.output_notice_revealer.set_halign(Gtk.Align.END)
    app.output_notice_revealer.set_valign(Gtk.Align.START)
    app.output_notice_revealer.set_margin_top(10)
    app.output_notice_revealer.set_margin_end(10)
    notice_box = Gtk.Box(spacing=8, css_classes=["output-notice-chip"])
    app.output_notice_icon = Gtk.Image(icon_name="hiresti-tech-symbolic")
    app.output_notice_icon.add_css_class("output-notice-icon")
    app.output_notice_label = Gtk.Label(label="", xalign=0, css_classes=["output-notice-text"])
    notice_box.append(app.output_notice_icon)
    notice_box.append(app.output_notice_label)
    # Fork: optional action ("Undo") on the chip; see app_diagnostics.show_undo_notice.
    app.output_notice_action_btn = Gtk.Button(label="Undo", css_classes=["flat", "output-notice-action"])
    app.output_notice_action_btn.set_visible(False)
    app.output_notice_action_btn.connect("clicked", lambda b: app.on_output_notice_action(b))
    notice_box.append(app.output_notice_action_btn)
    app.output_notice_revealer.set_child(notice_box)
    app.body_overlay.add_overlay(app.output_notice_revealer)

    app.viz_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP)
    app.viz_revealer.set_reveal_child(False)
    app.viz_revealer.set_valign(Gtk.Align.END)
    app.viz_revealer.set_halign(Gtk.Align.FILL)
    app.viz_revealer.set_hexpand(True)
    app.viz_revealer.set_vexpand(False)

    app.viz_fullscreen_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE)
    app.viz_fullscreen_revealer.set_reveal_child(False)
    app.viz_fullscreen_revealer.set_visible(False)
    app.viz_fullscreen_revealer.set_halign(Gtk.Align.FILL)
    app.viz_fullscreen_revealer.set_valign(Gtk.Align.FILL)
    app.viz_fullscreen_revealer.set_hexpand(True)
    app.viz_fullscreen_revealer.set_vexpand(True)
    app.viz_fullscreen_revealer.add_css_class("viz-panel")
    app.viz_fullscreen_revealer.add_css_class("viz-fullscreen-revealer")
    if getattr(app, "content_overlay", None) is not None:
        app.content_overlay.add_overlay(app.viz_fullscreen_revealer)
    _body_mark("viz-fullscreen-shell")

    app.viz_btn = Gtk.Button(icon_name="hiresti-pan-up-symbolic", css_classes=["flat", "viz-handle-btn"])
    app.viz_btn.set_tooltip_text("Lyrics, Visualizer and DSP (E)")
    app.viz_btn.set_size_request(50, 23)
    app.viz_btn.connect("clicked", app.toggle_visualizer)

    app.viz_anchor = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=0,
        halign=Gtk.Align.FILL,
        valign=Gtk.Align.END,
        hexpand=True,
        vexpand=True,
        css_classes=["viz-handle-anchor"],
    )
    app.viz_anchor.append(app.viz_revealer)
    app.body_overlay.add_overlay(app.viz_anchor)

    app.viz_handle_box = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=0,
        halign=Gtk.Align.CENTER,
        valign=Gtk.Align.END,
        hexpand=True,
        vexpand=True,
        css_classes=["viz-handle-floating"],
    )
    app.viz_handle_box.set_margin_end(0)
    app.viz_handle_box.set_margin_bottom(2)
    app.viz_handle_box.append(app.viz_btn)
    # Fork (ui/viz_panel.py): the floating handle is built (other code shows and hides it) but
    # not placed. The panel opens from the DSP button and with E, and closes from its header.

    app.viz_root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    app.viz_root.set_hexpand(True)
    app.viz_root.set_halign(Gtk.Align.FILL)
    app.viz_root.set_valign(Gtk.Align.END)
    app.viz_root.set_vexpand(False)

    app.viz_switcher = Gtk.StackSwitcher()
    app.viz_switcher.set_halign(Gtk.Align.START)
    app.viz_switcher.set_margin_start(0)
    app.viz_switcher.add_css_class("mini-switcher")
    app.viz_switcher.remove_css_class("linked")
    app.viz_switcher.set_hexpand(False)

    app.viz_stack_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    app.viz_stack_box.add_css_class("viz-panel")
    app.viz_stack_box.set_overflow(Gtk.Overflow.HIDDEN)
    app.viz_stack_box.set_vexpand(False)
    app.viz_stack_box.set_valign(Gtk.Align.END)

    app.viz_stack = Gtk.Stack()
    app.viz_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
    app.viz_stack.set_size_request(-1, int(ui_config.WINDOW_HEIGHT / 2))
    app.viz_stack.set_vexpand(False)
    app.viz_stack.set_valign(Gtk.Align.FILL)
    app.viz_switcher.set_stack(app.viz_stack)
    app.viz_stack.connect("notify::visible-child-name", app.on_viz_page_changed)
    _body_mark("viz-stack-shell")

    app.viz_surface_overlay = Gtk.Overlay()
    app.viz_surface_overlay.set_hexpand(True)
    app.viz_surface_overlay.set_vexpand(False)
    app.viz_surface_overlay.set_valign(Gtk.Align.FILL)
    app.viz_surface_overlay.set_child(app.viz_stack)

    app.viz = _HybridVisualizer()
    app.viz.set_num_bars(32)
    app.viz.set_valign(Gtk.Align.FILL)
    app.viz_stack.add_titled(app.viz, "spectrum", "Spectrum")
    _body_mark("viz-spectrum-tab")

    app.viz_freq_scale_dd = Gtk.DropDown(model=Gtk.StringList.new(app.viz.get_frequency_scale_names()))
    app.viz_freq_scale_dd.add_css_class("viz-theme-dd")
    app.viz_freq_scale_dd.add_css_class("viz-right-first")
    app.viz_freq_scale_dd.set_valign(Gtk.Align.CENTER)
    app.viz_freq_scale_dd.connect("notify::selected", app.on_viz_frequency_scale_changed)

    app.viz_bars_dd = Gtk.DropDown(model=Gtk.StringList.new([str(v) for v in app.VIZ_BAR_OPTIONS]))
    app.viz_bars_dd.add_css_class("viz-theme-dd")
    app.viz_bars_dd.set_valign(Gtk.Align.CENTER)
    app.viz_bars_dd.connect("notify::selected", app.on_viz_bars_changed)

    app.viz_theme_dd = Gtk.DropDown(model=Gtk.StringList.new(app.viz.get_theme_names()))
    app.viz_theme_dd.add_css_class("viz-theme-dd")
    app.viz_theme_dd.add_css_class("viz-right-last")
    app.viz_theme_dd.set_valign(Gtk.Align.CENTER)
    app.viz_theme_dd.connect("notify::selected", app.on_spectrum_theme_changed)

    effect_names = list(app.viz.get_effect_names() or [])
    if "Dots" not in effect_names:
        effect_names.append("Dots")
    logger.info("Visualizer effects available: %s", effect_names)
    app.viz_effect_dd = Gtk.DropDown(model=Gtk.StringList.new(effect_names))
    app.viz_effect_dd.add_css_class("viz-theme-dd")
    app.viz_effect_dd.set_valign(Gtk.Align.CENTER)
    app.viz_effect_dd.connect("notify::selected", app.on_viz_effect_changed)

    app.viz_profile_dd = Gtk.DropDown(model=Gtk.StringList.new(app.viz.get_profile_names()))
    app.viz_profile_dd.add_css_class("viz-theme-dd")
    app.viz_profile_dd.set_valign(Gtk.Align.CENTER)
    app.viz_profile_dd.connect("notify::selected", app.on_viz_profile_changed)

    app.lyrics_font_dd = Gtk.DropDown(model=Gtk.StringList.new(app.LYRICS_FONT_PRESETS))
    app.lyrics_font_dd.add_css_class("viz-theme-dd")
    app.lyrics_font_dd.add_css_class("lyrics-font-dd")
    app.lyrics_font_dd.set_valign(Gtk.Align.CENTER)
    app.lyrics_font_dd.connect("notify::selected", app.on_lyrics_font_preset_changed)

    theme_row = Gtk.Box(spacing=10)
    app.viz_theme_row = theme_row
    theme_row.add_css_class("viz-theme-row")
    theme_row.set_hexpand(True)
    theme_row.set_halign(Gtk.Align.FILL)
    theme_row.set_margin_start(32)
    theme_row.set_margin_end(32)
    theme_row.set_margin_top(8)
    theme_row.append(app.viz_switcher)
    theme_row.append(Gtk.Box(hexpand=True))
    right_ctrl_box = Gtk.Box(spacing=4)
    right_ctrl_box.add_css_class("viz-right-controls")
    right_ctrl_box.set_halign(Gtk.Align.END)
    theme_row.append(right_ctrl_box)
    from ui import viz_panel  # fork: the panel's own way out, now that the handle is gone

    theme_row.append(viz_panel.close_button(app))
    right_ctrl_box.append(app.viz_freq_scale_dd)
    right_ctrl_box.append(app.viz_bars_dd)
    right_ctrl_box.append(app.viz_profile_dd)
    right_ctrl_box.append(app.viz_effect_dd)
    right_ctrl_box.append(app.viz_theme_dd)
    app.viz_fullscreen_btn = Gtk.Button(icon_name="hiresti-view-fullscreen-symbolic", css_classes=["flat", "viz-overlay-btn"])
    app.viz_fullscreen_btn.set_tooltip_text("Expand Waveform")
    app.viz_fullscreen_btn.connect("clicked", app.toggle_viz_fullscreen)
    app.viz_fullscreen_btn.set_size_request(35, 35)
    app.viz_fullscreen_btn.add_css_class("viz-fullscreen-btn")
    app.lyrics_font_dd.set_visible(False)
    app.lyrics_ctrl_box = Gtk.Box(spacing=4)
    app.lyrics_ctrl_box.add_css_class("viz-right-controls")
    app.lyrics_ctrl_box.set_visible(False)
    right_ctrl_box.append(app.lyrics_ctrl_box)
    app.lyrics_ctrl_box.append(app.lyrics_font_dd)
    app.viz_corner_box = Gtk.Box(halign=Gtk.Align.END, valign=Gtk.Align.START)
    app.viz_corner_box.set_margin_top(12)
    app.viz_corner_box.set_margin_end(18)
    app.viz_corner_box.append(app.viz_fullscreen_btn)
    # added to viz_content_overlay below so it stays at full-panel top-right

    app.dr_meter = LevelMonitor()
    app.dr_meter.set_halign(Gtk.Align.FILL)
    app.dr_meter.set_valign(Gtk.Align.FILL)
    app.dr_meter.set_margin_end(4)
    app.dr_meter.set_margin_top(4)
    app.dr_meter.set_margin_bottom(4)
    app.dr_meter.set_can_target(False)

    app.lyrics_tab_root = Gtk.Overlay()
    app.bg_viz = BackgroundVisualizer()
    app.lyrics_tab_root.set_child(app.bg_viz)
    app.lyrics_motion_dd = Gtk.DropDown(model=Gtk.StringList.new(app.bg_viz.get_motion_mode_names()))
    app.lyrics_motion_dd.add_css_class("viz-theme-dd")
    app.lyrics_motion_dd.add_css_class("lyrics-motion-dd")
    app.lyrics_motion_dd.add_css_class("viz-right-last")
    app.lyrics_motion_dd.set_valign(Gtk.Align.CENTER)
    app.lyrics_motion_dd.connect("notify::selected", app.on_lyrics_motion_changed)
    app.lyrics_motion_dd.set_visible(False)
    app.lyrics_ctrl_box.append(app.lyrics_motion_dd)

    app.lyrics_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    app.lyrics_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    app.lyrics_scroller.add_css_class("lyrics-scroller")

    app.lyrics_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    app.lyrics_vbox.set_halign(Gtk.Align.CENTER)
    app.lyrics_vbox.set_margin_top(30)
    app.lyrics_vbox.set_margin_bottom(30)

    app.lyrics_scroller.set_child(app.lyrics_vbox)
    app.lyrics_tab_root.add_overlay(app.lyrics_scroller)

    app.lyrics_offset_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    app.lyrics_offset_box.set_halign(Gtk.Align.END)
    app.lyrics_offset_box.set_valign(Gtk.Align.CENTER)
    app.lyrics_offset_box.set_margin_end(12)
    app.lyrics_offset_box.set_visible(False)
    btn_off_up = Gtk.Button(icon_name="go-up-symbolic", css_classes=["flat", "circular", "lyrics-offset-arrow"])
    btn_off_up.connect("clicked", app.on_lyrics_offset_step, 50)
    btn_off_down = Gtk.Button(icon_name="go-down-symbolic", css_classes=["flat", "circular", "lyrics-offset-arrow"])
    btn_off_down.connect("clicked", app.on_lyrics_offset_step, -50)
    app.lyrics_offset_label = Gtk.Label(label="0ms", css_classes=["caption", "dim-label"])
    app.lyrics_offset_box.append(btn_off_up)
    app.lyrics_offset_box.append(app.lyrics_offset_label)
    app.lyrics_offset_box.append(btn_off_down)
    app.lyrics_tab_root.add_overlay(app.lyrics_offset_box)
    app.viz_stack.add_titled(app.lyrics_tab_root, "lyrics", "Lyrics")
    _body_mark("viz-lyrics-tab")

    app.dsp_tab_root = app._build_dsp_workspace()
    app.dsp_tab_scroller = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
    app.dsp_tab_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    app.dsp_tab_scroller.set_propagate_natural_height(False)
    app.dsp_tab_scroller.set_propagate_natural_width(False)
    app.dsp_tab_scroller.set_child(app.dsp_tab_root)
    app.viz_stack.add_titled(app.dsp_tab_scroller, "dsp", "DSP")
    _body_mark("viz-dsp-tab")

    # Horizontal row: spectrum fills remaining space, DR meter sits to the right.
    # Wrapped in an Overlay so the fullscreen icon stays at top-right of the full panel.
    app.viz_main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    app.viz_main_row.set_hexpand(True)
    app.viz_main_row.set_vexpand(False)
    app.viz_main_row.set_valign(Gtk.Align.FILL)
    app.viz_surface_overlay.set_hexpand(True)
    app.viz_main_row.append(app.viz_surface_overlay)

    # DR meter: 70% of the viz panel height, pinned to bottom-right
    _dr_h = int(ui_config.WINDOW_HEIGHT / 2 * 0.85)
    app.dr_meter.set_vexpand(False)
    app.dr_meter.set_valign(Gtk.Align.END)
    app.dr_meter.set_size_request(84, _dr_h)
    if not _hide_dr_meter_debug():
        app.viz_main_row.append(app.dr_meter)
    else:
        app.dr_meter.set_visible(False)

    app.viz_content_overlay = Gtk.Overlay()
    app.viz_content_overlay.set_hexpand(True)
    app.viz_content_overlay.set_vexpand(False)
    app.viz_content_overlay.set_valign(Gtk.Align.FILL)
    app.viz_content_overlay.set_child(app.viz_main_row)
    app.viz_content_overlay.add_overlay(app.viz_corner_box)  # fullscreen btn at panel top-right
    app.viz_stack_box.append(app.viz_content_overlay)
    app.viz_stack_box.set_size_request(-1, int(ui_config.WINDOW_HEIGHT / 2))
    app.viz_root.append(theme_row)
    app.viz_root.append(app.viz_stack_box)
    app.viz_revealer.set_child(app.viz_root)
    if hasattr(app, "_sync_viz_height_to_window"):
        app._sync_viz_height_to_window()
    app.on_viz_page_changed(app.viz_stack, None)
    viz_panel.apply(app)  # fork: the Spectrum tab only when turned on in Settings
    _body_mark("viz-shell-finalized")

    app.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["sidebar-shell"])

    # Search sits at the very top of the sidebar, above the DISCOVER
    # section. The entry itself was created during header setup.
    search_holder = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        margin_start=12, margin_end=12, margin_top=12, margin_bottom=4,
    )
    app.search_entry.set_hexpand(True)
    app.search_entry.set_size_request(-1, -1)
    search_holder.append(app.search_entry)
    app.sidebar_box.append(search_holder)

    app.nav_list = Gtk.ListBox(css_classes=["navigation-sidebar"], margin_top=10)
    app.nav_list.connect("row-activated", app.on_nav_selected)

    for header, nav_items in _sidebar_nav_sections():
        header_row = Gtk.ListBoxRow()
        header_row.nav_id = ""
        header_row.add_css_class("sidebar-group-row")
        if hasattr(header_row, "set_activatable"):
            header_row.set_activatable(False)
        if hasattr(header_row, "set_selectable"):
            header_row.set_selectable(False)
        header_row.set_child(Gtk.Label(label=header, xalign=0, css_classes=["sidebar-header"]))
        app.nav_list.append(header_row)

        for nid, icon, txt in nav_items:
            row = Gtk.ListBoxRow()
            row.nav_id = nid
            box = Gtk.Box(spacing=12, margin_start=12, margin_top=8, margin_bottom=8)
            box.append(Gtk.Image.new_from_icon_name(icon))
            box.append(Gtk.Label(label=txt))
            row.set_child(box)
            app.nav_list.append(row)

    # Fork: the list scrolls, so its height never sets the window's minimum height. Unscrolled,
    # a long Recent section made the content taller than an 800 px window and pushed the
    # player bar off the bottom.
    app.nav_scroll = Gtk.ScrolledWindow(
        vexpand=True,
        hscrollbar_policy=Gtk.PolicyType.NEVER,
        vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
        css_classes=["sidebar-scroll"],
    )
    app.nav_scroll.set_child(app.nav_list)
    app.sidebar_box.append(app.nav_scroll)
    app.paned.set_start_child(app.sidebar_box)
    app.paned.set_shrink_start_child(False)
    _body_mark("sidebar")
    # Fork: non-homogeneous, so a hidden page's width never props the window open.
    app.right_stack = Gtk.Stack(
        transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
        hhomogeneous=False,
        vhomogeneous=False,
    )
    # Fork: the content area has its own width breakpoints (track columns, album hero);
    # see install_adaptive_layout.
    app.content_bin = Adw.BreakpointBin(child=app.right_stack, width_request=360, height_request=240)
    app.paned.set_end_child(app.content_bin)
    _body_mark("right-stack")

    app._build_grid_view()
    _body_mark("grid-view")
    app._build_tracks_view()
    _body_mark("tracks-view")
    app._build_settings_page()
    _body_mark("settings-page")
    app._build_search_view()
    _body_mark("search-view")
    app.paned.set_position(int(ui_config.WINDOW_WIDTH * ui_config.SIDEBAR_RATIO))
    _body_mark("done")


def build_player_bar(app, container):
    # Shell: bar overlay + revealer stacked vertically.
    # The overlay wraps only the bar so overlaid buttons stay pinned to the bar.
    app._player_bar_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    app._player_bar_shell.add_css_class("player-overlay-container")
    container.append(app._player_bar_shell)

    app.player_overlay = Gtk.Overlay()
    app._player_bar_shell.append(app.player_overlay)

    app.bottom_bar = Gtk.CenterBox(css_classes=["card-bar"])
    app.player_overlay.set_child(app.bottom_bar)
    bottom_click = Gtk.GestureClick()
    bottom_click.set_button(0)
    bottom_click.connect("released", lambda *_args: app.close_queue_drawer())
    app.bottom_bar.add_controller(bottom_click)

    app.mini_controls = Gtk.Box(spacing=4, valign=Gtk.Align.START, halign=Gtk.Align.END)
    app.mini_controls.set_margin_top(6)
    app.mini_controls.set_margin_end(6)
    app.mini_controls.set_visible(False)

    m_restore = Gtk.Button(icon_name="ebb-pip-exit-symbolic", css_classes=["flat", "circular"])
    m_restore.set_tooltip_text("Leave Mini Player")  # fork
    m_restore.connect("clicked", app.toggle_mini_mode)

    m_close = Gtk.Button(icon_name="window-close-symbolic", css_classes=["flat", "circular"])
    m_close.connect("clicked", lambda b: app.win.close())

    app.mini_controls.append(m_restore)
    app.mini_controls.append(m_close)
    app.player_overlay.add_overlay(app.mini_controls)

    # ── Mini-mode queue arrow (overlaid on bar, bottom-center) ────
    app.mini_queue_arrow = Gtk.Button(
        icon_name="pan-down-symbolic",
        css_classes=["flat", "circular", "mini-queue-arrow"],
    )
    app.mini_queue_arrow.set_tooltip_text("Queue")
    app.mini_queue_arrow.set_visible(False)
    app.mini_queue_arrow.connect("clicked", app.toggle_mini_queue)
    app.mini_queue_arrow.set_valign(Gtk.Align.END)
    app.mini_queue_arrow.set_halign(Gtk.Align.CENTER)
    app.mini_queue_arrow.set_margin_bottom(0)
    app.player_overlay.add_overlay(app.mini_queue_arrow)

    # ── Mini-mode queue drawer (revealer below the bar overlay) ────
    app.mini_queue_revealer = Gtk.Revealer(
        transition_type=Gtk.RevealerTransitionType.NONE,
    )
    app.mini_queue_revealer.set_transition_duration(0)
    app.mini_queue_revealer.set_reveal_child(False)
    app.mini_queue_revealer.set_visible(False)

    mini_q_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0,
                         css_classes=["mini-queue-drawer"],
                         halign=Gtk.Align.FILL,
                         hexpand=True)
    mini_q_head = Gtk.Box(spacing=8, margin_start=10, margin_end=10, margin_top=0, margin_bottom=4)
    mini_q_head.append(Gtk.Label(label="Queue", xalign=0, hexpand=True,
                                 css_classes=["heading"]))
    app.mini_queue_count_label = Gtk.Label(label="", css_classes=["dim-label"])
    mini_q_head.append(app.mini_queue_count_label)
    mini_q_box.append(mini_q_head)

    app.mini_queue_list = Gtk.ListBox(css_classes=["tracks-list", "mini-queue-list"])
    app.mini_queue_list.connect("row-activated", app.on_queue_track_selected)
    app.mini_queue_scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=False)
    app.mini_queue_scroll.set_size_request(-1, 500)
    app.mini_queue_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    app.mini_queue_scroll.set_margin_start(10)
    app.mini_queue_scroll.set_margin_end(10)
    app.mini_queue_scroll.set_margin_bottom(10)
    app.mini_queue_scroll.set_child(app.mini_queue_list)
    mini_q_box.append(app.mini_queue_scroll)

    app.mini_queue_revealer.set_child(mini_q_box)
    app._player_bar_shell.append(app.mini_queue_revealer)

    side_panel_width = 340
    app.player_side_panel_width = side_panel_width

    left_panel = Gtk.Box()
    left_panel.set_hexpand(False)
    left_panel.set_halign(Gtk.Align.START)

    app.info_area = Gtk.Box(spacing=14, valign=Gtk.Align.CENTER, halign=Gtk.Align.START)
    app.info_area.set_hexpand(False)
    app.art_img = Gtk.Image()
    app.art_img.set_size_request(80, 80)
    app.art_img.set_margin_top(6)
    app.art_img.set_margin_start(6)
    app.art_img.set_margin_bottom(6)
    app.art_img.add_css_class("playback-art")
    app.art_img.set_valign(Gtk.Align.CENTER)  # fork: square at every tier's size (its background shows)
    gest = Gtk.GestureClick()
    gest.connect("pressed", app.on_player_art_clicked)
    app.art_img.add_controller(gest)

    text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, spacing=0)
    text_box.set_hexpand(False)
    text_box.set_size_request(120, -1)
    title_row = Gtk.Box(spacing=2, valign=Gtk.Align.CENTER, hexpand=False)
    app.lbl_title = Gtk.Label(xalign=0, css_classes=["player-title"], ellipsize=3)
    # Fork: say so when nothing is playing instead of leaving a blank hole (cleared in play_track).
    app.lbl_title.set_label("Nothing playing")
    app.lbl_title.add_css_class("player-idle")
    app.lbl_title.set_single_line_mode(True)
    app.lbl_title.set_width_chars(-1)
    app.lbl_title.set_max_width_chars(32)
    app.lbl_title.set_hexpand(False)
    app.lbl_title.set_halign(Gtk.Align.START)
    app.track_fav_btn = Gtk.Button(css_classes=["flat", "circular", "player-heart-btn"], icon_name="hiresti-favorite-outline-symbolic", valign=Gtk.Align.START)
    app.track_fav_btn.set_margin_top(0)
    app.track_fav_btn.set_margin_start(5)
    app.track_fav_btn.set_tooltip_text("Favorite Track")
    app.track_fav_btn.set_sensitive(False)
    app.track_fav_btn.set_visible(False)
    app.track_fav_btn.connect("clicked", app.on_track_fav_clicked)
    app.lbl_artist = Gtk.Button(css_classes=["flat", "player-artist-btn"])
    app.lbl_artist.set_halign(Gtk.Align.START)
    _artist_lbl = Gtk.Label(xalign=0, css_classes=["player-artist"], ellipsize=3)
    _artist_lbl.set_single_line_mode(True)
    _artist_lbl.set_width_chars(6)
    _artist_lbl.set_max_width_chars(32)
    app.lbl_artist.set_child(_artist_lbl)
    app.lbl_artist._inner_label = _artist_lbl
    app.lbl_artist.connect("clicked", lambda _b: app.on_player_artist_clicked())
    app.lbl_artist.set_cursor_from_name("pointer")  # fork: it's a link

    app.lbl_album = Gtk.Button(css_classes=["flat", "player-album-btn"])
    app.lbl_album.set_halign(Gtk.Align.START)
    _album_lbl = Gtk.Label(xalign=0, css_classes=["player-album"], ellipsize=3)
    _album_lbl.set_single_line_mode(True)
    _album_lbl.set_width_chars(6)
    _album_lbl.set_max_width_chars(32)
    app.lbl_album.set_child(_album_lbl)
    app.lbl_album._inner_label = _album_lbl
    app.lbl_album.connect("clicked", lambda _b: app.on_player_album_clicked())
    app.lbl_album.set_cursor_from_name("pointer")  # fork: it's a link

    title_row.append(app.lbl_title)
    title_row.append(app.track_fav_btn)
    text_box.append(title_row)
    text_box.append(app.lbl_artist)
    text_box.append(app.lbl_album)

    app.info_area.append(app.art_img)
    context_menu.tag(app.info_area, lambda: getattr(app, "playing_track", None), "track")
    app.info_area.append(text_box)
    left_panel.set_overflow(Gtk.Overflow.HIDDEN)
    left_panel.append(app.info_area)
    app.player_left_panel = left_panel
    app.player_left_clamp = None
    app.player_text_box = text_box
    app.player_title_row = title_row  # fork: ui/mini_player.py lays these out for its cover
    app.bottom_bar.set_start_widget(left_panel)

    center_panel = Gtk.Box()
    center_panel.set_hexpand(True)
    center_panel.set_halign(Gtk.Align.FILL)

    center_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        valign=Gtk.Align.CENTER,
        halign=Gtk.Align.FILL,
        hexpand=True,
        spacing=8,
    )
    ctrls = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER)
    ctrls.add_css_class("player-ctrls-box")

    # Fork: Shuffle and Repeat flank the transport (actions/play_modes.py); upstream had one
    # five-mode button among the side controls.
    from actions import play_modes

    app.shuffle_btn, app.repeat_btn = play_modes.buttons(app)
    ctrls.append(app.shuffle_btn)

    btn_prev = Gtk.Button(icon_name="media-skip-backward-symbolic", css_classes=["flat", "transport-btn"])
    btn_prev.connect("clicked", app.on_prev_track)
    btn_prev.set_tooltip_text("Previous Track (Ctrl+←)")
    ctrls.append(btn_prev)

    app.play_btn = Gtk.Button(icon_name="media-playback-start-symbolic", css_classes=["pill", "transport-main-btn"])
    app.play_btn.connect("clicked", app.on_play_pause)
    app.play_btn.set_tooltip_text("Play / Pause (Space)")
    ctrls.append(app.play_btn)

    btn_next = Gtk.Button(icon_name="media-skip-forward-symbolic", css_classes=["flat", "transport-btn"])
    btn_next.connect("clicked", lambda b: app.on_next_track())
    btn_next.set_tooltip_text("Next Track (Ctrl+→)")
    ctrls.append(btn_next)
    ctrls.append(app.repeat_btn)
    center_box.append(ctrls)

    app.timeline_box = Gtk.Box(spacing=12, orientation=Gtk.Orientation.HORIZONTAL)
    attr_list = Pango.AttrList.from_string("font-features 'tnum=1'")
    app.lbl_current_time = Gtk.Label(label="0:00", css_classes=["dim-label"])
    app.lbl_current_time.set_attributes(attr_list)
    app.lbl_current_time.set_width_chars(5)
    app.lbl_current_time.set_max_width_chars(5)
    app.lbl_current_time.set_xalign(1.0)
    app.lbl_total_time = Gtk.Label(label="0:00", css_classes=["dim-label"])
    app.lbl_total_time.set_attributes(attr_list)
    app.lbl_total_time.set_width_chars(5)
    app.lbl_total_time.set_max_width_chars(5)
    app.lbl_total_time.set_xalign(0.0)
    app.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    app.scale.set_hexpand(True)
    app.scale.add_css_class("progress-scale")
    app.scale.connect("value-changed", app.on_seek)
    app.timeline_box.append(app.lbl_current_time)
    app.timeline_box.append(app.scale)
    app.timeline_box.append(app.lbl_total_time)
    # Fixed, centred width instead of filling the whole centre panel — the
    # bar stretched edge-to-edge on wide windows and read as too long.
    # Fork: the width is per window tier (apply_layout_tier); 560 is the "full" tier.
    app.timeline_box.set_size_request(560, -1)
    app.timeline_box.set_hexpand(False)
    app.timeline_box.set_halign(Gtk.Align.CENTER)
    center_box.append(app.timeline_box)

    app.tech_box = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, margin_top=4)
    # Keep a stable reserved slot so playback start/stop does not shift controls.
    app.tech_box.set_size_request(-1, 22)
    app.bp_label = None
    app.lbl_tech = Gtk.Label(label="", ellipsize=3, visible=True)
    app.tech_box.append(app.lbl_tech)
    center_box.append(app.tech_box)

    center_panel.append(center_box)
    app.bottom_bar.set_center_widget(center_panel)
    app.player_center_panel = center_panel  # fork: ui/mini_player.py
    app.player_center_box = center_box
    app.player_ctrls = ctrls

    right_panel = Gtk.Box()
    right_panel.set_hexpand(False)
    right_panel.set_halign(Gtk.Align.END)

    app.vol_box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER)
    app.vol_box.set_hexpand(False)
    app.vol_box.set_halign(Gtk.Align.END)

    app.playback_status_btn = Gtk.Button(
        icon_name="hiresti-status-normal-symbolic",
        css_classes=["flat", "circular", "player-side-btn"],
    )
    app.playback_status_btn.set_focusable(False)
    app.playback_status_btn.set_tooltip_text("Signal path: standard (system mixer)")
    app.vol_box.append(app.playback_status_btn)

    app.dsp_btn = Gtk.Button(icon_name="hiresti-eq-symbolic", css_classes=["flat", "circular", "player-side-btn", "eq-btn"])
    app.dsp_btn.set_tooltip_text("Open DSP Workspace")
    app.dsp_btn.connect("clicked", app.open_dsp_workspace)
    app.vol_box.append(app.dsp_btn)

    app.vol_btn = Gtk.Button(icon_name="hiresti-volume-high-symbolic", css_classes=["flat", "player-side-btn"])
    app.vol_pop = app._build_volume_popover()
    app.vol_pop.set_parent(app.vol_btn)
    app.vol_btn.connect("clicked", lambda b: app.vol_pop.popup())
    app.vol_btn.set_tooltip_text("Volume")
    app.vol_box.append(app.vol_btn)

    right_panel.append(Gtk.Box(hexpand=True))
    right_panel.append(app.vol_box)
    app.player_right_panel = right_panel
    app.bottom_bar.set_end_widget(right_panel)
    from ui import mini_player  # fork: the mini player's cover layout and its button (#18)
    mini_player.build(app)

    # Fork: width tiers come from window breakpoints (apply_layout_tier); upstream's
    # notify::width handler never fired (GTK4 widgets have no width property).
    app._player_bar_layout_tier = "full"

    # Start/end use content width to avoid large dead space on wide windows.


# ---------------------------------------------------------------- adaptive layout (fork)
# Upstream pinned the window at >= 1034 px: the player bar is a Gtk.CenterBox, whose minimum is
# the sum of its parts, and its timeline had a fixed 560 px size request. The bar's own width
# tiers listened to notify::width, which GTK4 widgets don't have, so they never ran. Window
# breakpoints now pick a tier; each tier's minimum content width fits the narrowest window in
# it, so the app tiles in a half-width (or narrower) niri column.
# Play modes: Shuffle and Repeat in the transport row. Splitting the one play-mode button in two
# (r30) took the tiny tier's bar to 466 px (cover and title 166 + transport 216 + the card's
# margins and padding 84), past windows under ~476 px: every page was cut off on the right.
# "micro" (<= 480 px) leaves them to Now Playing, which has both: the bar's minimum is 400.
#           timeline  side ctrls  quality row  album  cover  text  sidebar collapsed  play modes
_LAYOUT_TIERS = {
    "full": (560, True, True, True, 80, 120, False, True),
    "wide": (400, True, True, True, 80, 120, False, True),
    "medium": (240, True, True, True, 64, 110, False, True),
    "narrow": (220, False, False, True, 64, 110, True, True),
    "tiny": (150, False, False, False, 56, 90, True, True),
    "micro": (150, False, False, False, 56, 90, True, False),
}
_TIER_CONDITIONS = (
    ("wide", "max-width: 1079px and min-width: 900px"),
    ("medium", "max-width: 899px and min-width: 761px"),
    ("narrow", "max-width: 760px and min-width: 601px"),
    ("tiny", "max-width: 600px and min-width: 481px"),
    ("micro", "max-width: 480px"),
)
MAIN_MIN_SIZE = (420, 480)


def apply_main_min_size(app):
    """Explicit minimum size: windows with breakpoints don't derive one from their content."""
    win = getattr(app, "win", None)
    if win is not None:
        win.set_size_request(*MAIN_MIN_SIZE)


def apply_layout_tier(app, tier):
    """Size the player bar and the sidebar for a window-width tier (see _LAYOUT_TIERS)."""
    spec = _LAYOUT_TIERS.get(tier)
    if spec is None:
        tier, spec = "full", _LAYOUT_TIERS["full"]
    timeline, side, tech, album, cover, text, collapse, modes = spec
    app._layout_tier = tier
    app._player_bar_layout_tier = tier
    if not getattr(app, "is_mini_mode", False):  # mini mode owns the bar while it's active
        if getattr(app, "timeline_box", None) is not None:
            app.timeline_box.set_size_request(timeline, -1)
        for name, show in (("vol_box", side), ("tech_box", tech), ("lbl_album", album),
                           ("shuffle_btn", modes), ("repeat_btn", modes)):
            widget = getattr(app, name, None)
            if widget is not None:
                widget.set_visible(show)
        if getattr(app, "art_img", None) is not None:
            app.art_img.set_size_request(cover, cover)
            set_bar_cover_size(app, cover)
        if getattr(app, "player_text_box", None) is not None:
            app.player_text_box.set_size_request(text, -1)
    _set_sidebar_collapsed(app, collapse)


def set_bar_cover_size(app, px):
    """Fork: the tiers' smaller covers never showed. load_img pins a Gtk.Image's pixel size to
    the size it loads at (80), and the pixel size beats the size request, so the cover stayed
    80 px in every tier. The cover now loads at the tier's size (load_cover_art reads
    _bar_art_px), and a tier change reloads it from the disk cache at the new size, so a
    widening window does not stretch a smaller bitmap."""
    art = app.art_img
    if getattr(app, "_bar_art_px", 80) == px and art.get_pixel_size() == px:
        return
    app._bar_art_px = px
    art.set_pixel_size(px)
    ref = getattr(app, "_bar_cover_ref", None)
    url = app._get_tidal_image_url(ref) if ref and hasattr(app, "_get_tidal_image_url") else None
    if url:
        import utils

        utils.load_img(art, url, app.cache_dir, px)


def reconcile_layout_tier(app, force=False):
    """Apply the tier of the window's current breakpoint ("full" when none applies)."""
    win = getattr(app, "win", None)
    current = win.get_current_breakpoint() if win is not None and hasattr(win, "get_current_breakpoint") else None
    tier = "full"
    for name, bp in (getattr(app, "_layout_breakpoints", None) or {}).items():
        if bp is current:
            tier = name
    if force or tier != getattr(app, "_layout_tier", None):
        apply_layout_tier(app, tier)
    return False


def install_adaptive_layout(app):
    win = getattr(app, "win", None)
    if win is None or not hasattr(win, "add_breakpoint"):
        return
    apply_main_min_size(app)
    app._layout_breakpoints = {}
    for name, condition in _TIER_CONDITIONS:
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(condition))
        win.add_breakpoint(bp)
        app._layout_breakpoints[name] = bp
    win.connect("notify::current-breakpoint", lambda *_a: reconcile_layout_tier(app))
    reconcile_layout_tier(app, force=True)
    _install_content_breakpoints(app)


def _install_content_breakpoints(app):
    """Content-width breakpoints (independent of the sidebar): which track columns fit, album hero size.

    Content width   Track table                         Album / playlist hero
    >= 1600         artist 270 px, album 320 px          full
    >= 1350         artist 220 px, album 260 px          full
    >= 1100         artist 170 px, album 210 px          full
    >= 960          title | artist | album | time       full
    820 - 959       title over artist | album | time    full
    680 - 819       title over artist | time            full
    580 - 679       title over artist | time            tighter margins
    < 580           title over artist | time            action icons below Play/Shuffle
    < 520           (same), selection bar uses plain buttons instead of 32 px-padded pills;
                    rows: 8 px gaps, 40 px time, no "+" / trash (both in ⋮)

    The cover keeps its size request: the scrolled page sizes the hero to its *minimum* height,
    so a smaller request there lets the drawn cover overflow onto the track list.
    """
    content_bin = getattr(app, "content_bin", None)
    if content_bin is None:
        return
    from ui.track_table import track_columns

    cols = track_columns(app)
    no_artist = [(cols, "artist-column", False)]
    no_album = no_artist + [(cols, "album-column", False)]
    tight = []
    if getattr(app, "album_header_box", None) is not None:
        tight += [(app.album_header_box, "margin-start", 16), (app.album_header_box, "margin-end", 16)]
    small = list(tight)
    primary = getattr(app, "album_primary_actions_box", None)
    actions_row = primary.get_parent() if primary is not None else None
    if actions_row is not None and getattr(app, "album_action_btns_box", None) is not None:
        small += [
            (actions_row, "orientation", Gtk.Orientation.VERTICAL),
            (app.album_action_btns_box, "halign", Gtk.Align.START),
        ]
    # The selection bar (Select All / Add to Playlist / Cancel) is three pills, about 433 px at
    # minimum, and its closed slide revealer still counts that width: below ~500 px of content the
    # album page overflowed sideways. Plain buttons and tighter spacing take it to ~280 px.
    revealer = getattr(app, "track_list_select_revealer", None)
    select_bar = revealer.get_child() if revealer is not None else None
    bar_btns = [
        b
        for b in (getattr(app, n, None) for n in ("track_list_select_all_btn", "track_list_add_selected_btn", "track_list_select_cancel_btn"))
        if b is not None
    ]
    compact = small + (
        [(select_bar, "spacing", 6), (select_bar, "margin-start", 4), (select_bar, "margin-end", 4)]
        if select_bar is not None
        else []
    )
    # Fork: track rows' gaps 16 -> 8, the time cell 64 -> 40, no "+" / trash (⋮ has both).
    compact += [(cols, "row-gap", 8), (cols, "time-width", 40), (cols, "row-tools", False), (cols, "wide", False)]
    def widths(artist, album):
        return [(cols, "artist-width", artist), (cols, "album-width", album)]

    # Several conditions can match at once; AdwBreakpointBin applies the last matching one, so
    # the min-width tiers go in ascending order (none of them overlaps a max-width one).
    for condition, setters, plain_bar in (
        ("min-width: 1100px", widths(170, 210), False),
        ("min-width: 1350px", widths(220, 260), False),
        ("min-width: 1600px", widths(270, 320), False),
        ("max-width: 959px", no_artist, False),
        ("max-width: 819px", no_album, False),
        ("max-width: 679px", no_album + tight, False),
        ("max-width: 579px", no_album + small, False),
        ("max-width: 519px", no_album + compact, True),
    ):
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(condition))
        for obj, prop, value in setters:
            bp.add_setter(obj, prop, value)
        if plain_bar and bar_btns:
            # CSS classes aren't a breakpoint setter target, so toggle them on apply/unapply.
            bp.connect("apply", lambda _bp: [b.remove_css_class("pill") for b in bar_btns])
            bp.connect("unapply", lambda _bp: [b.add_css_class("pill") for b in bar_btns])
        content_bin.add_breakpoint(bp)


def _sidebar_backdrop(app):
    backdrop = getattr(app, "_sidebar_backdrop", None)
    if backdrop is None:
        backdrop = Gtk.Box(css_classes=["sidebar-backdrop"], hexpand=True, vexpand=True, visible=False)
        click = Gtk.GestureClick()
        click.connect("released", lambda *_a: hide_sidebar_overlay(app))
        backdrop.add_controller(click)
        app._sidebar_backdrop = backdrop
    return backdrop


def _set_sidebar_collapsed(app, collapsed):
    """Narrow windows: move the sidebar out of the paned into a floating overlay (hidden)."""
    collapsed = bool(collapsed)
    if collapsed == bool(getattr(app, "_sidebar_collapsed", False)):
        return
    sidebar = getattr(app, "sidebar_box", None)
    paned = getattr(app, "paned", None)
    overlay = getattr(app, "body_overlay", None)
    if sidebar is None or paned is None or overlay is None:
        return
    backdrop = _sidebar_backdrop(app)
    if collapsed:
        app._sidebar_collapsed = True
        paned.set_start_child(None)
        sidebar.add_css_class("sidebar-floating")
        sidebar.set_halign(Gtk.Align.START)
        sidebar.set_size_request(280, -1)
        sidebar.set_visible(False)
        backdrop.set_visible(False)
        overlay.add_overlay(backdrop)
        overlay.add_overlay(sidebar)
    else:
        overlay.remove_overlay(sidebar)
        overlay.remove_overlay(backdrop)
        sidebar.remove_css_class("sidebar-floating")
        sidebar.set_halign(Gtk.Align.FILL)
        sidebar.set_size_request(-1, -1)
        sidebar.set_visible(True)
        paned.set_start_child(sidebar)
        paned.set_shrink_start_child(False)
        app._sidebar_collapsed = False
        restore = getattr(app, "_restore_paned_position_after_layout", None)
        if callable(restore):
            GLib.idle_add(restore)
    toggle = getattr(app, "sidebar_toggle_btn", None)
    if toggle is not None:
        toggle.set_visible(collapsed)


def toggle_sidebar_overlay(app, show=None):
    """Show/hide the floating sidebar. No-op (returns False) while the sidebar is docked."""
    if not getattr(app, "_sidebar_collapsed", False):
        return False
    sidebar = app.sidebar_box
    if show is None:
        show = not sidebar.get_visible()
    sidebar.set_visible(bool(show))
    _sidebar_backdrop(app).set_visible(bool(show))
    return True


def hide_sidebar_overlay(app):
    """Close the floating sidebar if it's open; True when it was."""
    if getattr(app, "_sidebar_collapsed", False) and app.sidebar_box.get_visible():
        return toggle_sidebar_overlay(app, False)
    return False
