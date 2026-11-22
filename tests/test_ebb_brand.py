"""Fork: the rename to Ebb. hiresTI's data moves over once; its identifiers and feeds stay out."""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core import brand  # noqa: E402
from utils import paths  # noqa: E402


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_CACHE_HOME", "cache"),
                     ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(var, str(tmp_path / sub))
    monkeypatch.setattr(paths, "_checked", set())
    return tmp_path


def test_first_start_moves_the_hiresti_login_and_settings_over(xdg):
    old = xdg / "config" / "hiresti"
    old.mkdir()
    (old / "hiresti_token.json").write_text("{}")
    (old / "settings.json").write_text('{"volume": 40}')

    assert paths.get_config_dir() == str(xdg / "config" / "ebb")
    assert (xdg / "config" / "ebb" / "hiresti_token.json").read_text() == "{}"
    assert os.path.islink(old) and os.readlink(old) == "ebb"
    assert (old / "settings.json").read_text() == '{"volume": 40}'  # the old path still works


def test_history_caches_playlists_and_logs_move_too(xdg):
    for sub in ("cache", "data", "state"):
        (xdg / sub / "hiresti").mkdir()
        (xdg / sub / "hiresti" / "marker").write_text(sub)
    assert paths.get_cache_dir() == str(xdg / "cache" / "ebb")
    assert paths.get_data_dir() == str(xdg / "data" / "ebb")
    assert paths.get_state_dir() == str(xdg / "state" / "ebb")
    for sub in ("cache", "data", "state"):
        assert (xdg / sub / "ebb" / "marker").read_text() == sub


def test_an_existing_ebb_directory_is_never_overwritten(xdg):
    (xdg / "config" / "hiresti").mkdir()
    (xdg / "config" / "hiresti" / "settings.json").write_text("old")
    (xdg / "config" / "ebb").mkdir()
    (xdg / "config" / "ebb" / "settings.json").write_text("new")
    paths.get_config_dir()
    assert (xdg / "config" / "ebb" / "settings.json").read_text() == "new"
    assert (xdg / "config" / "hiresti" / "settings.json").read_text() == "old"
    assert not os.path.islink(xdg / "config" / "hiresti")


def test_a_fresh_install_creates_nothing(xdg):
    assert paths.get_config_dir() == str(xdg / "config" / "ebb")
    assert not os.path.lexists(xdg / "config" / "ebb")
    assert not os.path.lexists(xdg / "config" / "hiresti")


def test_each_directory_is_checked_once_per_run(xdg, monkeypatch):
    (xdg / "config" / "hiresti").mkdir()
    moves = []
    monkeypatch.setattr(paths.os, "rename", lambda a, _b: moves.append(a))
    monkeypatch.setattr(paths.os, "symlink", lambda *_a: None)
    paths.get_config_dir()
    paths.get_config_dir()
    assert len(moves) == 1


def test_without_xdg_variables_the_home_fallbacks_are_ebb(monkeypatch, tmp_path):
    for var in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(paths, "_checked", set())
    assert paths.get_config_dir() == str(tmp_path / ".config" / "ebb")
    assert paths.get_state_dir() == str(tmp_path / ".local" / "state" / "ebb")


def test_cached_hiresti_releases_are_not_offered_as_updates():
    pytest.importorskip("gi")
    from services import update_check

    stale = {"latest_version": "1.9.13", "last_checked_at": 1}  # from hiresTI, in migrated settings
    app = SimpleNamespace(app_version=brand.VERSION, settings={"update_check": stale})
    update_check.init_update_check_state(app)
    assert app._update_check_state["update_available"] is False
    assert app._update_check_state["latest_version"] == ""

    ours = dict(stale, latest_version="99.0.0", source=update_check._RELEASES_URL)
    app = SimpleNamespace(app_version=brand.VERSION, settings={"update_check": ours})
    update_check.init_update_check_state(app)
    assert app._update_check_state["update_available"] is True


def test_identifiers_are_valid_and_not_hiresti_s():
    gi = pytest.importorskip("gi")
    from gi.repository import Gio

    assert Gio.Application.id_is_valid(brand.APP_ID)
    from services import mpris

    assert Gio.dbus_is_name(mpris.BUS_NAME) and mpris.BUS_NAME == "org.mpris.MediaPlayer2.ebb"
    assert "hiresti" not in (brand.APP_ID + brand.SLUG + brand.RELEASES_API_URL).lower()
    assert gi is not None


def test_upstream_version_names_the_hiresti_release():
    with open(os.path.join(os.path.dirname(__file__), "..", "version.txt"), encoding="utf-8") as fh:
        assert brand.upstream_version() == fh.read().strip()
