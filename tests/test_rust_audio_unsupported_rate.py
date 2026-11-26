"""Fork #11: a DAC with no mode for the track's rate stops on that track and says why.

A 44.1/48 kHz-only device (the Bose QC Ultra 2 is one) on Rawlink failed a 96 kHz track with the
raw "no alt-setting for rate=96000 bit_depth=24" after three retries and the player went on to the
next track. The engine has no resampler on any output, so the DSP resampler can't help either."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from _rust import audio as rust_audio  # noqa: E402

_Adapter = rust_audio.RustAudioPlayerAdapter
_ERR = (
    "native-transport USB rate-setting failed after 3 retries: "
    "no alt-setting for rate=96000 bit_depth=24 on 'Bose QC Ultra 2'"
)


def _classifier():
    return SimpleNamespace(**{k: getattr(_Adapter, k) for k in (
        "_ERR_USB_PERMISSION_KEYS", "_ERR_DEVICE_KEYS", "_ERR_ALSA_FAULT_KEYS", "_ERR_NETWORK_KEYS", "_ERR_CODEC_KEYS")})


def test_a_missing_alt_setting_is_its_own_category_not_a_disconnect():
    assert _Adapter._classify_rust_error(_classifier(), _ERR) == "unsupported_rate"
    # Not shadowed by the permission check, and permission still wins when both appear.
    assert _Adapter._classify_rust_error(_classifier(), "Access denied (insufficient permissions)") == "usb_permission"


def test_the_message_names_the_format_and_the_way_out():
    msg = rust_audio._unsupported_rate_message(_ERR)
    assert msg.startswith("This device can't play 96 kHz / 24-bit.")
    assert "PipeWire" in msg
    assert "44.1 kHz" in rust_audio._unsupported_rate_message("no alt-setting for rate=44100 bit_depth=32")
    assert rust_audio._unsupported_rate_message("something else") == "This device can't play this track's sample rate."


def _player():
    stopped, advanced = [], []
    player = SimpleNamespace(
        output_state="active", output_error=None, _cached_is_playing=True, limiter_enabled=False,
        _limiter_negotiation_retry_pending=False, _rust_disconnect_recovering=False,
        _rust=SimpleNamespace(stop=lambda: stopped.append(True)),
        _recover_after_disconnect=lambda: advanced.append("recover"),
        exclusive_lock_mode=False, current_driver="USB Rawlink v2",
        _last_loaded_uri="https://example.invalid/track-96k.flac",
        _release_pipewire_clock_override=lambda reason=None: None,
        _on_eos_callback=lambda: advanced.append("next"),
    )
    return player, stopped, advanced


def test_the_track_stops_with_the_message_and_the_end_of_stream_does_not_skip(monkeypatch):
    player, stopped, advanced = _player()
    _Adapter._apply_rust_error_policy(player, "unsupported_rate", _ERR)
    assert stopped == [True] and player._cached_is_playing is False
    assert player.output_state == "error" and player.output_error.startswith("This device can't play 96 kHz")
    assert player._eos_blocked_uri == player._last_loaded_uri

    idles = []
    monkeypatch.setattr(rust_audio.GLib, "idle_add", lambda fn, *a: idles.append(fn))
    eos = rust_audio._RustAudioCore.EVENT_EOS
    _Adapter._on_rust_event(player, eos, "native-transport-eos")
    assert idles == []  # stays on the track that can't play

    player._last_loaded_uri = "https://example.invalid/next-44k.flac"  # the user picked another track
    _Adapter._on_rust_event(player, eos, "native-transport-eos")
    assert idles == [player._on_eos_callback]
