"""Fork: playlist collages are built in load_img's worker, never on the main thread.

Building a collage that is not cached yet downloads up to four covers and decodes them, and
gdk-pixbuf decodes through glycin and GIO: with gvfsd-metadata hung, each decode on the main
thread froze the UI for the 25 s D-Bus timeout.
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

pytest.importorskip("gi")

from actions import ui_actions  # noqa: E402


class _Img:
    def __init__(self):
        self.icon = None
        self.pixel_size = -1

    def set_pixel_size(self, px):
        self.pixel_size = px

    def set_from_icon_name(self, name):
        self.icon = name


def _capture(monkeypatch, result):
    built, loads, idle = [], [], []

    def generate(refs, **kwargs):
        built.append((list(refs), kwargs))
        return result

    monkeypatch.setattr(ui_actions.utils, "generate_auto_collage_cover", generate)
    monkeypatch.setattr(
        ui_actions.utils, "load_img", lambda widget, provider, cache_dir, size: loads.append((widget, provider, size))
    )
    monkeypatch.setattr(ui_actions.GLib, "idle_add", lambda fn, *args: idle.append((fn, args)))
    return built, loads, idle


def test_the_collage_is_built_by_the_image_worker(monkeypatch):
    built, loads, idle = _capture(monkeypatch, "/cache/playlist_covers/c.png")
    img = _Img()
    app = SimpleNamespace(cache_dir="/cache")

    ui_actions._load_collage_cover(app, img, ["a", "b"], 42, key_prefix="daily_mix_today", size=256)

    assert built == []  # nothing downloaded or decoded on the calling (main) thread
    [(widget, provider, size)] = loads
    assert widget is img and size == 42 and callable(provider)
    assert provider() == "/cache/playlist_covers/c.png"  # what load_img's worker runs
    [(refs, kwargs)] = built
    assert refs == ["a", "b"]
    assert kwargs == {
        "image_cache_dir": "/cache",
        "collage_cache_dir": os.path.join("/cache", "playlist_covers"),
        "key_prefix": "daily_mix_today",
        "size": 256,
    }
    assert idle == []


def test_a_failed_collage_falls_back_to_the_icon_on_the_main_loop(monkeypatch):
    built, loads, idle = _capture(monkeypatch, None)
    img = _Img()

    ui_actions._load_collage_cover(SimpleNamespace(cache_dir="/cache"), img, ["a"], 160, fallback_icon="audio-x-generic-symbolic")
    [(_widget, provider, _size)] = loads
    assert provider() is None
    assert img.icon is None  # not from the worker thread
    [(fn, args)] = idle
    fn(*args)
    assert img.icon == "audio-x-generic-symbolic" and img.pixel_size == 160


def test_no_covers_shows_the_icon_at_once(monkeypatch):
    built, loads, idle = _capture(monkeypatch, None)
    img = _Img()

    ui_actions._load_collage_cover(SimpleNamespace(cache_dir="/cache"), img, [], 160, fallback_icon="audio-x-generic-symbolic")

    assert img.icon == "audio-x-generic-symbolic" and img.pixel_size == 160
    assert loads == [] and built == []
