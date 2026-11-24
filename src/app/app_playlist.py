"""
Playlist management for TidalApp.
Contains playlist creation, editing and management methods.
"""
import logging
from gi.repository import Adw, Gtk, GLib
from core.executor import submit_daemon
import copy
from ui.track_table import clear_track_rows, set_track_rows_hidden  # fork
from ui import track_table  # fork: header meta helpers
from ui import dialogs  # fork: the small dialogs, one look

logger = logging.getLogger(__name__)


def on_playlist_sort_clicked(self, field):
    if self.playlist_sort_field == field:
        self.playlist_sort_asc = not self.playlist_sort_asc
    else:
        self.playlist_sort_field = field
        self.playlist_sort_asc = True
    if self.current_playlist_id:
        self.render_playlist_detail(self.current_playlist_id)


def on_playlists_home_sort_changed(self, sort_key):
    """Handle sort selection change on the playlists home page."""
    if self.playlists_home_sort == sort_key:
        self.playlists_home_sort_asc = not self.playlists_home_sort_asc
    else:
        self.playlists_home_sort = sort_key
        self.playlists_home_sort_asc = True
    self.render_playlists_home()


def on_playlist_folder_card_clicked(self, folder_obj):
    if folder_obj is None:
        return
    fid = str(getattr(folder_obj, "id", "") or "")
    if not fid:
        return
    self.current_playlist_folder = folder_obj
    stack = list(getattr(self, "current_playlist_folder_stack", []) or [])
    if stack and str(stack[-1].get("id", "")) == fid:
        pass
    else:
        stack.append({"id": fid, "name": str(getattr(folder_obj, "name", "") or "Folder"), "obj": folder_obj})
    self.current_playlist_folder_stack = stack
    if getattr(self, "back_btn", None) is not None:
        self.back_btn.set_sensitive(True)
    self.render_playlists_home()


def on_playlist_folder_up_clicked(self, _btn=None):
    stack = list(getattr(self, "current_playlist_folder_stack", []) or [])
    if not stack:
        self.current_playlist_folder = None
        self.render_playlists_home()
        return
    stack.pop()
    self.current_playlist_folder_stack = stack
    if stack:
        self.current_playlist_folder = stack[-1].get("obj")
    else:
        self.current_playlist_folder = None
    self.render_playlists_home()


def on_create_playlist_folder_clicked(self, _btn=None):
    if not getattr(self.backend, "user", None):
        self._show_simple_dialog("Login Required", "Please login first.")
        return

    def _submit(name):
        folder_name = str(name or "").strip() or "New Folder"
        parent_id = "root"
        if getattr(self, "current_playlist_folder", None) is not None:
            parent_id = str(getattr(self.current_playlist_folder, "id", "root") or "root")
        self.show_output_notice("Creating folder...", "ok", 1500)

        def task():
            f = self.backend.create_cloud_folder(folder_name, parent_folder_id=parent_id)

            def apply():
                if f is None:
                    self.show_output_notice("Failed to create folder.", "warn", 2600)
                else:
                    self.show_output_notice("Folder created.", "ok", 2200)
                    self.render_playlists_home()
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    self._prompt_playlist_name(
        "New Folder",
        "New Folder",
        _submit,
        subtitle="Create a folder to organize your cloud playlists.",
        placeholder="Folder name",
        save_label="Create",
        dialog_size=(480, 220),
    )


def on_playlist_folder_rename_clicked(self, folder_obj=None):
    folder_obj = folder_obj or getattr(self, "current_playlist_folder", None)
    if folder_obj is None:
        return
    old_name = str(getattr(folder_obj, "name", "") or "Folder")

    def _submit(name):
        new_name = str(name or "").strip()
        if not new_name or new_name == old_name:
            return
        self.show_output_notice("Renaming folder...", "ok", 1500)

        def task():
            res = self.backend.rename_cloud_folder(folder_obj, new_name)

            def apply():
                if bool(res.get("ok")):
                    self.show_output_notice("Folder renamed.", "ok", 2200)
                    stack = list(getattr(self, "current_playlist_folder_stack", []) or [])
                    for item in stack:
                        if str(item.get("id", "")) == str(getattr(folder_obj, "id", "") or ""):
                            item["name"] = new_name
                    self.current_playlist_folder_stack = stack
                    self.render_playlists_home()
                else:
                    self.show_output_notice("Failed to rename folder.", "warn", 2600)
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    self._prompt_playlist_name(
        "Rename Folder",
        old_name,
        _submit,
        subtitle="Update folder name for your cloud playlists.",
        placeholder="Folder name",
        save_label="Rename",
        dialog_size=(480, 220),
    )


def on_playlist_folder_delete_clicked(self, folder_obj=None):
    folder_obj = folder_obj or getattr(self, "current_playlist_folder", None)
    if folder_obj is None:
        return
    fname = str(getattr(folder_obj, "name", "") or "this folder")
    def _delete():
        self.show_output_notice("Deleting folder...", "ok", 1600)

        def task():
            res = self.backend.delete_cloud_folder(folder_obj)

            def apply():
                if bool(res.get("ok")):
                    self.show_output_notice("Folder deleted.", "ok", 2200)
                    fid = str(getattr(folder_obj, "id", "") or "")
                    stack = [x for x in list(getattr(self, "current_playlist_folder_stack", []) or []) if str(x.get("id", "")) != fid]
                    self.current_playlist_folder_stack = stack
                    self.current_playlist_folder = stack[-1].get("obj") if stack else None
                    self.render_playlists_home()
                else:
                    self.show_output_notice("Failed to delete folder.", "warn", 2800)
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    dialogs.confirm(
        self, "Delete Folder?", f"“{fname}” will be deleted permanently.", "Delete", _delete, destructive=True
    )


def on_playlist_card_clicked(self, playlist_id):
    from actions import ui_actions

    ui_actions.open_grid_page(self)  # fork: a local playlist renders into the grid too
    # Fork: show the grid page. A local playlist opens from search results (its only way in),
    # and it rendered behind them, so the click seemed to do nothing. Back returns to them.
    current_view = self.right_stack.get_visible_child_name()
    if current_view and current_view != "grid_view":
        self.nav_history.append(current_view)
        self.right_stack.set_visible_child_name("grid_view")
        if hasattr(self, "_remember_last_view"):
            self._remember_last_view("grid_view")
    self.current_remote_playlist = None
    if self.remote_playlist_edit_btn is not None:
        self.remote_playlist_edit_btn.set_visible(False)
    if self.remote_playlist_visibility_btn is not None:
        self.remote_playlist_visibility_btn.set_visible(False)
    if self.remote_playlist_more_btn is not None:
        self.remote_playlist_more_btn.set_visible(False)
    self.current_playlist_id = playlist_id
    self.playlist_edit_mode = False
    self.playlist_rename_mode = False
    if hasattr(self, "grid_title_label") and self.grid_title_label is not None:
        self.grid_title_label.set_visible(False)
    if hasattr(self, "grid_subtitle_label") and self.grid_subtitle_label is not None:
        self.grid_subtitle_label.set_visible(False)
    if self.back_btn is not None:
        self.back_btn.set_sensitive(True)
    self.render_playlist_detail(playlist_id)


def playlist_byline(creator, own):
    """Who made a playlist, for the header (fork). Any missing creator name used to read "TIDAL":
    your own playlists said so (TIDAL sends no name for them; tidalapi may say "me"),
    and so did other people's. Editorial playlists have no creator at all: those are TIDAL's."""
    if own:
        return "You"
    if creator is None or not str(getattr(creator, "id", "") or "").strip("0 "):
        return "TIDAL"
    name = str(getattr(creator, "name", "") or "").strip()
    # someone else's, name unknown (tidalapi's placeholders "me" and "user"): no line at all
    return "" if name in ("", "me", "user") else name


def on_remote_playlist_card_clicked(self, playlist_obj):
    if playlist_obj is None:
        return
    self.current_remote_playlist = playlist_obj
    self.current_album = None
    self.current_playlist_id = None
    self.playlist_edit_mode = False
    self.playlist_rename_mode = False
    if hasattr(self, "reset_track_list_select_mode"):
        self.reset_track_list_select_mode()
    self.right_stack.set_visible_child_name("tracks")
    if hasattr(self, "_remember_last_view"):
        self._remember_last_view("tracks")
    self.back_btn.set_sensitive(True)

    title = getattr(playlist_obj, "name", "TIDAL Playlist")
    section = ""
    gtl = getattr(self, "grid_title_label", None)
    if gtl is not None:
        section = str(gtl.get_text() or "").strip()
    if section and section.lower() not in ("", "albums", "playlists"):
        self._track_view_source = {"type": section, "name": title, "obj": playlist_obj, "open_method": "on_remote_playlist_card_clicked"}
    else:
        self._track_view_source = {"type": "playlist", "name": title, "obj": playlist_obj, "open_method": "on_remote_playlist_card_clicked"}
    creator = getattr(playlist_obj, "creator", None)
    user_id = str(getattr(getattr(self.backend, "user", None), "id", "") or "").strip()
    creator_id = str(getattr(creator, "id", "") or "").strip()
    self._remote_playlist_is_own = bool(user_id and creator_id and user_id == creator_id)
    creator_name = playlist_byline(creator, self._remote_playlist_is_own)
    self.header_kicker.set_text("Playlist")
    self.header_title.set_text(title)
    self.header_title.set_tooltip_text(title)
    self.header_artist.set_text(creator_name)
    self.header_artist.set_tooltip_text(creator_name)
    self.header_artist.set_visible(bool(creator_name))
    self.header_artist.add_css_class("album-artist-plain")  # not a link: the album page's artist is
    self.header_meta.set_text("")
    if getattr(self, "track_list_placeholder_label", None) is not None:  # fork: empty-list state
        self.track_list_placeholder_label.set_text("Loading tracks…")
        self.track_list_placeholder_retry.set_visible(False)
    if hasattr(self, "similar_albums_box"):
        self.similar_albums_box.set_visible(False)
    if self.fav_btn is not None:
        # Fork #24: the heart shows on someone else's playlist (your own are yours already).
        # It was hidden because on_fav_clicked could only toggle albums and mixes.
        can_fav = not self._remote_playlist_is_own and callable(getattr(self.backend, "is_playlist_favorite", None))
        self.fav_btn.set_visible(can_fav)
        if can_fav:
            self._update_fav_icon(self.fav_btn, self.backend.is_playlist_favorite(getattr(playlist_obj, "id", "")))
    if self.add_playlist_btn is not None:
        self.add_playlist_btn.set_visible(False)
    if self.remote_playlist_edit_btn is not None:
        self.remote_playlist_edit_btn.set_visible(False)
    if self.remote_playlist_visibility_btn is not None:
        self.remote_playlist_visibility_btn.set_visible(False)
    if self.remote_playlist_more_btn is not None:
        self.remote_playlist_more_btn.set_visible(self._remote_playlist_is_own)
    self._refresh_remote_playlist_visibility_button(playlist_obj)
    # Ensure play/shuffle buttons exist and are visible
    from actions.ui_actions import _ensure_play_shuffle_btns, _load_album_header_bg
    _ensure_play_shuffle_btns(self)
    import utils.helpers as utils
    utils.load_img(self.header_art, lambda: self.backend.get_artwork_url(playlist_obj, 640), self.cache_dir, utils.COVER_SIZE)
    if hasattr(self, "album_header_bg") and self.album_header_bg is not None:
        _load_album_header_bg(self, lambda: self.backend.get_artwork_url(playlist_obj, 640))

    clear_track_rows(self.track_list)  # fork: keeps the empty-list placeholder

    # Clean up previous lazy-load hook (if any).
    try:
        old_vadj = getattr(self, "_remote_pl_vadj", None)
        old_handler = int(getattr(self, "_remote_pl_vadj_handler_id", 0) or 0)
        if old_vadj is not None and old_handler:
            old_vadj.disconnect(old_handler)
    except Exception:
        pass
    self._remote_pl_vadj = None
    self._remote_pl_vadj_handler_id = 0

    render_token = int(getattr(self, "_remote_pl_render_token", 0) or 0) + 1
    self._remote_pl_render_token = render_token

    state = {
        "tracks": [],
        "offset": 0,
        "loading": False,
        "has_more": True,
    }
    initial_limit = 20
    page_limit = 40

    def _get_total_tracks():
        for k in ("number_of_tracks", "num_tracks", "numberOfTracks", "total_number_of_items"):
            try:
                v = int(getattr(playlist_obj, k, 0) or 0)
            except Exception:
                v = 0
            if v > 0:
                return v
        return 0

    def _apply_loaded_tracks():
        total = _get_total_tracks()
        loaded = len(state["tracks"])
        # Fork: the playlist's size, not "20/30" (that only meant "20 loaded so far";
        # the rest loads on scroll or when played).
        count = total if total > 0 else loaded
        # Fork: and the running time. Summing the tracks only counts when all of them are in.
        seconds = track_table.total_seconds(playlist_obj, state["tracks"] if loaded >= count else None)
        self.header_meta.set_text(track_table.meta_line(track_table.count_text(count),
                                                        track_table.runtime_text(seconds)))
        self.load_album_tracks(list(state["tracks"]))

    # Fork: a confirmed removal updates this page in place (_after_playlist_removal) instead of
    # reloading it from the top.
    def _drop_track(track_id):
        if int(getattr(self, "_remote_pl_render_token", 0) or 0) != render_token:
            return
        if state["loading"]:
            # A page is in flight with pre-removal offsets: reload rather than guess.
            self.on_remote_playlist_card_clicked(playlist_obj)
            return
        kept = [tr for tr in state["tracks"] if getattr(tr, "id", None) != track_id]
        state["offset"] = max(0, int(state["offset"]) - (len(state["tracks"]) - len(kept)))
        state["tracks"] = kept
        _apply_loaded_tracks()

    self._remote_pl_view = {"pl": playlist_obj, "drop": _drop_track}

    def _get_track_scroller():
        try:
            return self.track_list.get_ancestor(Gtk.ScrolledWindow)
        except Exception:
            return None

    def _maybe_load_more(_adj=None):
        if int(getattr(self, "_remote_pl_render_token", 0) or 0) != render_token:
            return
        if state["loading"] or not state["has_more"]:
            return
        scroller = _get_track_scroller()
        if scroller is None:
            return
        vadj = scroller.get_vadjustment()
        if vadj is None:
            return
        # Keep first screen fixed: only start paging after user scrolls.
        if float(vadj.get_value()) <= 1.0:
            return
        remain = float(vadj.get_upper()) - (float(vadj.get_value()) + float(vadj.get_page_size()))
        if remain <= 320:
            _load_next_page()

    def _ensure_scroll_hook():
        if self._remote_pl_vadj_handler_id:
            return
        scroller = _get_track_scroller()
        if scroller is None:
            return
        vadj = scroller.get_vadjustment()
        if vadj is None:
            return
        self._remote_pl_vadj = vadj
        self._remote_pl_vadj_handler_id = vadj.connect("value-changed", _maybe_load_more)

    def _load_next_page():
        if state["loading"] or not state["has_more"]:
            return
        state["loading"] = True
        offset = int(state["offset"])
        limit = initial_limit if offset == 0 else page_limit

        def task():
            page = list(self.backend.get_playlist_tracks_page(playlist_obj, limit=limit, offset=offset) or [])

            def apply():
                if int(getattr(self, "_remote_pl_render_token", 0) or 0) != render_token:
                    return False
                state["loading"] = False
                if not page:
                    state["has_more"] = False
                    return False
                state["tracks"].extend(page)
                state["offset"] += len(page)
                if len(page) < limit:
                    state["has_more"] = False
                _apply_loaded_tracks()
                _ensure_scroll_hook()
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    _load_next_page()


def _refresh_remote_playlist_visibility_button(self, playlist_obj=None):
    pl = playlist_obj or getattr(self, "current_remote_playlist", None)
    if pl is None:
        return
    is_public = bool(getattr(pl, "public", False))
    # Update menu item icon and label
    icon = getattr(self, "_vis_menu_icon", None)
    label = getattr(self, "_vis_menu_label", None)
    if icon is not None:
        icon.set_from_icon_name("changes-allow-symbolic" if is_public else "changes-prevent-symbolic")
    if label is not None:
        label.set_text("Make Private" if is_public else "Make Public")


def on_remote_playlist_toggle_public_clicked(self, _btn=None, playlist_obj=None):
    pl = playlist_obj or getattr(self, "current_remote_playlist", None)
    if pl is None:
        return
    target_public = not bool(getattr(pl, "public", False))
    self.show_output_notice("Updating playlist visibility...", "ok", 1800)

    def task():
        res = self.backend.update_cloud_playlist(pl, is_public=target_public)

        def apply():
            if bool(res.get("ok")):
                try:
                    pl.public = target_public
                except Exception:
                    pass
                self._refresh_remote_playlist_visibility_button(pl)
                self.show_output_notice(
                    "Playlist is now public." if target_public else "Playlist is now private.",
                    "ok",
                    2200,
                )
            else:
                self.show_output_notice("Failed to update playlist visibility.", "warn", 3200)
            return False

        GLib.idle_add(apply)

    submit_daemon(task)


_EDITOR_COVER_SIZE = 120
_EDITOR_COVER_MIN_WINDOW_W = 520  # under this the form needs the whole width


def _open_cloud_playlist_editor(
    self,
    dialog_title,
    save_label,
    initial_title,
    initial_desc="",
    initial_public=False,
    playlist_obj=None,
    folder_options=None,
    initial_folder_id="root",
    on_submit=None,
):
    # Fork: a dialog inside the window, with its title and buttons in a header bar. It was a
    # Gtk.Dialog titled only in the window's title bar, which niri does not draw.
    dialog = Adw.Dialog(title=str(dialog_title or ""), content_width=600)
    root = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=12,
        margin_top=14,
        margin_bottom=14,
        margin_start=14,
        margin_end=14,
    )
    content = Gtk.Box(spacing=16)

    import utils.helpers as utils

    try:
        roomy = int(self.win.get_width() or 0) >= _EDITOR_COVER_MIN_WINDOW_W
    except Exception:
        roomy = True
    if playlist_obj is not None and roomy:
        # Fork: only an existing playlist has a cover to show, and only where there is room
        # beside the form. A new one got an empty square, and under it a "Change image" button
        # that was never enabled.
        cover = Gtk.Image(css_classes=["album-cover-img", "playlist-cover-img"], valign=Gtk.Align.START)
        cover.set_size_request(_EDITOR_COVER_SIZE, _EDITOR_COVER_SIZE)
        utils.load_img(
            cover, lambda: self.backend.get_artwork_url(playlist_obj, 640), self.cache_dir, _EDITOR_COVER_SIZE
        )
        content.append(cover)

    right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True)
    right.append(Gtk.Label(label="Title", xalign=0))
    title_entry = Gtk.Entry(text=str(initial_title or ""))
    right.append(title_entry)

    folder_dd = None
    folder_ids = []
    if folder_options:
        right.append(Gtk.Label(label="Folder", xalign=0))
        folder_labels = [str(item[1] or "Root") for item in folder_options]
        folder_ids = [str(item[0] or "root") for item in folder_options]
        folder_dd = Gtk.DropDown(model=Gtk.StringList.new(folder_labels))
        selected_idx = 0
        target_id = str(initial_folder_id or "root")
        for i, fid in enumerate(folder_ids):
            if fid == target_id:
                selected_idx = i
                break
        folder_dd.set_selected(selected_idx)
        right.append(folder_dd)

    right.append(Gtk.Label(label="Description", xalign=0))
    desc_view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, vexpand=True)
    desc_buf = desc_view.get_buffer()
    desc_buf.set_text(str(initial_desc or ""))
    desc_scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=120)
    desc_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    desc_scroll.set_child(desc_view)
    right.append(desc_scroll)
    count_lbl = Gtk.Label(xalign=0, css_classes=["dim-label"])
    right.append(count_lbl)

    public_row = Gtk.Box(spacing=8, margin_top=6)
    public_lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
    public_lbl_box.append(Gtk.Label(label="Make it public", xalign=0))
    # Fork: wraps. On one line it made the form 430 px wide at least, past a narrow window's edge.
    public_lbl_box.append(
        Gtk.Label(
            label="Your playlist will be visible on your profile and accessible by anyone.",
            xalign=0,
            wrap=True,
            css_classes=["dim-label"],
        )
    )
    public_switch = Gtk.Switch(active=bool(initial_public), halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
    public_row.append(public_lbl_box)
    public_row.append(public_switch)
    right.append(public_row)

    content.append(right)
    root.append(content)

    cancel_btn = Gtk.Button(label="Cancel")
    save_btn = Gtk.Button(label=save_label, css_classes=["suggested-action"])
    header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
    header.pack_start(cancel_btn)
    header.pack_end(save_btn)
    view = Adw.ToolbarView()
    view.add_top_bar(header)
    view.set_content(root)
    dialog.set_child(view)
    dialog.set_default_widget(save_btn)
    dialog.set_focus(title_entry)

    def _update_count(_buf=None):
        txt = desc_buf.get_text(desc_buf.get_start_iter(), desc_buf.get_end_iter(), True) or ""
        count_lbl.set_text(f"{len(txt)}/500 characters")
        if len(txt) > 500:
            count_lbl.add_css_class("status-error")
        else:
            count_lbl.remove_css_class("status-error")
        return False

    desc_buf.connect("changed", _update_count)
    _update_count()

    def _valid():
        title = str(title_entry.get_text() or "").strip()
        desc = desc_buf.get_text(desc_buf.get_start_iter(), desc_buf.get_end_iter(), True) or ""
        return bool(title) and len(desc) <= 500

    def _sync_save(*_args):
        # Fork: both were checked after the dialog had closed, so what had been typed was lost.
        save_btn.set_sensitive(_valid())

    title_entry.connect("changed", _sync_save)
    desc_buf.connect("changed", _sync_save)
    _sync_save()

    def _submit(*_args):
        if not _valid():
            return
        title = str(title_entry.get_text() or "").strip()
        desc = desc_buf.get_text(desc_buf.get_start_iter(), desc_buf.get_end_iter(), True) or ""
        is_public = bool(public_switch.get_active())
        selected_folder_id = str(initial_folder_id or "root")
        if folder_dd is not None and folder_ids:
            idx = int(folder_dd.get_selected())
            if 0 <= idx < len(folder_ids):
                selected_folder_id = folder_ids[idx]
        dialog.close()
        if not title:
            self.show_output_notice("Playlist title cannot be empty.", "warn", 2600)
            return
        if len(desc) > 500:
            self.show_output_notice("Description is too long (max 500).", "warn", 2600)
            return
        if callable(on_submit):
            on_submit(title, desc, is_public, selected_folder_id)

    cancel_btn.connect("clicked", lambda _b: dialog.close())
    save_btn.connect("clicked", _submit)
    title_entry.connect("activate", _submit)  # Enter in the title saves
    dialogs.present(self, dialog)


def on_remote_playlist_rename_clicked(self, playlist_obj=None):
    pl = playlist_obj or getattr(self, "current_remote_playlist", None)
    if pl is None:
        return
    title_init = str(getattr(pl, "name", None) or "Untitled Playlist")
    desc_init = str(getattr(pl, "description", None) or "")
    public_init = bool(getattr(pl, "public", False))

    def _submit(title, desc, is_public, _folder_id):
        self.show_output_notice("Saving playlist...", "ok", 1800)

        def task():
            res = self.backend.update_cloud_playlist(pl, name=title, description=desc, is_public=is_public)

            def apply():
                if bool(res.get("ok")):
                    try:
                        pl.name = title
                        pl.description = desc
                        pl.public = is_public
                    except Exception:
                        pass
                    self.show_output_notice("Playlist updated.", "ok", 2400)
                    if getattr(self, "current_remote_playlist", None) is not None and getattr(self.current_remote_playlist, "id", None) == getattr(pl, "id", None):
                        self.on_remote_playlist_card_clicked(pl)
                else:
                    self.show_output_notice("Failed to update playlist.", "warn", 3200)
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    self._open_cloud_playlist_editor(
        dialog_title="Edit playlist",
        save_label="Save",
        initial_title=title_init,
        initial_desc=desc_init,
        initial_public=public_init,
        playlist_obj=pl,
        on_submit=_submit,
    )


def on_remote_playlist_delete_clicked(self, playlist_obj=None):
    pl = playlist_obj or getattr(self, "current_remote_playlist", None)
    if pl is None:
        return
    pname = str(getattr(pl, "name", None) or "this playlist")
    def _delete():
        self.show_output_notice("Deleting playlist...", "ok", 1600)

        def task():
            res = self.backend.delete_cloud_playlist(pl)

            def apply():
                if bool(res.get("ok")):
                    self.show_output_notice("Playlist deleted.", "ok", 2200)
                    if getattr(self, "current_remote_playlist", None) is not None and getattr(self.current_remote_playlist, "id", None) == getattr(pl, "id", None):
                        self.current_remote_playlist = None
                    self.render_playlists_home()
                else:
                    self.show_output_notice("Failed to delete playlist.", "warn", 3000)
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    dialogs.confirm(
        self,
        "Delete Playlist?",
        f"“{pname}” will be deleted from your TIDAL account. This cannot be undone.",
        "Delete",
        _delete,
        destructive=True,
    )


def on_remote_playlist_move_to_folder_clicked(self, playlist_obj=None):
    pl = playlist_obj or getattr(self, "current_remote_playlist", None)
    if pl is None:
        return

    def _move(target_id):
        self.show_output_notice("Moving playlist...", "ok", 1800)

        def task():
            res = self.backend.move_cloud_playlist_to_folder(pl, target_folder_id=target_id)

            def apply():
                if bool(res.get("ok")):
                    self.show_output_notice("Playlist moved.", "ok", 2200)
                    self.current_remote_playlist = None
                    self.current_playlist_folder = None
                    self.current_playlist_folder_stack = []
                    self.render_playlists_home()
                else:
                    self.show_output_notice("Failed to move playlist.", "warn", 2800)
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    # Fork: listing the folders is a request. It ran on the main thread before the dialog opened.
    def _fetch():
        folders = [{"id": "root", "path": "Root"}] + list(self.backend.get_all_playlist_folders(limit=1000) or [])
        options = [(str(f.get("id", "root")), str(f.get("path", "Root"))) for f in folders]

        def _present():
            dialogs.choose(
                self,
                "Move to Folder",
                "",
                [label for _fid, label in options],
                "Move",
                lambda index: _move(options[index][0]),
            )
            return False

        GLib.idle_add(_present)

    submit_daemon(_fetch)


# Fork: removing a track from your own TIDAL playlist hides it at once and offers Undo. The
# removal is sent once the notice has gone (it used to be sent at once, with no way back, and
# then reloaded the page from the top). Removal is by track id, so waiting can't hit the wrong row.
_UNDO_NOTICE_MS = 5000
_UNDO_COMMIT_MS = 5300  # after the notice, so Undo can't be clicked once the request is out


def _track_title(track):
    if isinstance(track, dict):
        return str(track.get("title") or track.get("name") or "track")
    return str(getattr(track, "name", None) or getattr(track, "title", None) or "track")


def on_remove_single_track_from_remote_playlist(self, track):
    pl = getattr(self, "current_remote_playlist", None)
    track_id = getattr(track, "id", None) if track is not None else None
    if pl is None or track_id is None:
        return
    _flush_pending_playlist_removal(self)
    pending = {"pl": pl, "track": track, "track_id": track_id, "source": 0}

    def _due():
        pending["source"] = 0
        _commit_playlist_removal(self, pending)
        return False

    pending["source"] = GLib.timeout_add(_UNDO_COMMIT_MS, _due)
    self._pending_playlist_removal = pending
    set_track_rows_hidden(self.track_list, track_id, True)
    self.show_undo_notice(
        f"Removed \u201c{_track_title(track)}\u201d", lambda: _undo_playlist_removal(self, pending), _UNDO_NOTICE_MS
    )


def _undo_playlist_removal(self, pending):
    if getattr(self, "_pending_playlist_removal", None) is not pending:
        return  # already sent
    self._pending_playlist_removal = None
    if pending.get("source"):
        GLib.source_remove(pending["source"])
        pending["source"] = 0
    if getattr(self, "current_remote_playlist", None) is pending["pl"]:
        set_track_rows_hidden(self.track_list, pending["track_id"], False)


def _flush_pending_playlist_removal(self, wait=False):
    """Send a removal still inside its Undo window now (another removal, or the app quitting)."""
    pending = getattr(self, "_pending_playlist_removal", None)
    if pending is None:
        return
    if pending.get("source"):
        GLib.source_remove(pending["source"])
        pending["source"] = 0
    _commit_playlist_removal(self, pending, wait=wait)


def _commit_playlist_removal(self, pending, wait=False):
    if getattr(self, "_pending_playlist_removal", None) is pending:
        self._pending_playlist_removal = None

    def task():
        try:
            res = self.backend.remove_tracks_from_cloud_playlist(pending["pl"], [pending["track"]])
            ok = bool((res or {}).get("ok"))
        except Exception:
            logger.exception("Removing a track from a cloud playlist failed")
            ok = False
        if not wait:
            GLib.idle_add(_after_playlist_removal, self, pending, ok)
        return ok

    if wait:
        task()  # at shutdown a daemon worker would die with the process
    else:
        submit_daemon(task)


def _decrement_track_count(pl):
    for attr in ("num_tracks", "number_of_tracks", "numberOfTracks"):
        try:
            count = int(getattr(pl, attr, 0) or 0)
            if count > 0:
                setattr(pl, attr, count - 1)
        except Exception:
            pass


def _after_playlist_removal(self, pending, ok):
    pl, track_id = pending["pl"], pending["track_id"]
    on_page = getattr(self, "current_remote_playlist", None) is pl
    if not ok:
        if on_page:
            set_track_rows_hidden(self.track_list, track_id, False)
        self.show_output_notice(
            f"Couldn't remove \u201c{_track_title(pending['track'])}\u201d from the playlist.", "warn", 3200
        )
        return False
    _decrement_track_count(pl)
    view = getattr(self, "_remote_pl_view", None)
    if on_page and view is not None and view.get("pl") is pl:
        view["drop"](track_id)
    return False


def on_playlist_track_selected(self, box, row):
    if not row:
        return
    idx = getattr(row, "playlist_track_index", -1)
    tracks = getattr(box, "playlist_tracks", [])
    if not tracks or idx < 0 or idx >= len(tracks):
        return
    pl_name = ""
    pl_id = getattr(self, "current_playlist_id", None)
    if pl_id and hasattr(self, "playlist_mgr"):
        p = self.playlist_mgr.get_playlist(pl_id)
        pl_name = (p.get("name", "") if p else "") if p else ""
    if not pl_name:
        rpl = getattr(self, "current_remote_playlist", None)
        pl_name = str(getattr(rpl, "name", "") or getattr(rpl, "title", "") or "") if rpl else ""
    rpl_obj = getattr(self, "current_remote_playlist", None)
    self.playback_source = {"type": "playlist", "name": pl_name or "Playlist", "playlist_id": pl_id, "obj": rpl_obj}
    self.current_track_list = tracks
    self._set_play_queue(tracks)
    self.play_track(idx)


def _next_playlist_name(self):
    return "New Playlist"


def on_create_playlist_clicked(self, _btn=None):
    if not getattr(self.backend, "user", None):
        self._show_simple_dialog("Login Required", "Please login first.")
        return
    default_name = self._next_playlist_name()
    folder_rows = [{"id": "root", "path": "Root"}] + list(self.backend.get_all_playlist_folders(limit=1000) or [])
    folder_options = [(str(row.get("id", "root")), str(row.get("path", "Root"))) for row in folder_rows]
    initial_folder_id = "root"
    if getattr(self, "current_playlist_folder", None) is not None:
        initial_folder_id = str(getattr(self.current_playlist_folder, "id", "root") or "root")

    def _submit(name, desc, is_public, folder_id):
        self.show_output_notice("Creating cloud playlist...", "ok", 1600)

        def task():
            pl = self.backend.create_cloud_playlist_in_folder(name, desc, parent_folder_id=folder_id)
            if pl is not None and bool(is_public):
                try:
                    self.backend.update_cloud_playlist(pl, is_public=True)
                except Exception:
                    pass

            def apply():
                if pl is None:
                    self.show_output_notice("Failed to create cloud playlist.", "warn", 2600)
                    return False
                self.show_output_notice(f"Created playlist: {getattr(pl, 'name', name)}", "ok", 2200)
                self.render_playlists_home()
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    self._open_cloud_playlist_editor(
        dialog_title="Create playlist",
        save_label="Create",
        initial_title=default_name,
        initial_desc="Created with Ebb",
        initial_public=False,
        playlist_obj=None,
        folder_options=folder_options,
        initial_folder_id=initial_folder_id,
        on_submit=_submit,
    )


def _prompt_playlist_pick(self, on_pick):
    if not getattr(self.backend, "user", None):
        self._show_simple_dialog("Login Required", "Please login first.")
        return

    # `get_user_playlists(limit=1000)` is paginated — up to ~20 HTTP
    # round-trips at 50/page.  Running it synchronously on the GTK main
    # thread froze the UI long enough for Wayland to tear down the surface
    # (vkAcquireNextImageKHR → VK_SUBOPTIMAL_KHR →
    # VK_ERROR_SURFACE_LOST_KHR → "Broken pipe dispatching to Wayland
    # display") and the app crashed.  Fetch on a daemon thread and build
    # the dialog only after the data lands.
    self.show_output_notice("Loading playlists…", "ok", 1800)

    def _create_and_pick(use_dedupe):
        def _task():
            created = self.backend.create_cloud_playlist(
                self._next_playlist_name(), "Created with Ebb"
            )

            def _apply():
                if created is not None:
                    on_pick(created, use_dedupe)
                else:
                    self.show_output_notice(
                        "Failed to create cloud playlist.", "warn", 2600
                    )
                return False

            GLib.idle_add(_apply)

        submit_daemon(_task)

    def _fetch_task():
        playlists = list(self.backend.get_user_playlists(limit=1000) or [])

        def _present():
            if not playlists:
                _create_and_pick(True)
                return False

            names = [getattr(p, "name", None) or "Untitled Playlist" for p in playlists]
            dedupe_ck = Gtk.CheckButton(label="Skip tracks already in the playlist", active=True)
            dialogs.choose(
                self,
                "Add to Playlist",
                "",
                names,
                "Add",
                lambda index: on_pick(playlists[index], dedupe_ck.get_active()),
                extra_child=dedupe_ck,
                extra_responses=(("New Playlist", lambda: _create_and_pick(dedupe_ck.get_active())),),
            )
            return False

        GLib.idle_add(_present)

    submit_daemon(_fetch_task)


def on_add_tracks_to_playlist(self, tracks):
    items = [t for t in (tracks or []) if t is not None]
    if not items:
        return

    def _do_add(playlist_obj, dedupe):
        self.show_output_notice("Adding tracks to cloud playlist...", "ok", 1800)

        def task():
            res = self.backend.add_tracks_to_cloud_playlist(playlist_obj, items, dedupe=bool(dedupe), batch_size=100)

            def apply():
                if bool(res.get("ok")):
                    added = int(res.get("added", 0) or 0)
                    requested = int(res.get("requested", 0) or 0)
                    skipped = max(0, requested - added)
                    msg = f"Added {added} tracks"
                    if skipped:
                        msg += f" (skipped {skipped})"
                    self.show_output_notice(msg, "ok", 2600)
                else:
                    self.show_output_notice("Failed to add tracks to cloud playlist.", "warn", 3000)
                return False

            GLib.idle_add(apply)

        submit_daemon(task)

    self._prompt_playlist_pick(_do_add)


def on_add_single_track_to_playlist(self, track):
    if track is None:
        return
    self.on_add_tracks_to_playlist([track])


def on_add_current_album_to_playlist(self, _btn=None):
    tracks = list(getattr(self, "current_track_list", []) or [])
    if not tracks:
        return
    self.on_add_tracks_to_playlist(tracks)


def _prompt_playlist_name(
    self,
    title,
    initial_name,
    on_submit,
    subtitle=None,
    placeholder=None,
    save_label="Save",
    dialog_size=None,
):
    # dialog_size: unused now that the prompt is a dialog inside the window; the callers pass it.
    dialogs.prompt_text(
        self, title, subtitle, initial_name, on_submit, placeholder=placeholder, save_label=save_label
    )


def on_playlist_start_inline_rename(self, playlist_id):
    self.playlist_rename_mode = True
    self.render_playlist_detail(playlist_id)


def on_playlist_commit_inline_rename(self, playlist_id, name):
    new_name = (name or "").strip()
    if new_name:
        self.playlist_mgr.rename_playlist(playlist_id, new_name)
    self.playlist_rename_mode = False
    self.render_playlist_detail(playlist_id)


def on_playlist_cancel_inline_rename(self, playlist_id):
    self.playlist_rename_mode = False
    self.render_playlist_detail(playlist_id)


def on_playlist_delete_clicked(self, playlist_id):
    def _delete():
        self.playlist_mgr.delete_playlist(playlist_id)
        self.current_playlist_id = None
        self.render_playlists_home()

    dialogs.confirm(
        self, "Delete Playlist?", "This playlist will be deleted permanently.", "Delete", _delete, destructive=True
    )


def on_playlist_remove_track_clicked(self, playlist_id, track_index):
    # Fork: keep a copy of the entry so the notice can offer Undo.
    entry = None
    try:
        tracks = list((self.playlist_mgr.get_playlist(playlist_id) or {}).get("tracks") or [])
        if 0 <= int(track_index) < len(tracks):
            entry = copy.deepcopy(tracks[int(track_index)])
    except Exception:
        entry = None
    removed = self.playlist_mgr.remove_track(playlist_id, track_index)
    self.render_playlist_detail(playlist_id)
    if not removed or entry is None:
        return

    def _undo():
        if self.playlist_mgr.insert_track_entry(playlist_id, track_index, entry):
            if str(getattr(self, "current_playlist_id", "") or "") == str(playlist_id):
                self.render_playlist_detail(playlist_id)

    self.show_undo_notice(f"Removed \u201c{_track_title(entry)}\u201d", _undo, _UNDO_NOTICE_MS)


def on_playlist_move_track_clicked(self, playlist_id, track_index, direction):
    self.playlist_mgr.move_track(playlist_id, track_index, direction)
    self.render_playlist_detail(playlist_id)


def on_playlist_toggle_edit(self, _btn=None):
    self.playlist_edit_mode = not bool(getattr(self, "playlist_edit_mode", False))
    if self.current_playlist_id:
        self.render_playlist_detail(self.current_playlist_id)


def on_playlist_reorder_track(self, playlist_id, from_index, to_index):
    if self.playlist_mgr.move_track_to(playlist_id, from_index, to_index):
        self.render_playlist_detail(playlist_id)
