"""Fork: after Play, one log line says whether the position actually advanced.

2026-11-27: a resume after the headset reset while paused reported Playing with no sound and
left nothing in the log."""
import logging
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from _rust import audio as rust_audio  # noqa: E402

_Adapter = rust_audio.RustAudioPlayerAdapter


def _player(monkeypatch, positions):
    ticks = []
    monkeypatch.setattr(rust_audio.GLib, "timeout_add", lambda ms, fn: ticks.append(fn) or 7)
    monkeypatch.setattr(rust_audio.GLib, "source_remove", lambda _id: None)
    seq = iter(positions)
    player = SimpleNamespace(
        _cached_pos_s=0.0, _cached_is_playing=True, _last_loaded_uri="file:///tmp/x.mpd",
        output_state="active", output_error=None, _PLAY_CHECK_SAMPLES=4,
        _effective_output_selection=lambda: ("PipeWire", "pipewire"),
    )
    player._refresh_rust_cache = lambda force=False: setattr(player, "_cached_pos_s", next(seq))
    return player, ticks


def _run(player, ticks):
    _Adapter._start_play_progress_check(player)
    fn = ticks[0]
    while fn():
        pass


def test_a_moving_position_logs_advancing(monkeypatch, caplog):
    player, ticks = _player(monkeypatch, [10.0, 11.0, 12.0, 13.0, 14.0])
    with caplog.at_level(logging.INFO):
        _run(player, ticks)
    assert "Play check: advancing (10.0 -> 11.0 -> 12.0 -> 13.0 -> 14.0 s)" in caplog.text


def test_a_stuck_or_bouncing_position_logs_a_warning(monkeypatch, caplog):
    player, ticks = _player(monkeypatch, [12.0, 12.9, 12.1, 12.8, 12.0])
    with caplog.at_level(logging.INFO):
        _run(player, ticks)
    assert "Play check: NOT advancing (12.0 -> 12.9 -> 12.1 -> 12.8 -> 12.0 s)" in caplog.text
    assert "WARNING" in caplog.text


def test_pausing_during_the_check_logs_nothing(monkeypatch, caplog):
    player, ticks = _player(monkeypatch, [5.0, 6.0])
    with caplog.at_level(logging.INFO):
        _Adapter._start_play_progress_check(player)
        player._cached_is_playing = False
        assert ticks[0]() is False
    assert "Play check" not in caplog.text


def test_an_output_error_that_halts_playback_is_logged(monkeypatch, caplog):
    player, ticks = _player(monkeypatch, [5.0, 5.0])
    with caplog.at_level(logging.INFO):
        _Adapter._start_play_progress_check(player)
        player._cached_is_playing = False
        player.output_state, player.output_error = "error", "snd_pcm_open(default) rc=-2"
        assert ticks[0]() is False
    assert "Play check: playback halted by the output (5.0 s)" in caplog.text
    assert "snd_pcm_open(default) rc=-2" in caplog.text
