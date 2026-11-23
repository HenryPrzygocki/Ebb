import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GObject, Pango

from app.app_remote_control import REMOTE_ACCESS_MODES
from core import brand  # fork
from ui import account  # fork
from ui import offline  # fork
from ui import shelf  # fork
import utils
from ui.track_table import build_tracks_header, append_header_action_spacers

PAGE_INSET = 32  # fork: where every page's content starts (left and right)


# Fork: what the selected driver does, under the Audio Driver row. Upstream's fixed text
# recommended "ALSA (auto) for most setups" and didn't mention Auto or PipeWire.
_DRIVER_SUMMARY = {
    "Auto (Default)": "The system's default output, shared with other apps.",
    "PipeWire": "A PipeWire output, shared with other apps.",
    "ALSA (auto)": "Opens the device directly: other apps can't play on it meanwhile.",
    "ALSA (mmap)": "Opens the device directly, with zero-copy writes.",
    "USB Rawlink v2": "Talks to a USB DAC directly, past the kernel's USB audio driver.",
}
_DRIVER_SUMMARY_FALLBACK = "How Ebb reaches the output device."


def _driver_summary(driver):
    """The summary for a driver id; the ids keep upstream's full-width parentheses."""
    key = str(driver or "").replace("（", " (").replace("）", ")").replace("  (", " (").strip()
    return _DRIVER_SUMMARY.get(key, _DRIVER_SUMMARY_FALLBACK)


def _row_follows(row, control):
    """Fork: a driver-specific Audio Output row shows only while its control applies. The
    actions code makes the control insensitive otherwise (on_driver_changed and the bit-depth
    sync), which left five of the nine rows greyed out under the default driver."""
    def sync(*_args):
        row.set_visible(bool(control.get_sensitive()))

    control.connect("notify::sensitive", sync)
    sync()


def build_grid_view(app):
    grid_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["home-view"])
    # Fork: every page's content starts 32 px in (PAGE_INSET): grid pages were at 20, album
    # pages at 32, search at 32 plus a centring clamp, Settings at 40, so the left edge jumped
    # between pages. The title also sat 12 px right of its subtitle (.section-title's margin).
    title_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=4,
        margin_start=PAGE_INSET,
        margin_end=PAGE_INSET,
        margin_top=28,
        margin_bottom=10,
        css_classes=["home-topbar"],
    )
    app.grid_title_box = title_box
    title_row = Gtk.Box(spacing=12)
    app.grid_title_row = title_row
    app.grid_title_label = Gtk.Label(label="Home", xalign=0, css_classes=["section-title"])
    app.grid_subtitle_label = Gtk.Label(
        label="Fresh picks and playlists tailored to your listening",
        xalign=0.0,
        ellipsize=3,
        hexpand=True,
        halign=Gtk.Align.FILL,
        css_classes=["home-subtitle", "dim-label"],
    )
    app.artist_fav_btn = Gtk.Button(
        css_classes=["heart-btn"],
        icon_name="hiresti-favorite-symbolic",
        visible=False,
    )
    app.artist_fav_btn.connect("clicked", app.on_artist_fav_clicked)
    title_row.append(app.grid_title_label)
    title_row.append(app.artist_fav_btn)
    title_row.append(Gtk.Box(hexpand=True))
    title_box.append(title_row)
    # Fork: subtitle under the title, not floating at the far right edge (it also kept the
    # header from shrinking on narrow windows).
    title_box.append(app.grid_subtitle_label)
    grid_vbox.append(title_box)

    app.login_prompt_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=20,
        hexpand=True,
        halign=Gtk.Align.FILL,
        valign=Gtk.Align.CENTER,
        vexpand=True,
    )
    app.login_prompt_box.set_visible(False)
    prompt_card = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=12,
        margin_top=12,
        margin_bottom=12,
        margin_start=18,
        margin_end=18,
        halign=Gtk.Align.CENTER,
        css_classes=["login-hero-card"],
    )
    # Avoid forcing a hard minimum width; small windows (e.g. mini mode / narrow
    # restored width) can otherwise trigger GtkStack measure warnings.
    prompt_card.set_size_request(-1, -1)
    prompt_icon = Gtk.Image(
        icon_name=brand.APP_ID,
        pixel_size=104,
        css_classes=["dim-label", "login-hero-icon"],
        halign=Gtk.Align.CENTER,
    )
    prompt_label = Gtk.Label(
        label=offline.SIGN_IN_TITLE,
        css_classes=["heading", "login-hero-title"],
        wrap=True,
        justify=Gtk.Justification.CENTER,
        xalign=0.5,
    )
    prompt_sub = Gtk.Label(
        label=offline.SIGN_IN_TEXT,
        css_classes=["dim-label", "login-hero-subtitle"],
        wrap=True,
        justify=Gtk.Justification.CENTER,
        xalign=0.5,
    )
    prompt_btn = Gtk.Button(
        label="Sign In",
        css_classes=["pill", "suggested-action", "login-hero-btn"],
        halign=Gtk.Align.CENTER,
    )
    prompt_btn.set_size_request(220, 46)
    prompt_btn.connect("clicked", app.on_login_clicked)
    prompt_card.append(prompt_icon)
    prompt_card.append(prompt_label)
    prompt_card.append(prompt_sub)
    prompt_card.append(prompt_btn)
    # Fork: the same card when TIDAL can't be reached at startup (ui/offline.py).
    retry_btn = Gtk.Button(label="Try Again", css_classes=["pill", "suggested-action", "login-hero-btn"],
                           halign=Gtk.Align.CENTER, visible=False)
    retry_btn.set_size_request(220, 46)
    retry_btn.connect("clicked", lambda _b: offline.retry(app))
    again_btn = Gtk.Button(label="Sign In Again", css_classes=["flat"], halign=Gtk.Align.CENTER, visible=False)
    again_btn.connect("clicked", lambda b: offline.sign_in_again(app, b))
    prompt_card.append(retry_btn)
    prompt_card.append(again_btn)
    app.login_prompt_title, app.login_prompt_text = prompt_label, prompt_sub
    app.login_prompt_btn, app.login_retry_btn, app.login_again_btn = prompt_btn, retry_btn, again_btn
    app.login_prompt_box.append(prompt_card)
    grid_vbox.append(app.login_prompt_box)

    app.alb_scroll = Gtk.ScrolledWindow(vexpand=True)
    app.collection_content_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=20,
        margin_start=PAGE_INSET,
        margin_end=PAGE_INSET,
        margin_bottom=32,
        css_classes=["home-content-box"],
    )
    app.collection_base_margin_start = PAGE_INSET
    app.collection_base_margin_end = PAGE_INSET
    app.collection_base_margin_bottom = 32
    app.alb_scroll.set_child(app.collection_content_box)
    grid_vbox.append(app.alb_scroll)
    app.right_stack.add_named(grid_vbox, "grid_view")


def sync_lossless_banner(app):
    """Fork: reveal the banner while the login type caps most tracks at AAC (ui/account.py)."""
    account.sync_banner(app)


def toggle_login_view(app, logged_in):
    sync_lossless_banner(app)
    app.login_prompt_box.set_visible(not logged_in)
    app.alb_scroll.set_visible(logged_in)
    if hasattr(app, "search_entry") and app.search_entry is not None:
        app.search_entry.set_visible(logged_in)
    if hasattr(app, "sidebar_box") and app.sidebar_box is not None:
        app.sidebar_box.set_visible(logged_in)
    if not logged_in:
        account.show_signed_out(app)  # fork
        app.grid_title_label.set_text("Welcome")
        if hasattr(app, "grid_subtitle_label") and app.grid_subtitle_label is not None:
            app.grid_subtitle_label.set_text(offline.page_subtitle(app))
        return

    display_name = "User"
    user = app.backend.user
    if user:
        meta = getattr(user, "profile_metadata", None)
        if meta:
            if isinstance(meta, dict):
                display_name = meta.get("name") or meta.get("firstName") or display_name
            else:
                display_name = getattr(meta, "name", None) or getattr(meta, "first_name", None) or display_name

        if display_name == "User" or display_name is None:
            candidates = [
                getattr(user, "first_name", None),
                getattr(user, "name", None),
                getattr(user, "firstname", None),
            ]
            for candidate in candidates:
                if candidate and isinstance(candidate, str) and candidate.strip():
                    display_name = candidate
                    break

        if (not display_name or display_name == "User") and hasattr(user, "username") and user.username:
            try:
                display_name = user.username.split("@")[0].capitalize()
            except Exception:
                display_name = user.username

    account.show_signed_in(app, display_name)  # fork: avatar, not "Hi, <name>"
    app.grid_title_label.set_text("Home")
    if hasattr(app, "grid_subtitle_label") and app.grid_subtitle_label is not None:
        app.grid_subtitle_label.set_text("Fresh picks and playlists tailored to your listening")


def build_tracks_view(app):
    trk_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["tracks-view"])
    trk_scroll = Gtk.ScrolledWindow(vexpand=True)
    app.trk_scroll = trk_scroll
    trk_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    # Header: overlay with the dimmed album cover as background, content on top.
    # The overlay's natural size must be driven by the content box (so the
    # area below the action pills doesn't sit on the bg Picture's full
    # natural texture height ~640 px). Use an empty sizing anchor as the
    # main child and add the bg Picture as a non-measured overlay child;
    # only the content is measured.
    app.album_header_overlay = Gtk.Overlay(css_classes=["album-header-overlay"])
    bg_anchor = Gtk.Box(can_target=False)
    bg_anchor.set_size_request(-1, 200)  # min-height; content usually drives
    app.album_header_overlay.set_child(bg_anchor)

    app.album_header_bg = Gtk.Picture()
    app.album_header_bg.set_can_shrink(True)
    try:
        app.album_header_bg.set_content_fit(Gtk.ContentFit.COVER)
    except Exception:
        pass
    app.album_header_bg.add_css_class("album-header-bg")
    app.album_header_bg.set_can_target(False)
    app.album_header_overlay.add_overlay(app.album_header_bg)
    # Fork: the background is blurred (CSS); clip it so the blur doesn't glow past the hero.
    app.album_header_overlay.set_overflow(Gtk.Overflow.HIDDEN)

    album_header_dim = Gtk.Box(
        css_classes=["album-header-bg-dim"], hexpand=True, vexpand=True,
        can_target=False,
    )
    app.album_header_overlay.add_overlay(album_header_dim)

    app.album_header_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=20,
        margin_top=32, margin_bottom=20, margin_start=PAGE_INSET, margin_end=PAGE_INSET,
        css_classes=["album-header-box"],
    )
    album_header_top = Gtk.Box(spacing=24, css_classes=["album-header-top"])
    app.header_art = Gtk.Picture()
    app.header_art.set_size_request(utils.COVER_SIZE, utils.COVER_SIZE)
    app.header_art.set_can_shrink(True)
    try:
        app.header_art.set_content_fit(Gtk.ContentFit.COVER)
    except Exception:
        pass
    app.header_art.add_css_class("header-art")

    info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER, hexpand=True)
    app.header_kicker = Gtk.Label(label="Album", xalign=0, css_classes=["album-kicker"])
    app.header_title = Gtk.Label(xalign=0, wrap=True, css_classes=["album-title-large"])
    # Fork #27: the artist ellipsizes and the meta line wraps. Neither could shrink, so below
    # ~460 px of content the hero (cover 237 + "1993 • 12 Tracks • 42 min") was wider than the
    # page and lost its right edge. The artist's tooltip is the full name.
    app.header_artist = Gtk.Label(xalign=0, ellipsize=3, css_classes=["album-artist-medium"])
    tap = Gtk.GestureClick()
    tap.connect("pressed", app.on_header_artist_clicked)
    app.header_artist.add_controller(tap)
    motion = Gtk.EventControllerMotion()
    motion.connect(  # fork: no hand over a playlist's creator, which leads nowhere
        "enter", lambda c, x, y: utils.set_pointer_cursor(app.header_artist, not app.header_artist.has_css_class("album-artist-plain"))
    )
    motion.connect("leave", lambda c: utils.set_pointer_cursor(app.header_artist, False))
    app.header_artist.add_controller(motion)
    app.header_meta = Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR,
                                css_classes=["album-meta", "album-meta-pill"])

    info.append(app.header_kicker)
    info.append(app.header_title)
    info.append(app.header_artist)
    info.append(app.header_meta)

    app.fav_btn = Gtk.Button(css_classes=["flat", "album-fav-btn"], icon_name="hiresti-favorite-outline-symbolic", valign=Gtk.Align.CENTER)
    app.fav_btn.set_tooltip_text("Add to Favorites")
    app.fav_btn.connect("clicked", app.on_fav_clicked)
    app.add_playlist_btn = Gtk.Button(icon_name="list-add-symbolic", css_classes=["flat", "circular", "history-scroll-btn"], valign=Gtk.Align.CENTER)
    app.add_playlist_btn.set_tooltip_text("Add Album Tracks to Playlist")
    app.add_playlist_btn.connect("clicked", app.on_add_current_album_to_playlist)
    app.remote_playlist_edit_btn = Gtk.Button(icon_name="document-edit-symbolic", css_classes=["flat", "circular", "history-scroll-btn"], valign=Gtk.Align.CENTER)
    app.remote_playlist_edit_btn.set_tooltip_text("Edit Playlist")
    app.remote_playlist_edit_btn.set_visible(False)
    app.remote_playlist_edit_btn.connect("clicked", lambda _b: app.on_remote_playlist_rename_clicked())
    app.remote_playlist_visibility_btn = Gtk.Button(icon_name="changes-prevent-symbolic", css_classes=["flat", "circular", "history-scroll-btn"], valign=Gtk.Align.CENTER)
    app.remote_playlist_visibility_btn.set_tooltip_text("Set public/private")
    app.remote_playlist_visibility_btn.set_visible(False)
    app.remote_playlist_visibility_btn.connect("clicked", lambda _b: app.on_remote_playlist_toggle_public_clicked())
    # Fork: the album page's overflow icon (it was open-menu-symbolic, a different glyph).
    app.remote_playlist_more_btn = Gtk.Button(icon_name="view-more-symbolic", css_classes=["flat", "circular", "history-scroll-btn"], valign=Gtk.Align.CENTER)
    app.remote_playlist_more_btn.set_tooltip_text("More")
    app.remote_playlist_more_btn.set_visible(False)
    app.remote_playlist_more_pop = Gtk.Popover()
    app.remote_playlist_more_pop.set_parent(app.remote_playlist_more_btn)
    more_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=0,
        margin_top=4,
        margin_bottom=4,
        margin_start=4,
        margin_end=4,
        css_classes=["playlist-more-menu"],
    )
    # Fork: the album "More actions" items live here on playlist pages (one overflow button, not two).
    for _icon, _label, _handler in (
        ("media-skip-forward-symbolic", "Play Next", "on_play_next_current_tracks_clicked"),
        ("view-list-symbolic", "Add to Queue", "on_add_current_tracks_to_queue_clicked"),
    ):
        _btn = Gtk.Button(css_classes=["flat"])
        _row = Gtk.Box(spacing=8)
        _row.append(Gtk.Image.new_from_icon_name(_icon))
        _row.append(Gtk.Label(label=_label, xalign=0))
        _btn.set_child(_row)
        _btn.connect("clicked", lambda _b, h=_handler: (app.remote_playlist_more_pop.popdown(), getattr(app, h)()))
        more_box.append(_btn)
    more_box.append(Gtk.Separator())
    # Edit Playlist
    edit_menu_btn = Gtk.Button(css_classes=["flat"])
    edit_menu_row = Gtk.Box(spacing=8)
    edit_menu_row.append(Gtk.Image.new_from_icon_name("document-edit-symbolic"))
    edit_menu_row.append(Gtk.Label(label="Edit Playlist", xalign=0))
    edit_menu_btn.set_child(edit_menu_row)
    edit_menu_btn.connect("clicked", lambda _b: (app.remote_playlist_more_pop.popdown(), app.on_remote_playlist_rename_clicked()))
    more_box.append(edit_menu_btn)
    # Toggle Visibility
    vis_menu_btn = Gtk.Button(css_classes=["flat"])
    vis_menu_row = Gtk.Box(spacing=8)
    app._vis_menu_icon = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
    app._vis_menu_label = Gtk.Label(label="Make Public", xalign=0)
    vis_menu_row.append(app._vis_menu_icon)
    vis_menu_row.append(app._vis_menu_label)
    vis_menu_btn.set_child(vis_menu_row)
    vis_menu_btn.connect("clicked", lambda _b: (app.remote_playlist_more_pop.popdown(), app.on_remote_playlist_toggle_public_clicked()))
    more_box.append(vis_menu_btn)
    # Add to Playlist
    add_menu_btn = Gtk.Button(css_classes=["flat"])
    add_menu_row = Gtk.Box(spacing=8)
    add_menu_row.append(Gtk.Image.new_from_icon_name("list-add-symbolic"))
    add_menu_row.append(Gtk.Label(label="Add to Playlist", xalign=0))
    add_menu_btn.set_child(add_menu_row)
    add_menu_btn.connect("clicked", lambda _b: (app.remote_playlist_more_pop.popdown(), app.on_add_current_album_to_playlist()))
    more_box.append(add_menu_btn)
    more_box.append(Gtk.Separator())
    # Move to Folder
    move_btn = Gtk.Button(css_classes=["flat"])
    move_row = Gtk.Box(spacing=8)
    move_row.append(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
    move_row.append(Gtk.Label(label="Move to Folder", xalign=0))
    move_btn.set_child(move_row)
    move_btn.connect("clicked", lambda _b: (app.remote_playlist_more_pop.popdown(), app.on_remote_playlist_move_to_folder_clicked()))
    more_box.append(move_btn)
    del_btn = Gtk.Button(css_classes=["flat"])
    del_row = Gtk.Box(spacing=8)
    del_row.append(Gtk.Image.new_from_icon_name("user-trash-symbolic"))
    del_row.append(Gtk.Label(label="Delete Playlist", xalign=0))
    del_btn.set_child(del_row)
    del_btn.connect("clicked", lambda _b: (app.remote_playlist_more_pop.popdown(), app.on_remote_playlist_delete_clicked()))
    more_box.append(del_btn)
    app.remote_playlist_more_pop.set_child(more_box)
    app.remote_playlist_more_btn.connect("clicked", lambda _b: app.remote_playlist_more_pop.popup())

    # Fork: GNOME's selection-mode icon (a check in a circle). Upstream's bare check mark read as
    # "done" or "added", not "pick tracks".
    app.track_list_select_btn = Gtk.ToggleButton(
        icon_name="selection-mode-symbolic",
        css_classes=["flat", "circular", "history-scroll-btn"],
        valign=Gtk.Align.CENTER,
    )
    app.track_list_select_btn.set_tooltip_text("Select Tracks")
    app.track_list_select_btn.connect("toggled", app.on_track_list_select_mode_toggled)

    app.album_action_btns_box = Gtk.Box(spacing=4, valign=Gtk.Align.CENTER, halign=Gtk.Align.END, css_classes=["album-action-btns"])
    # Fork: "Hi-Res only" for playlists, mixes and search results (ui/hires_filter.py); it shows
    # only on lists that mix qualities, so never on an album.
    from ui import hires_filter

    app.hires_chip = hires_filter.Chip(
        app, lambda: app.populate_tracks(list(getattr(app, "_hires_source", None) or []))
    )
    app.hires_chip.set_margin_end(4)
    app.album_action_btns_box.append(app.hires_chip)
    app.album_action_btns_box.append(app.fav_btn)
    app.album_action_btns_box.append(app.track_list_select_btn)
    app.album_action_btns_box.append(app.add_playlist_btn)
    # Fork: the overflow menu is the last button, as the album page's is (appended after this
    # one, and only one of them shows). On playlists it came second, after the Hi-Res chip.
    app.album_action_btns_box.append(app.remote_playlist_more_btn)

    # Top row: cover + textual info (no action icons here anymore).
    album_header_top.append(app.header_art)
    album_header_top.append(info)
    app.album_header_box.append(album_header_top)

    # Bottom row: Play / Shuffle pills on the left, secondary icons on the right.
    album_header_actions = Gtk.Box(spacing=12, css_classes=["album-header-actions"])
    app.album_primary_actions_box = Gtk.Box(
        spacing=12, valign=Gtk.Align.CENTER, halign=Gtk.Align.START, hexpand=True,
        css_classes=["album-primary-actions"],
    )
    album_header_actions.append(app.album_primary_actions_box)
    album_header_actions.append(app.album_action_btns_box)
    app.album_header_box.append(album_header_actions)
    # Fork #24: right-click on the header is the menu of what the page shows (an album, a mix
    # or a playlist: context_menu reads the kind off the object); on the artist's name, the
    # artist's menu.
    from ui import context_menu

    context_menu.tag(
        app.album_header_box,
        lambda: getattr(app, "current_remote_playlist", None) or getattr(app, "current_album", None),
    )
    context_menu.tag(app.header_artist, lambda: getattr(getattr(app, "current_album", None), "artist", None), "artist")

    app.album_header_overlay.add_overlay(app.album_header_box)
    # By default Gtk.Overlay sizes to its main child only; without this the
    # content row spills below the 280 px bg Picture and overlaps the first
    # track row of trk_body.
    app.album_header_overlay.set_measure_overlay(app.album_header_box, True)
    trk_content.append(app.album_header_overlay)

    # Restore horizontal margin for the rest of the page below the header.
    trk_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, margin_top=20, margin_start=PAGE_INSET, margin_end=PAGE_INSET)
    trk_content.append(trk_body)

    # Column header (#/Title/Artist/Album/Time) intentionally hidden:
    # build the widget so app.album_sort_buttons stays populated for any
    # callers that look it up, but don't attach it to the body.
    _tracks_head, head_btns = build_tracks_header(
        on_sort_title=lambda _b: app.on_album_sort_clicked("title"),
        on_sort_artist=lambda _b: app.on_album_sort_clicked("artist"),
        on_sort_album=lambda _b: app.on_album_sort_clicked("album"),
        on_sort_time=lambda _b: app.on_album_sort_clicked("time"),
    )
    app.album_sort_buttons = head_btns

    app.track_list = Gtk.ListBox(css_classes=["tracks-list"], margin_start=0, margin_end=0, margin_bottom=32)
    app.track_list_base_margin_bottom = 32
    app.track_list.connect("row-activated", app.on_track_selected)
    # Fork: an empty list says why (still loading, failed load, empty playlist) with a retry.
    placeholder = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=32, margin_bottom=32,
        halign=Gtk.Align.CENTER, css_classes=["track-list-placeholder"],
    )
    app.track_list_placeholder_label = Gtk.Label(
        wrap=True, justify=Gtk.Justification.CENTER, max_width_chars=48, css_classes=["dim-label"],
    )
    app.track_list_placeholder_retry = Gtk.Button(
        label="Try Again", halign=Gtk.Align.CENTER, visible=False, css_classes=["pill"],
    )
    app.track_list_placeholder_retry.connect("clicked", lambda _b: app.retry_track_view())
    placeholder.append(app.track_list_placeholder_label)
    placeholder.append(app.track_list_placeholder_retry)
    app.track_list.set_placeholder(placeholder)
    trk_body.append(app.track_list)

    app.track_list_select_revealer = Gtk.Revealer(
        transition_type=Gtk.RevealerTransitionType.SLIDE_UP,
        transition_duration=180,
        reveal_child=False,
    )
    select_bar = Gtk.Box(
        spacing=12,
        margin_top=8, margin_bottom=8, margin_start=12, margin_end=12,
        css_classes=["select-action-bar"],
    )
    app.track_list_select_count_label = Gtk.Label(
        label="0 selected", xalign=0, hexpand=True, css_classes=["dim-label"],
    )
    # Fork: the closed (slide) revealer still counts this bar's width; an unshrinkable count label
    # pushed the album page 14 px past a 460 px window.
    app.track_list_select_count_label.set_ellipsize(Pango.EllipsizeMode.END)
    app.track_list_select_count_label.set_width_chars(4)
    select_bar.append(app.track_list_select_count_label)
    app.track_list_select_all_btn = Gtk.Button(label="Select All", css_classes=["flat", "pill"])
    app.track_list_select_all_btn.connect("clicked", app.on_track_list_select_all_clicked)
    select_bar.append(app.track_list_select_all_btn)
    app.track_list_add_selected_btn = Gtk.Button(label="Add to Playlist", css_classes=["pill", "suggested-action"])
    app.track_list_add_selected_btn.set_sensitive(False)
    app.track_list_add_selected_btn.connect("clicked", app.on_track_list_add_selected_clicked)
    select_bar.append(app.track_list_add_selected_btn)
    app.track_list_select_cancel_btn = Gtk.Button(label="Cancel", css_classes=["flat", "pill"])
    app.track_list_select_cancel_btn.connect("clicked", lambda _b: app.exit_track_list_select_mode())
    select_bar.append(app.track_list_select_cancel_btn)
    app.track_list_select_revealer.set_child(select_bar)
    trk_body.append(app.track_list_select_revealer)

    # Similar albums section (populated async in show_album_details).
    # Placed as a sibling of trk_content (not a child) so it can use its own
    # margin_start/end that matches collection_content_box (20 px each side),
    # giving the FlowBox the same available width as the main album grid.
    app.similar_albums_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=12,
        margin_top=8,
        margin_bottom=32,
        margin_start=20,
        margin_end=20,
        visible=False,
        css_classes=["home-section", "home-generic-section"],
    )
    app.similar_albums_label = Gtk.Label(label="More by this Artist", xalign=0, hexpand=True,
                                         css_classes=["home-section-title"])
    # Fork #27: one row, like Home's sections; "Show all" opens the rest (ui/shelf.py).
    similar_head = Gtk.Box(spacing=8)
    similar_head.append(app.similar_albums_label)
    similar_more = Gtk.Button(label="Show all", css_classes=["flat", "home-section-more"], valign=Gtk.Align.CENTER)
    similar_head.append(similar_more)
    app.similar_albums_box.append(similar_head)
    app.similar_albums_flow = shelf.Shelf(button=similar_more)
    app.similar_albums_flow.add_css_class("home-flow")
    app.similar_albums_box.append(app.similar_albums_flow)
    app.similar_albums_more_row = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=8,
        visible=False,
    )
    app.similar_albums_box.append(app.similar_albums_more_row)

    trk_scroll_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    trk_scroll_container.append(trk_content)
    trk_scroll_container.append(app.similar_albums_box)
    trk_scroll.set_child(trk_scroll_container)
    trk_vbox.append(trk_scroll)
    app.right_stack.add_named(trk_vbox, "tracks")


def build_settings_page(app):
    settings_scroll = Gtk.ScrolledWindow(vexpand=True)
    settings_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-container"], spacing=20)
    settings_scroll.set_child(settings_vbox)
    settings_vbox.append(Gtk.Label(label="Settings", xalign=0, css_classes=["album-title-large"], margin_bottom=10))

    settings_vbox.append(Gtk.Label(label="General", xalign=0, css_classes=["section-title"]))
    group_cfg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-group"])

    row_window_size = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    window_size_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    window_size_info.append(Gtk.Label(label="Remember Window Size", xalign=0, css_classes=["settings-label"]))
    window_size_desc = Gtk.Label(
        label="Restore the last main window width and height on next launch",
        xalign=0,
        css_classes=["dim-label"],
    )
    window_size_desc.set_wrap(True)
    window_size_desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    window_size_desc.set_max_width_chars(56)
    window_size_info.append(window_size_desc)
    row_window_size.append(window_size_info)
    row_window_size.append(Gtk.Box(hexpand=True))
    app.remember_window_size_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.remember_window_size_switch.set_active(bool(app.settings.get("remember_window_size", False)))
    app.remember_window_size_switch.connect("state-set", app.on_remember_window_size_toggled)
    row_window_size.append(app.remember_window_size_switch)
    group_cfg.append(row_window_size)
    # Fork: make the keyboard shortcuts discoverable.
    row_keys = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    keys_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
    keys_info.append(Gtk.Label(label="Keyboard Shortcuts", xalign=0, css_classes=["settings-label"]))
    keys_info.append(
        Gtk.Label(
            label="Space plays and pauses from anywhere except text fields. Ctrl+? lists every shortcut.",
            xalign=0,
            wrap=True,
            css_classes=["dim-label"],
        )
    )
    row_keys.append(keys_info)
    keys_btn = Gtk.Button(label="Show", valign=Gtk.Align.CENTER)
    keys_btn.connect("clicked", lambda _b: app.show_shortcuts_dialog())
    row_keys.append(keys_btn)
    group_cfg.append(row_keys)
    # Fork: Ebb's own translucency (ui/glass.py).
    from ui import glass as ui_glass

    row_glass = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    glass_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
    glass_info.append(Gtk.Label(label="Window Transparency", xalign=0, css_classes=["settings-label"]))
    glass_info.append(
        Gtk.Label(
            label="The desktop shows through the backgrounds; text and artwork stay solid. "
            "Reads best with a compositor that blurs behind windows.",
            xalign=0,
            wrap=True,
            css_classes=["dim-label"],
        )
    )
    row_glass.append(glass_info)
    app.glass_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, ui_glass.MAX * 100, 5)
    app.glass_scale.set_size_request(220, -1)
    app.glass_scale.set_valign(Gtk.Align.CENTER)
    app.glass_scale.set_round_digits(0)
    app.glass_scale.set_draw_value(True)
    app.glass_scale.set_value_pos(Gtk.PositionType.RIGHT)
    app.glass_scale.set_format_value_func(lambda _s, v: "Off" if v < 0.5 else f"{v:.0f}%")
    app.glass_scale.set_value(round(ui_glass.amount(app.settings) * 100))
    app.glass_scale.connect("value-changed", lambda s: ui_glass.set_amount(app, s.get_value() / 100))
    row_glass.append(app.glass_scale)
    group_cfg.append(row_glass)
    # Fork #17: the cover grids' card size (ui/card_grid.py).
    from ui import card_grid

    row_cards = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    cards_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
    cards_info.append(Gtk.Label(label="Card Size", xalign=0, css_classes=["settings-label"]))
    cards_info.append(
        Gtk.Label(
            label="Album, artist and playlist covers fill each row; this sets how many fit. "
            "Ctrl+= and Ctrl+\u2212 change it from any page, Ctrl+0 resets it.",
            xalign=0,
            wrap=True,
            css_classes=["dim-label"],
        )
    )
    row_cards.append(cards_info)
    app.card_size_dd = Gtk.DropDown(model=Gtk.StringList.new(list(card_grid.LABELS)), valign=Gtk.Align.CENTER)
    app.card_size_dd.set_selected(card_grid.SIZES.index(card_grid.current()))

    def _on_card_size(dd, _pspec):
        i = dd.get_selected()
        if 0 <= i < len(card_grid.SIZES):
            card_grid.set_size(app, card_grid.SIZES[i])

    app.card_size_dd.connect("notify::selected", _on_card_size)
    row_cards.append(app.card_size_dd)
    group_cfg.append(row_cards)
    from ui import viz_panel  # fork: the visualizer is opt-in

    group_cfg.append(viz_panel.settings_row(app))
    settings_vbox.append(group_cfg)

    settings_vbox.append(Gtk.Label(label="Streaming", xalign=0, css_classes=["section-title"], margin_top=10))
    group_q = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-group"])
    row_q = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_q.append(Gtk.Label(label="Audio Quality", hexpand=True, xalign=0))
    app.quality_dd = Gtk.DropDown(
        model=Gtk.StringList.new(
            ["Max (Up to 24-bit, 192 kHz)", "High (16-bit, 44.1 kHz)", "Low (320 kbps)"]
        )
    )
    app.quality_dd.connect("notify::selected-item", app.on_quality_changed)
    row_q.append(app.quality_dd)
    group_q.append(row_q)
    settings_vbox.append(group_q)

    settings_vbox.append(Gtk.Label(label="Audio Output", xalign=0, css_classes=["section-title"], margin_top=10))
    group_out = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-group"])

    row_bp = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    bp_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    bp_title_box = Gtk.Box(spacing=6, orientation=Gtk.Orientation.HORIZONTAL)
    bp_title_box.append(Gtk.Label(label="Bit-Perfect Mode", xalign=0, css_classes=["settings-label"]))
    # Fork: dialog-question-symbolic is a diamond with a "?" in Papirus, which reads as a
    # broken glyph (U+FFFD); every theme draws the information icon as a circled "i".
    bp_help_btn = Gtk.Button(icon_name="dialog-information-symbolic", css_classes=["flat", "circular"])
    bp_help_btn.set_tooltip_text("About Bit-Perfect Mode")
    bp_help_pop = Gtk.Popover()
    bp_help_pop.set_parent(bp_help_btn)
    bp_help_pop.set_autohide(True)
    bp_pop_content = Gtk.Label(wrap=True, max_width_chars=44, xalign=0)
    bp_pop_content.set_markup(
        "<b>Bit-Perfect Mode</b>\n\n"
        "Sends the audio to the device untouched.\n\n"
        "• <b>Processing:</b> the EQ and DSP are bypassed, and the app's volume stays at "
        "100%. A USB DAC's own hardware volume still works.\n\n"
        "• <b>Drivers:</b> only ALSA and USB Rawlink are offered. Auto and PipeWire go "
        "through the system mixer, which can resample.\n\n"
        "• <b>The device:</b> Ebb asks the system to release it, so other apps can't play "
        "on it meanwhile."
    )
    bp_pop_box = Gtk.Box(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
    bp_pop_box.append(bp_pop_content)
    bp_help_pop.set_child(bp_pop_box)
    bp_help_btn.connect("clicked", lambda x: bp_help_pop.popup())
    bp_title_box.append(bp_help_btn)
    bp_info.append(bp_title_box)
    bp_desc = Gtk.Label(
        label="No EQ, DSP or app volume, and only drivers that reach the device directly.",
        xalign=0,
        css_classes=["dim-label"],
    )
    bp_desc.set_wrap(True)
    bp_desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    bp_desc.set_max_width_chars(56)
    bp_info.append(bp_desc)
    row_bp.append(bp_info)
    row_bp.append(Gtk.Box(hexpand=True))
    app.bp_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.bp_switch.set_active(app.settings.get("bit_perfect", False))
    app.bp_switch.connect("state-set", app.on_bit_perfect_toggled)
    row_bp.append(app.bp_switch)
    group_out.append(row_bp)

    # Bit-Perfect now implies hardware exclusive: when the user turns
    # Bit-Perfect on we filter the driver dropdown to ALSA(auto)/(mmap)/USB
    # Rawlink v2 and toggle the internal exclusive_lock_mode along with it,
    # so a separate "Force Hardware Exclusive" switch would just be a second
    # control wired to the same state. Keep `ex_switch` as a hidden stub so
    # the few remaining `getattr(app, "ex_switch", None)` call sites are
    # safe; the real intent now lives in `bp_switch`.
    app.ex_switch = None

    row_rt = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    rt_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    rt_info.append(Gtk.Label(label="Realtime Audio Priority", xalign=0, css_classes=["settings-label"]))
    rt_info.append(
        Gtk.Label(
            label="ALSA (mmap) writer thread only. Off disables SCHED_FIFO",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_rt.append(rt_info)
    row_rt.append(Gtk.Box(hexpand=True))
    app.mmap_realtime_priority_dd = Gtk.DropDown(
        model=Gtk.StringList.new(app.ALSA_MMAP_REALTIME_PRIORITY_OPTIONS)
    )
    app.mmap_realtime_priority_dd.set_valign(Gtk.Align.CENTER)
    saved_rt_profile = app.settings.get(
        "alsa_mmap_realtime_priority",
        app.ALSA_MMAP_REALTIME_PRIORITY_DEFAULT,
    )
    if saved_rt_profile not in app.ALSA_MMAP_REALTIME_PRIORITY_OPTIONS:
        saved_rt_profile = app.ALSA_MMAP_REALTIME_PRIORITY_DEFAULT
    try:
        target_idx = app.ALSA_MMAP_REALTIME_PRIORITY_OPTIONS.index(saved_rt_profile)
        app.mmap_realtime_priority_dd.set_selected(target_idx)
    except ValueError:
        app.mmap_realtime_priority_dd.set_selected(
            app.ALSA_MMAP_REALTIME_PRIORITY_OPTIONS.index(app.ALSA_MMAP_REALTIME_PRIORITY_DEFAULT)
        )
    app.mmap_realtime_priority_dd.connect(
        "notify::selected-item",
        app.on_mmap_realtime_priority_changed,
    )
    row_rt.append(app.mmap_realtime_priority_dd)

    row_lat = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    lat_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    lat_info.append(Gtk.Label(label="Output Latency", xalign=0, css_classes=["settings-label"]))
    lat_info.append(
        Gtk.Label(
            label="Target buffer size (Effective on ALSA output)",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_lat.append(lat_info)
    row_lat.append(Gtk.Box(hexpand=True))
    app.latency_dd = Gtk.DropDown(model=Gtk.StringList.new(app.LATENCY_OPTIONS))
    app.latency_dd.set_valign(Gtk.Align.CENTER)
    saved_driver = str(app.settings.get("driver", "") or "")
    app.latency_dd.set_sensitive(saved_driver in ("ALSA", "ALSA（auto）", "ALSA (mmap)", "ALSA（mmap）"))

    saved_profile = app.settings.get("latency_profile", "Standard (100ms)")
    if saved_profile not in app.LATENCY_OPTIONS:
        saved_profile = "Standard (100ms)"
    try:
        target_idx = app.LATENCY_OPTIONS.index(saved_profile)
        app.latency_dd.set_selected(target_idx)
    except ValueError:
        app.latency_dd.set_selected(1)
    app.latency_dd.connect("notify::selected-item", app.on_latency_changed)
    row_lat.append(app.latency_dd)
    group_out.append(row_lat)
    _row_follows(row_lat, app.latency_dd)

    row_drv = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    drv_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    drv_title_box = Gtk.Box(spacing=6, orientation=Gtk.Orientation.HORIZONTAL)
    drv_title_box.append(Gtk.Label(label="Audio Driver", xalign=0, css_classes=["settings-label"]))
    drv_help_btn = Gtk.Button(icon_name="dialog-information-symbolic", css_classes=["flat", "circular"])
    drv_help_btn.set_tooltip_text("About the drivers")
    drv_help_pop = Gtk.Popover()
    drv_help_pop.set_parent(drv_help_btn)
    drv_help_pop.set_autohide(True)
    drv_pop_content = Gtk.Label(wrap=True, max_width_chars=44, xalign=0)
    drv_pop_content.set_markup(
        "<b>Audio Drivers</b>\n\n"
        "• <b>Auto (Default):</b> the system's default output, shared with other apps. "
        "The system mixer can resample.\n\n"
        "• <b>PipeWire:</b> a PipeWire output you pick, also shared and possibly resampled.\n\n"
        "• <b>ALSA (auto):</b> opens the device directly, with no mixer in between. Other "
        "apps can't play on it meanwhile.\n\n"
        "• <b>ALSA (mmap):</b> the same, with memory-mapped, zero-copy writes and an "
        "optional realtime writer thread.\n\n"
        "• <b>USB Rawlink v2:</b> talks to a USB DAC directly, past the kernel's USB audio "
        "driver.\n\n"
        "Bit-Perfect Mode offers only the direct ones: ALSA and USB Rawlink."
    )
    drv_pop_box = Gtk.Box(margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
    drv_pop_box.append(drv_pop_content)
    drv_help_pop.set_child(drv_pop_box)
    drv_help_btn.connect("clicked", lambda x: drv_help_pop.popup())
    drv_title_box.append(drv_help_btn)
    drv_info.append(drv_title_box)
    drv_desc = Gtk.Label(
        label=_driver_summary(None),
        xalign=0,
        css_classes=["dim-label"],
    )
    drv_desc.set_wrap(True)
    drv_desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    drv_desc.set_max_width_chars(56)
    drv_info.append(drv_desc)
    row_drv.append(drv_info)
    row_drv.append(Gtk.Box(hexpand=True))
    drivers = app.player.get_drivers()
    # Bit-Perfect mode hides the non-exclusive drivers (PipeWire shared sink
    # and Auto (Default) which routes through it). The legacy exclusive_lock
    # setting is treated as an alias here so users upgrading from older
    # builds still see the filter applied.
    if (app.settings.get("bit_perfect", False)
            or app.settings.get("exclusive_lock", False)):
        drivers = [
            drv
            for drv in drivers
            if drv in ("ALSA（auto）", "ALSA（mmap）", "USB Rawlink v2")
        ]
    app.driver_dd = Gtk.DropDown(model=Gtk.StringList.new(drivers))
    _show_ascii_parentheses(app.driver_dd)
    app.driver_dd.connect("notify::selected-item", app.on_driver_changed)

    def _sync_driver_desc(dd, _pspec=None):
        item = dd.get_selected_item()
        drv_desc.set_text(_driver_summary(item.get_string() if item is not None else None))

    app.driver_dd.connect("notify::selected-item", _sync_driver_desc)
    _sync_driver_desc(app.driver_dd)
    row_drv.append(app.driver_dd)
    group_out.append(row_drv)

    row_depth = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    depth_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    depth_info.append(Gtk.Label(label="Output Bit Depth", xalign=0, css_classes=["settings-label"]))
    depth_info.append(
        Gtk.Label(
            label="ALSA (auto) / ALSA (mmap) only. Not applicable for USB Rawlink v2 (bit depth is fixed by the device).",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_depth.append(depth_info)
    row_depth.append(Gtk.Box(hexpand=True))
    app.bit_depth_dd = Gtk.DropDown(model=Gtk.StringList.new(["Auto"]))
    app.bit_depth_dd.set_valign(Gtk.Align.CENTER)
    app.bit_depth_dd.set_sensitive(False)
    app.bit_depth_dd.connect("notify::selected-item", app.on_output_bit_depth_changed)
    row_depth.append(app.bit_depth_dd)
    group_out.append(row_depth)
    _row_follows(row_depth, app.bit_depth_dd)

    saved_driver_init = app.settings.get("driver", "")
    app.mmap_realtime_priority_dd.set_sensitive(saved_driver_init == "ALSA（mmap）")
    group_out.append(row_rt)
    _row_follows(row_rt, app.mmap_realtime_priority_dd)

    # ── USB Rawlink: Clock Alignment ────────────────────────────────────────
    from actions.audio_settings_actions import USB_CLOCK_OPTIONS, USB_CLOCK_DEFAULT
    row_usb_clk = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    usb_clk_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    usb_clk_info.append(Gtk.Label(label="USB Clock Alignment", xalign=0, css_classes=["settings-label"]))
    usb_clk_info.append(
        Gtk.Label(
            label="Push: clock driven by write position. Pull: clock driven by playback position. USB Rawlink v2 only.",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_usb_clk.append(usb_clk_info)
    row_usb_clk.append(Gtk.Box(hexpand=True))
    app.usb_clock_mode_dd = Gtk.DropDown(model=Gtk.StringList.new(USB_CLOCK_OPTIONS))
    app.usb_clock_mode_dd.set_valign(Gtk.Align.CENTER)
    saved_usb_clk = app.settings.get("usb_clock_mode", USB_CLOCK_DEFAULT)
    if saved_usb_clk not in USB_CLOCK_OPTIONS:
        saved_usb_clk = USB_CLOCK_DEFAULT
    app.usb_clock_mode_dd.set_selected(USB_CLOCK_OPTIONS.index(saved_usb_clk))
    app.usb_clock_mode_dd.set_sensitive(saved_driver_init == "USB Rawlink v2")
    app.usb_clock_mode_dd.connect("notify::selected-item", app.on_usb_clock_mode_changed)
    row_usb_clk.append(app.usb_clock_mode_dd)
    group_out.append(row_usb_clk)
    _row_follows(row_usb_clk, app.usb_clock_mode_dd)

    row_dev = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_dev.append(Gtk.Label(label="Output Device", hexpand=True, xalign=0))
    app.device_dd = Gtk.DropDown(model=Gtk.StringList.new(["Default"]))
    app.device_dd.set_sensitive(False)
    app.device_dd.connect("notify::selected-item", app.on_device_changed)
    from actions.audio_settings_actions import setup_device_dropdown_refresh_gesture
    setup_device_dropdown_refresh_gesture(app)
    row_dev.append(app.device_dd)
    group_out.append(row_dev)

    row_state = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_state.append(Gtk.Label(label="Output Status", xalign=0, valign=Gtk.Align.START))
    status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True, halign=Gtk.Align.FILL)
    app.output_status_label = Gtk.Label(label="Idle", xalign=0, hexpand=True, css_classes=["dim-label"])
    app.output_status_label.set_wrap(True)
    app.output_status_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    app.output_status_label.set_max_width_chars(72)
    status_box.append(app.output_status_label)
    app.usb_fix_perm_btn = Gtk.Button(label="Fix USB Permissions", css_classes=["flat"], valign=Gtk.Align.START)
    app.usb_fix_perm_btn.connect("clicked", app.on_usb_fix_permissions_clicked)
    app.usb_fix_perm_btn.set_visible(False)
    status_box.append(app.usb_fix_perm_btn)
    row_state.append(status_box)
    app.output_recover_btn = Gtk.Button(label="Recover", css_classes=["flat"], valign=Gtk.Align.START)
    app.output_recover_btn.connect("clicked", app.on_recover_output_clicked)
    app.output_recover_btn.set_sensitive(False)
    # Fork: offered once the output has failed or fallen back (update_output_status_ui), not
    # as a greyed-out button beside "Active".
    _row_follows(app.output_recover_btn, app.output_recover_btn)
    row_state.append(app.output_recover_btn)
    group_out.append(row_state)

    row_rebind = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    rebind_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    rebind_info.append(Gtk.Label(label="Auto Rebind Once", xalign=0, css_classes=["settings-label"]))
    rebind_info.append(
        Gtk.Label(
            label="When a disconnected device returns, auto switch back one time",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_rebind.append(rebind_info)
    row_rebind.append(Gtk.Box(hexpand=True))
    app.auto_rebind_once_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.auto_rebind_once_switch.set_active(bool(app.settings.get("output_auto_rebind_once", False)))
    app.auto_rebind_once_switch.connect("state-set", app.on_auto_rebind_once_toggled)
    row_rebind.append(app.auto_rebind_once_switch)
    group_out.append(row_rebind)

    settings_vbox.append(group_out)

    settings_vbox.append(Gtk.Label(label="Remote Control", xalign=0, css_classes=["section-title"], margin_top=10))
    group_remote = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-group"])

    row_remote_enable = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    remote_enable_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    remote_enable_info.append(Gtk.Label(label="Enable Remote Control", xalign=0, css_classes=["settings-label"]))
    remote_enable_info.append(
        Gtk.Label(
            label="Expose playback and queue control over HTTP JSON-RPC",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_remote_enable.append(remote_enable_info)
    row_remote_enable.append(Gtk.Box(hexpand=True))
    app.remote_api_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.remote_api_switch.connect("state-set", app.on_remote_api_enabled_toggled)
    row_remote_enable.append(app.remote_api_switch)
    group_remote.append(row_remote_enable)
    # Fork: the access mode, endpoints and key matter only while remote control is on; they
    # were six rows of noise (an empty key box among them) with it off.
    remote_details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    group_remote.append(remote_details)
    app.remote_api_switch.bind_property("active", remote_details, "visible", GObject.BindingFlags.SYNC_CREATE)

    row_remote_mode = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    mode_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    mode_info.append(Gtk.Label(label="Access Mode", xalign=0, css_classes=["settings-label"]))
    mode_info.append(
        Gtk.Label(
            label="Local only is for same-machine clients. LAN is for another device on your network.",
            xalign=0,
            css_classes=["dim-label"],
            wrap=True,
        )
    )
    row_remote_mode.append(mode_info)
    row_remote_mode.append(Gtk.Box(hexpand=True))
    app.remote_api_access_dd = Gtk.DropDown(model=Gtk.StringList.new(REMOTE_ACCESS_MODES))
    app.remote_api_access_dd.connect("notify::selected-item", app.on_remote_api_access_mode_changed)
    row_remote_mode.append(app.remote_api_access_dd)
    remote_details.append(row_remote_mode)

    row_remote_network = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    app.remote_api_network_row = row_remote_network
    network_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    network_info.append(Gtk.Label(label="Network Binding", xalign=0, css_classes=["settings-label"]))
    network_info.append(
        Gtk.Label(
            label="Configure the bind address and port. Apply is required before changes take effect.",
            xalign=0,
            css_classes=["dim-label"],
            wrap=True,
        )
    )
    row_remote_network.append(network_info)
    network_controls = Gtk.Box(spacing=8, hexpand=True, halign=Gtk.Align.END)
    app.remote_api_bind_entry = Gtk.Entry(placeholder_text="0.0.0.0")
    app.remote_api_bind_entry.set_width_chars(13)
    network_controls.append(app.remote_api_bind_entry)
    app.remote_api_port_spin = Gtk.SpinButton.new_with_range(1, 65535, 1)
    app.remote_api_port_spin.set_numeric(True)
    app.remote_api_port_spin.set_width_chars(6)
    network_controls.append(app.remote_api_port_spin)
    app.remote_api_apply_btn = Gtk.Button(label="Apply", css_classes=["flat"])
    app.remote_api_apply_btn.connect("clicked", app.on_remote_api_apply_network_settings)
    network_controls.append(app.remote_api_apply_btn)
    row_remote_network.append(network_controls)
    remote_details.append(row_remote_network)

    row_remote_allow = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    app.remote_api_allowlist_row = row_remote_allow
    allow_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    allow_info.append(Gtk.Label(label="Allowed Clients", xalign=0, css_classes=["settings-label"]))
    allow_info.append(
        Gtk.Label(
            label="Optional CIDRs, e.g. 192.168.1.0/24 or 192.168.1.50/32",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_remote_allow.append(allow_info)
    row_remote_allow.append(Gtk.Box(hexpand=True))
    app.remote_api_allowlist_entry = Gtk.Entry(placeholder_text="192.168.1.0/24, 192.168.1.50/32")
    app.remote_api_allowlist_entry.set_width_chars(16)
    row_remote_allow.append(app.remote_api_allowlist_entry)
    remote_details.append(row_remote_allow)

    row_remote_endpoint = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_remote_endpoint.append(Gtk.Label(label="MCP Endpoint", xalign=0, css_classes=["settings-label"]))
    row_remote_endpoint.append(Gtk.Box(hexpand=True))
    endpoint_controls = Gtk.Box(spacing=8, halign=Gtk.Align.END)
    app.remote_api_endpoint_label = Gtk.Label(label="", xalign=1, css_classes=["dim-label"])
    app.remote_api_endpoint_label.set_selectable(True)
    endpoint_controls.append(app.remote_api_endpoint_label)
    app.remote_api_endpoint_copy_btn = Gtk.Button(label="Copy", css_classes=["flat"])
    app.remote_api_endpoint_copy_btn.connect("clicked", app.on_remote_api_copy_endpoint_clicked)
    endpoint_controls.append(app.remote_api_endpoint_copy_btn)
    row_remote_endpoint.append(endpoint_controls)
    remote_details.append(row_remote_endpoint)

    row_remote_rpc_endpoint = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_remote_rpc_endpoint.append(Gtk.Label(label="RPC Endpoint", xalign=0, css_classes=["settings-label"]))
    row_remote_rpc_endpoint.append(Gtk.Box(hexpand=True))
    rpc_endpoint_controls = Gtk.Box(spacing=8, halign=Gtk.Align.END)
    app.remote_api_rpc_endpoint_label = Gtk.Label(label="", xalign=1, css_classes=["dim-label"])
    app.remote_api_rpc_endpoint_label.set_selectable(True)
    rpc_endpoint_controls.append(app.remote_api_rpc_endpoint_label)
    app.remote_api_rpc_endpoint_copy_btn = Gtk.Button(label="Copy", css_classes=["flat"])
    app.remote_api_rpc_endpoint_copy_btn.connect("clicked", app.on_remote_api_copy_rpc_endpoint_clicked)
    rpc_endpoint_controls.append(app.remote_api_rpc_endpoint_copy_btn)
    row_remote_rpc_endpoint.append(rpc_endpoint_controls)
    remote_details.append(row_remote_rpc_endpoint)

    row_remote_status = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_remote_status.append(Gtk.Label(label="Status", xalign=0, css_classes=["settings-label"]))
    row_remote_status.append(Gtk.Box(hexpand=True))
    app.remote_api_status_label = Gtk.Label(label="Stopped", xalign=1, css_classes=["dim-label"])
    app.remote_api_status_label.set_selectable(True)
    row_remote_status.append(app.remote_api_status_label)
    remote_details.append(row_remote_status)

    row_remote_key = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    key_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    key_info.append(Gtk.Label(label="API Key", xalign=0, css_classes=["settings-label"]))
    key_info.append(
        Gtk.Label(
            label="Use this bearer token from OpenClaw or the MCP bridge.",
            xalign=0,
            css_classes=["dim-label"],
        )
    )
    row_remote_key.append(key_info)
    key_controls = Gtk.Box(spacing=8, hexpand=True, halign=Gtk.Align.END)
    app.remote_api_key_entry = Gtk.Entry(editable=False, hexpand=True, valign=Gtk.Align.CENTER,
                                         placeholder_text="No key yet")
    app.remote_api_key_entry.set_width_chars(14)
    key_controls.append(app.remote_api_key_entry)
    app.remote_api_copy_btn = Gtk.Button(label="Copy", css_classes=["flat"])
    app.remote_api_copy_btn.connect("clicked", app.on_remote_api_copy_key_clicked)
    key_controls.append(app.remote_api_copy_btn)
    app.remote_api_generate_btn = Gtk.Button(label="Generate Key", css_classes=["flat"])
    app.remote_api_generate_btn.connect("clicked", app.on_remote_api_generate_key_clicked)
    key_controls.append(app.remote_api_generate_btn)
    row_remote_key.append(key_controls)
    remote_details.append(row_remote_key)

    settings_vbox.append(group_remote)

    # ---- Scrobbling section ----
    settings_vbox.append(Gtk.Label(label="Scrobbling", xalign=0, css_classes=["section-title"], margin_top=10))
    group_scrobble = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-group"])

    # Last.fm enable
    row_lfm_enable = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    lfm_enable_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    lfm_enable_info.append(Gtk.Label(label="Last.fm", xalign=0, css_classes=["settings-label"]))
    lfm_enable_info.append(
        Gtk.Label(label="Scrobble played tracks to your Last.fm profile", xalign=0, css_classes=["dim-label"])
    )
    row_lfm_enable.append(lfm_enable_info)
    row_lfm_enable.append(Gtk.Box(hexpand=True))
    app.scrobble_lastfm_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.scrobble_lastfm_switch.connect("state-set", app.on_lastfm_enabled_toggled)
    row_lfm_enable.append(app.scrobble_lastfm_switch)
    group_scrobble.append(row_lfm_enable)

    # Last.fm Connect row
    row_lfm_connect = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=4, margin_bottom=8)
    app.scrobble_lastfm_status_label = Gtk.Label(label="Not connected", xalign=0, css_classes=["dim-label"], hexpand=True)
    row_lfm_connect.append(app.scrobble_lastfm_status_label)
    app.scrobble_lastfm_disconnect_btn = Gtk.Button(label="Disconnect", css_classes=["flat", "destructive-action"])
    app.scrobble_lastfm_disconnect_btn.set_sensitive(False)
    app.scrobble_lastfm_disconnect_btn.set_visible(False)
    app.scrobble_lastfm_disconnect_btn.connect("clicked", app.on_lastfm_disconnect_clicked)
    row_lfm_connect.append(app.scrobble_lastfm_disconnect_btn)
    app.scrobble_lastfm_connect_btn = Gtk.Button(label="Connect", css_classes=["flat", "suggested-action"])
    app.scrobble_lastfm_connect_btn.connect("clicked", app.on_lastfm_connect_clicked)
    row_lfm_connect.append(app.scrobble_lastfm_connect_btn)
    group_scrobble.append(row_lfm_connect)

    sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL, margin_start=12, margin_end=12)
    group_scrobble.append(sep)

    # ListenBrainz enable
    row_lb_enable = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    lb_enable_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    lb_enable_info.append(Gtk.Label(label="ListenBrainz", xalign=0, css_classes=["settings-label"]))
    lb_enable_info.append(
        Gtk.Label(label="Submit listens to your ListenBrainz account", xalign=0, css_classes=["dim-label"])
    )
    row_lb_enable.append(lb_enable_info)
    row_lb_enable.append(Gtk.Box(hexpand=True))
    app.scrobble_lb_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
    app.scrobble_lb_switch.connect("state-set", app.on_listenbrainz_enabled_toggled)
    row_lb_enable.append(app.scrobble_lb_switch)
    group_scrobble.append(row_lb_enable)

    # ListenBrainz token
    row_lb_token = Gtk.Box(spacing=12, margin_start=12, margin_end=12, margin_top=4, margin_bottom=8)
    row_lb_token.append(Gtk.Label(label="User Token", xalign=0, css_classes=["dim-label"], width_chars=12))
    app.scrobble_lb_token_entry = Gtk.Entry(hexpand=True, visibility=False, input_purpose=Gtk.InputPurpose.PASSWORD,
                                             placeholder_text="From listenbrainz.org/profile/")
    row_lb_token.append(app.scrobble_lb_token_entry)
    app.scrobble_lb_status_label = Gtk.Label(label="", css_classes=["dim-label"])
    row_lb_token.append(app.scrobble_lb_status_label)
    lb_save_btn = Gtk.Button(label="Save", css_classes=["flat"])
    lb_save_btn.connect("clicked", app.on_listenbrainz_token_saved)
    row_lb_token.append(lb_save_btn)
    group_scrobble.append(row_lb_token)

    settings_vbox.append(group_scrobble)

    # Sync scrobble UI to current settings
    if hasattr(app, "_init_scrobble_settings_ui"):
        app._init_scrobble_settings_ui()

    settings_vbox.append(Gtk.Label(label="Diagnostics", xalign=0, css_classes=["section-title"], margin_top=10))
    group_diag = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["settings-group"])
    row_diag = Gtk.Box(spacing=10, margin_start=12, margin_end=12, margin_top=8, margin_bottom=8)
    row_diag.append(Gtk.Label(label="Runtime Health", xalign=0, hexpand=True))
    app.network_status_label = Gtk.Label(label="NET IDLE", xalign=1, css_classes=["diag-chip", "status-idle"])
    app.decoder_status_label = Gtk.Label(label="DEC IDLE", xalign=1, css_classes=["diag-chip", "status-idle"])
    app.events_btn = Gtk.Button(label="Events", css_classes=["flat"])
    row_diag.append(app.network_status_label)
    row_diag.append(app.decoder_status_label)
    row_diag.append(app.events_btn)
    group_diag.append(row_diag)
    settings_vbox.append(group_diag)

    app._diag_pop = Gtk.Popover()
    app._diag_pop.set_parent(app.events_btn)
    pop_box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=8,
        margin_top=10,
        margin_bottom=10,
        margin_start=10,
        margin_end=10,
    )
    pop_box.append(Gtk.Label(label="Recent Events", xalign=0, css_classes=["settings-label"]))
    sw = Gtk.ScrolledWindow(min_content_height=180, min_content_width=540)
    app._diag_text = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
    sw.set_child(app._diag_text)
    pop_box.append(sw)
    app._diag_pop.set_child(pop_box)
    app.events_btn.connect("clicked", app.show_diag_events)
    if hasattr(app, "_refresh_remote_api_settings_ui"):
        app._refresh_remote_api_settings_ui()
    _wrap_settings_descriptions(settings_vbox)
    app.right_stack.add_named(settings_scroll, "settings")


def _toggle_search_tracks(app):
    from actions import ui_actions

    app.search_tracks_expanded = not bool(getattr(app, "search_tracks_expanded", False))
    ui_actions.render_search_tracks_page(app)


def _show_ascii_parentheses(dropdown):
    """Fork: show "ALSA (auto)" while the model keeps upstream's ids ("ALSA（auto）"), which
    settings and driver checks compare against."""
    factory = Gtk.SignalListItemFactory()
    factory.connect("setup", lambda _f, item: item.set_child(Gtk.Label(xalign=0)))
    factory.connect(
        "bind",
        lambda _f, item: item.get_child().set_label(
            item.get_item().get_string().replace("（", " (").replace("）", ")")
        ),
    )
    dropdown.set_factory(factory)


def _wrap_settings_descriptions(root):
    """Fork: descriptions wrap instead of setting the settings page's minimum width.

    Only plain one-line labels (no ellipsizing, not already wrapping) that sit beside
    controls in a settings row; headings and status lines are left alone. Dropdowns
    centre vertically instead of stretching to a tall row's height.
    """
    todo = [root]
    while todo:
        widget = todo.pop()
        child = widget.get_first_child()
        while child is not None:
            todo.append(child)
            child = child.get_next_sibling()
        if (
            isinstance(widget, Gtk.Label)
            and widget.has_css_class("dim-label")
            and not widget.get_wrap()
            and widget.get_ellipsize() == Pango.EllipsizeMode.NONE
        ):
            widget.set_wrap(True)
            widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        elif isinstance(widget, Gtk.DropDown) and widget.get_valign() == Gtk.Align.FILL:
            widget.set_valign(Gtk.Align.CENTER)


def build_search_view(app):
    app.search_scroll = Gtk.ScrolledWindow(vexpand=True)
    vbox = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=24,
        margin_top=32,
        margin_bottom=32,
        margin_start=PAGE_INSET,
        margin_end=PAGE_INSET,
        css_classes=["home-view", "search-view"],
    )
    # Fork: no centring clamp; the results start on the same edge as every other page.
    app.search_scroll.set_child(vbox)
    app.search_content_box = vbox
    app.search_base_margin_bottom = 32

    app.search_status_label = Gtk.Label(xalign=0, css_classes=["dim-label", "search-status-label"])
    app.search_status_label.set_visible(False)
    vbox.append(app.search_status_label)

    # Fork #27: each result kind is a shelf (one row, "Show all" for the rest of up to 50), as on
    # Home and artist pages. They were sideways-scrolling rows of the first 6.
    def _result_shelf(title, activate=True):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["home-section"])
        head, more = shelf.heading(title)
        box.append(head)
        flow = shelf.Shelf(button=more)
        flow.set_column_spacing(24)
        flow.set_row_spacing(24)
        if activate:
            flow.connect("child-activated", app.on_grid_item_activated)
        box.append(flow)
        box.set_visible(False)
        vbox.append(box)
        return box, flow

    app.res_art_box, app.res_art_flow = _result_shelf("Artists")
    app.res_alb_box, app.res_alb_flow = _result_shelf("Albums")
    # TIDAL's playlists (fork: the search request dropped them), then your own that match.
    app.res_tpl_box, app.res_tpl_flow = _result_shelf("Playlists", activate=False)
    app.res_pl_box, app.res_pl_flow = _result_shelf("Your Playlists", activate=False)

    app.res_trk_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["home-section"])
    trk_head = Gtk.Box(spacing=8)
    trk_head.append(Gtk.Label(label="Tracks", xalign=0, hexpand=True, css_classes=["home-section-title"]))
    # Fork: selecting is a mode, as on album and playlist pages (Escape or the toggle ends it):
    # the checkboxes and their two actions were on every search, greyed out until used.
    app.like_selected_tracks_btn = Gtk.Button(label="Like Selected", css_classes=["flat", "pill"], visible=False)
    app.like_selected_tracks_btn.set_sensitive(False)
    app.like_selected_tracks_btn.connect("clicked", app.on_like_selected_search_tracks)
    trk_head.append(app.like_selected_tracks_btn)
    app.add_selected_tracks_btn = Gtk.Button(label="Add Selected", css_classes=["flat", "pill"], visible=False)
    app.add_selected_tracks_btn.set_sensitive(False)
    app.add_selected_tracks_btn.connect("clicked", app.on_add_selected_search_tracks)
    trk_head.append(app.add_selected_tracks_btn)
    app.search_select_btn = Gtk.ToggleButton(
        icon_name="selection-mode-symbolic", css_classes=["flat", "circular"], valign=Gtk.Align.CENTER,
        tooltip_text="Select Tracks",
    )
    app.search_select_btn.connect("toggled", app.on_search_select_mode_toggled)
    trk_head.append(app.search_select_btn)
    # Fork #27: the first 10 tracks, then all of them (up to 50) on "Show all".
    app.search_tracks_more_btn = Gtk.Button(
        label="Show all", css_classes=["flat", "home-section-more"], valign=Gtk.Align.CENTER, visible=False,
    )
    app.search_tracks_more_btn.connect("clicked", lambda _b: _toggle_search_tracks(app))
    trk_head.append(app.search_tracks_more_btn)
    # Fork: the pager reads "‹ 2 / 5 ›" as on Liked Songs (ui/pager.py); it said "Page 2/5 ‹ ›".
    app.search_prev_page_btn = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
    app.search_prev_page_btn.set_tooltip_text("Previous page")
    app.search_prev_page_btn.set_sensitive(False)
    app.search_prev_page_btn.connect("clicked", app.on_search_tracks_prev_page)
    trk_head.append(app.search_prev_page_btn)
    app.search_tracks_page_label = Gtk.Label(label="1 / 1", css_classes=["dim-label", "ebb-pager-label"], valign=Gtk.Align.CENTER)
    trk_head.append(app.search_tracks_page_label)
    app.search_next_page_btn = Gtk.Button(icon_name="go-next-symbolic", css_classes=["flat", "circular"], valign=Gtk.Align.CENTER)
    app.search_next_page_btn.set_tooltip_text("Next page")
    app.search_next_page_btn.set_sensitive(False)
    app.search_next_page_btn.connect("clicked", app.on_search_tracks_next_page)
    trk_head.append(app.search_next_page_btn)
    app.res_trk_box.append(trk_head)
    app.res_trk_list = Gtk.ListBox(css_classes=["boxed-list", "tracks-list", "search-tracks-list"])
    app.res_trk_list.connect("row-activated", app.on_search_track_selected)
    app.res_trk_box.append(app.res_trk_list)
    app.res_trk_box.set_visible(False)
    vbox.append(app.res_trk_box)

    # Fork: tracks come right after artists.
    vbox.reorder_child_after(app.res_trk_box, app.res_art_box)
    app.right_stack.add_named(app.search_scroll, "search_view")
