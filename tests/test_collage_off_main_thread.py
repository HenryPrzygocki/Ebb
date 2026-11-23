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


def test_a_collage_is_published_in_one_rename(tmp_path, monkeypatch):
    # Another image worker may test os.path.exists(out_path) while this one is still writing.
    from utils import helpers

    covers = []
    for name, rgb in (("a", (255, 0, 0)), ("b", (0, 0, 255))):
        surface = helpers.cairo.ImageSurface(helpers.cairo.FORMAT_ARGB32, 8, 8)
        cr = helpers.cairo.Context(surface)
        cr.set_source_rgb(*(c / 255 for c in rgb))
        cr.paint()
        path = tmp_path / f"{name}.png"
        surface.write_to_png(str(path))
        covers.append(str(path))
    seen = []
    real_replace = helpers.os.replace
    monkeypatch.setattr(helpers.os, "replace", lambda src, dst: (seen.append((src, dst)), real_replace(src, dst))[1])

    out = helpers.generate_auto_collage_cover(covers, str(tmp_path), str(tmp_path / "collages"), key_prefix="t", size=32)

    [(src, dst)] = seen
    assert dst == out and os.path.basename(src).startswith(".collage-")
    assert os.path.getsize(out) > 0
    assert sorted(os.listdir(tmp_path / "collages")) == [os.path.basename(out)]  # no temp file left
