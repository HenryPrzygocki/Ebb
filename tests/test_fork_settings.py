"""Fork: the fork's own settings survive a save and a load (core/settings.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import settings as S  # noqa: E402


def test_fork_settings_survive_a_save_and_load(tmp_path):
    # normalize_settings() rebuilds the dict from the keys it knows; the fork's own settings
    # were dropped on every save until they were added there.
    path = str(tmp_path / "settings.json")
    S.save_settings(path, {"window_transparency": 0.4, "card_size": "large", "show_spectrum": True, "play_mode": 5})
    loaded = S.load_settings(path)
    assert loaded["window_transparency"] == 0.4
    assert loaded["card_size"] == "large"
    assert loaded["show_spectrum"] is True
    assert loaded["play_mode"] == 5


def test_odd_values_fall_back_to_the_defaults():
    odd = S.normalize_settings({"window_transparency": "x", "card_size": "huge", "show_spectrum": "maybe"})
    assert (odd["window_transparency"], odd["card_size"], odd["show_spectrum"]) == (0.25, "medium", False)
    assert S.normalize_settings({"window_transparency": 5})["window_transparency"] == 0.6
    assert S.normalize_settings({})["card_size"] == "medium"
