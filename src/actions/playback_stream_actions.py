from threading import Thread

from gi.repository import GLib

import utils


def on_quality_changed(app, dd, p):
    selected = dd.get_selected_item()
    if not selected:
        return
    mode_str = selected.get_string()
    app.backend.set_quality_mode(mode_str)
    from ui import account  # fork: the AAC banner only applies while lossless is requested
    account.sync_banner(app)
    if hasattr(app, "stream_prefetch_cache"):
        app.stream_prefetch_cache.clear()

    if app.player.is_playing() and app.current_index >= 0:
        pos, _ = app.player.get_position()
        track = app.current_track_list[app.current_index]

        def refresh():
            new_url = app.backend.get_stream_url(track)
            GLib.idle_add(lambda: app._restart_player_with_url(new_url, pos))

        Thread(target=refresh, daemon=True).start()


def restart_player_with_url(app, url, pos):
    if not url:
        return
    app.player.stop()
    if hasattr(app.player, "hint_source_format"):
        bd = int(getattr(app.backend, "_last_stream_bit_depth", 0) or 0)
        sr = int(getattr(app.backend, "_last_stream_sample_rate", 0) or 0)
        if bd or sr:
            app.player.hint_source_format(bd, sr)
    app.player.load(url)
    app.player.play()
    GLib.timeout_add(700, lambda: app.player.seek(pos))
    if hasattr(app, "_mpris_sync_playback"):
        app._mpris_sync_playback()
    if hasattr(app, "_mpris_emit_seeked"):
        GLib.timeout_add(750, lambda: (app._mpris_emit_seeked(pos), False)[1])


def load_cover_art(app, cover_id_or_url):
    app._bar_cover_ref = cover_id_or_url  # fork: the mini player's cover loads it at 640 px
    url = app._get_tidal_image_url(cover_id_or_url)
    if not url:
        return

    if hasattr(app, "_prime_now_playing_cover_color"):
        try:
            app._prime_now_playing_cover_color(url)
        except Exception:
            pass

    if hasattr(app, "art_img"):
        # Fork: at the window tier's size (ui/builders.py set_bar_cover_size), not always 80.
        utils.load_img(app.art_img, url, app.cache_dir, int(getattr(app, "_bar_art_px", 80) or 80))
    from ui import mini_player

    mini_player.load_cover(app)
