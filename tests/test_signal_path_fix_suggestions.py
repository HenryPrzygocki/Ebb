"""Fork #15: the diagnostics' "How to Fix" only suggests what the current driver can do.

Bit-Perfect implies exclusive output and hides PipeWire, and PipeWire force-rate never runs since
upstream 1.9.6, yet PipeWire users were told to enable Bit-Perfect and to restart playback to
apply force-rate."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from services import signal_path  # noqa: E402


def _view(driver, bit_perfect=False):
    view = SimpleNamespace(
        player=SimpleNamespace(bit_perfect_mode=bit_perfect, current_driver=driver),
        _get_current_driver=lambda: driver,
        _get_pipewire_clock_state=lambda: (0, ""),
    )
    cls = next(v for v in vars(signal_path).values() if isinstance(v, type) and hasattr(v, "_build_fix_suggestions"))
    return lambda *a: cls._build_fix_suggestions(view, *a)


def test_pipewire_is_pointed_at_an_exclusive_driver_not_at_dead_force_rate():
    fixes = _view("PipeWire")("active", "96kHz", "24-bit")
    assert fixes == ["For bit-perfect output, choose ALSA or USB Rawlink, then turn on Bit-Perfect"]
    assert not any("force-rate" in f or f == "Enable Bit-Perfect mode" for f in fixes)


def test_other_drivers_still_get_the_bit_perfect_switch_and_the_rest():
    assert _view("ALSA（auto）")("error", "Unknown", "Unknown") == [
        "Enable Bit-Perfect mode", "Click Recover in Settings", "Play a track for a few seconds to detect format"]
    assert _view("USB Rawlink v2", bit_perfect=True)("active", "96kHz", "24-bit") == []
