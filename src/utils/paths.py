"""
Common path utilities for cache, config, and data directories.
"""
import logging
import os

from core import brand

logger = logging.getLogger(__name__)
_checked = set()


def _adopt_legacy_dir(path: str) -> str:
    """Fork: the first time Ebb asks for one of its directories, move hiresTI's over (login,
    settings, history, playlists, caches) and leave a symlink at the old name, so nothing is
    lost and anything still pointed at the old path keeps working."""
    if path in _checked:
        return path
    _checked.add(path)
    parent, name = os.path.split(path)
    legacy = os.path.join(parent, brand.LEGACY_SLUG)
    if name != brand.SLUG or os.path.lexists(path) or os.path.islink(legacy) or not os.path.isdir(legacy):
        return path
    try:
        os.rename(legacy, path)
    except OSError as exc:
        logger.warning("Could not move %s to %s: %s", legacy, path, exc)
        return path
    try:
        os.symlink(brand.SLUG, legacy)
    except OSError as exc:
        logger.warning("Moved %s to %s, but could not leave a symlink: %s", legacy, path, exc)
    logger.info("Moved %s to %s", legacy, path)
    return path


def _get_xdg_dir(env_var: str, fallback: str) -> str:
    """Get XDG-compatible directory with fallback."""
    xdg = os.environ.get(env_var)
    if xdg:
        return _adopt_legacy_dir(os.path.join(xdg, brand.SLUG))
    return _adopt_legacy_dir(os.path.expanduser(fallback))


def get_cache_dir() -> str:
    """
    Get cache directory for app data.
    Supports XDG_CACHE_HOME (automatically set by Flatpak).
    """
    return _get_xdg_dir('XDG_CACHE_HOME', '~/.cache/ebb')


def get_config_dir() -> str:
    """
    Get config directory for app settings.
    Supports XDG_CONFIG_HOME (automatically set by Flatpak).
    """
    return _get_xdg_dir('XDG_CONFIG_HOME', '~/.config/ebb')


def get_data_dir() -> str:
    """
    Get data directory for app data.
    Supports XDG_DATA_HOME (automatically set by Flatpak).
    """
    return _get_xdg_dir('XDG_DATA_HOME', '~/.local/share/ebb')


def get_state_dir() -> str:
    """Fork: logs live here ($XDG_STATE_HOME/ebb)."""
    return _get_xdg_dir('XDG_STATE_HOME', '~/.local/state/ebb')
