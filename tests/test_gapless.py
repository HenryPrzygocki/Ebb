"""Fork: gapless playback, the app's half (actions/gapless.py; the engine's is gapless.rs)."""
import os
import sys
import time
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import gapless, playback_actions, up_next  # noqa: E402
from app import app_queue  # noqa: E402


class Track:
    def __init__(self, name):
        self.name = name
        self.id = name


def mpd(track_id):
    return f"/tmp/hiresti_{track_id}.mpd"


class FakePlayer:
    def __init__(self):
        self._last_loaded_uri = ""
        self.queued = []
        self.gapless = True

    def supports_gapless(self):
        return self.gapless

    def queue_next(self, uri):
        self.queued.append(uri)
        return 0


class FakeBackend:
    quality = "LOSSLESS"

    def __init__(self):
        self.resolved = []

    def get_stream_url(self, track):
        self.resolved.append(track.id)
        return mpd(track.id)


class FakeApp:
    MODE_LOOP, MODE_ONE, MODE_SHUFFLE, MODE_SMART, MODE_NORMAL = 0, 1, 2, 3, 4

    def __init__(self, names=("t0", "t1", "t2"), mode=4):
        self.play_queue = [Track(n) for n in names]
        self.play_mode = mode
        self.player = FakePlayer()
        self.backend = FakeBackend()
        self.stream_prefetch_cache = {}
        self.current_track_index = -1
        self.playing_track = None
        self._play_request_id = 0
        self.played = []  # (name, engine_advanced)
        self.reloads = 0
        self._refresh_queue_views = lambda: None
        self._update_track_list_icon = lambda: None
        self.play_track(0)

    def _get_active_queue(self):
        return list(self.play_queue)

    def get_next_index(self, direction=1):
        return playback_actions.get_next_index(self, direction)

    def play_track(self, index, from_history=False, engine_advanced=False):  # bookkeeping, no audio
        self._play_request_id += 1
        gapless.disarm(self)
        queue = self._get_active_queue()
        entry = queue[index]
        playback_actions.record_track_change(self, queue, entry, from_history=from_history)
        self.current_track_index = index
        self.playing_track = entry
        self.played.append((entry.name, engine_advanced))
        if not engine_advanced:
            self.player._last_loaded_uri = mpd(entry.id)  # load() would set it
        up_next.settle(self)

    def on_next_track(self, auto=False):  # the end of a track without gapless
        self.reloads += 1
        playback_actions.on_next_track(self, auto=auto)

    def end_of_track_soon(self):
        gapless.on_about_to_finish(self, self.player._last_loaded_uri)

    def engine_advances(self):
        """The engine continued into the track it was handed (the adapter updates the URI)."""
        uri = self.player.queued[-1]
        self.player._last_loaded_uri = uri
        gapless.on_gapless_advance(self, uri)


@pytest.fixture(autouse=True)
def inline(monkeypatch):
    """The resolve thread and main-loop callbacks run inline."""

    class InlineThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(gapless, "Thread", InlineThread)
    monkeypatch.setattr(gapless.GLib, "idle_add", lambda fn, *args: fn(*args))
    monkeypatch.delenv("HIRESTI_DISABLE_GAPLESS", raising=False)
    monkeypatch.delenv("HIRESTI_LOCAL_URI", raising=False)


def test_the_next_track_is_handed_to_the_engine_before_this_one_ends():
    app = FakeApp()
    app.end_of_track_soon()
    assert app.player.queued == [mpd("t1")]
    assert app.backend.resolved == ["t1"]


def test_a_fresh_prefetched_stream_is_reused():
    app = FakeApp()
    app.stream_prefetch_cache["t1"] = {"url": "/tmp/prefetched.mpd", "quality": "LOSSLESS",
                                       "fetched_at": time.monotonic()}
    app.end_of_track_soon()
    assert app.player.queued == ["/tmp/prefetched.mpd"]
    assert app.backend.resolved == []


def test_the_advance_changes_track_without_a_reload_and_hands_over_the_next():
    app = FakeApp()
    app.end_of_track_soon()
    app.engine_advances()
    assert app.played[-1] == ("t1", True)
    assert app.current_track_index == 1
    assert app.reloads == 0
    app.end_of_track_soon()
    assert app.player.queued[-1] == mpd("t2")


def test_up_next_is_what_follows():
    app = FakeApp()
    app_queue.add_tracks_to_queue(app, [Track("X")])
    app.end_of_track_soon()
    assert app.player.queued == [mpd("X")]
    app.engine_advances()
    assert app.played[-1] == ("X", True)
    assert up_next.pending(app) == []


def test_shuffle_hands_over_the_track_it_then_plays():
    app = FakeApp(names=[f"t{i}" for i in range(12)], mode=FakeApp.MODE_SHUFFLE)
    for _ in range(5):
        app.end_of_track_soon()
        handed = app.player.queued[-1]
        app.engine_advances()
        assert mpd(app.played[-1][0]) == handed and app.played[-1][1] is True
    assert app.reloads == 0
    assert len({name for name, _ in app.played}) == 6, "no repeats within a shuffle cycle"


def test_a_queue_change_after_the_hand_over_loads_the_right_track():
    app = FakeApp()
    app.end_of_track_soon()  # t1 is handed over...
    app_queue.add_tracks_to_queue(app, [Track("X")])  # ...then X is queued
    app.engine_advances()  # the engine went on to t1 regardless
    assert app.reloads == 1
    assert app.played[-1] == ("X", False), "X plays, loaded the usual way"


def test_no_hand_over_on_repeat_one_at_the_end_of_the_queue_or_when_unavailable(monkeypatch):
    app = FakeApp(mode=FakeApp.MODE_ONE)
    app.end_of_track_soon()
    assert app.player.queued == []

    app = FakeApp(names=("only",))
    app.end_of_track_soon()
    assert app.player.queued == []

    app = FakeApp()
    app.player.gapless = False  # an engine build without rac_queue_next
    app.end_of_track_soon()
    assert app.player.queued == []

    app = FakeApp()
    monkeypatch.setenv("HIRESTI_DISABLE_GAPLESS", "1")
    app.end_of_track_soon()
    assert app.player.queued == []


def test_stale_and_repeated_events_are_ignored():
    app = FakeApp()
    gapless.on_about_to_finish(app, "/tmp/a_track_no_longer_loaded.mpd")
    assert app.player.queued == []
    app.end_of_track_soon()
    app.end_of_track_soon()  # a seek near the end asks again
    assert app.player.queued == [mpd("t1")]


def test_a_track_change_while_the_stream_resolves_cancels_the_hand_over(monkeypatch):
    app = FakeApp()
    real_resolve = gapless.resolve_stream

    def resolve_while_the_user_skips(app_, entry):
        url = real_resolve(app_, entry)
        app_.play_track(2)
        return url

    monkeypatch.setattr(gapless, "resolve_stream", resolve_while_the_user_skips)
    app.end_of_track_soon()
    assert app.player.queued == []


def test_play_track_after_an_advance_never_touches_the_engine(monkeypatch):
    from actions import lyrics_playback_actions as playback

    tasks = []

    class RecordingThread:
        def __init__(self, target=None, args=(), daemon=None, **_kw):
            self.target = target

        def start(self):
            if getattr(self.target, "__name__", "") == "task":
                tasks.append(self.target)

    monkeypatch.setattr(playback, "Thread", RecordingThread)
    monkeypatch.setattr(playback.GLib, "idle_add", lambda *a, **k: 0)
    monkeypatch.setattr(playback, "_apply_track_redirect", lambda *a: None)
    monkeypatch.setattr(playback_actions, "record_track_change", lambda *a, **k: None)
    monkeypatch.setattr(up_next, "settle", lambda app: False)
    track = SimpleNamespace(id="t1", name="T1", cover=None, artist=SimpleNamespace(name="A"),
                            album=SimpleNamespace(name="B", cover=None))
    app = mock.MagicMock()
    app._play_request_id = 0
    app.play_mode = 4
    app._get_active_queue.return_value = [track]
    app.stream_prefetch_cache = {}
    app.audio_cache_tracks = 0
    app.backend.quality = "LOSSLESS"
    app.backend.get_stream_url.return_value = mpd("t1")
    app.backend._last_stream_bit_depth = 16
    app.backend._last_stream_sample_rate = 44100
    app.backend.get_lyrics.return_value = None
    app.player._last_loaded_uri = mpd("t1")
    app.player.output_state = "active"
    app.player.output_error = ""
    app.player._pipewire_rate_blocked = False

    playback.play_track(app, 0, engine_advanced=True)
    assert len(tasks) == 1
    tasks.pop()()
    app.player.load.assert_not_called()
    app.player.play.assert_not_called()
    app.backend.get_stream_url.assert_not_called()
    assert app.playing_track is track and app.current_track_index == 0

    playback.play_track(app, 0)  # an ordinary track change still loads and plays
    tasks.pop()()
    app.player.load.assert_called_once_with(mpd("t1"))
    app.player.play.assert_called_once()


def test_the_adapter_adopts_the_advance_without_reloading(monkeypatch):
    audio = pytest.importorskip("_rust.audio")
    calls = []
    adapter = SimpleNamespace(
        stream_info={"codec": "FLAC", "rate": 96000, "depth": 24, "bitrate": 2_400_000},
        _cached_pos_s=301.5, _cached_dur_s=302.0, _last_loaded_uri=mpd("a"),
        _reset_rust_visual_sync_state=lambda: calls.append("reset"),
        _on_gapless_advance_callback=lambda uri: calls.append(uri),
    )
    monkeypatch.setattr(audio.GLib, "idle_add", lambda fn, *args: fn(*args))
    audio.RustAudioPlayerAdapter._adopt_gapless_advance(adapter, mpd("b"))
    assert adapter._last_loaded_uri == mpd("b")
    assert (adapter._cached_pos_s, adapter._cached_dur_s) == (0.0, 0.0)
    assert adapter.stream_info["rate"] == 96000 and adapter.stream_info["bitrate"] == 0
    assert calls == ["reset", mpd("b")]
    assert audio._event_uri(f"native-transport gapless-advance prev_frames=9 uri={mpd('b')}") == mpd("b")
    assert audio._event_uri("native-transport about-to-finish") == ""
