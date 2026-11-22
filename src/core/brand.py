"""Fork: Ebb's name and identifiers, in one place.

Ebb is a modified version of hiresTI by yelanxin (GPL-3.0-or-later). Module, icon, setting and
environment-variable names stay upstream's so upstream changes keep merging cleanly; what users
and the desktop see (the name, app ID, D-Bus names, data directories, links) comes from here.
"""
import os

APP_NAME = "Ebb"
APP_ID = "io.github.henryprzygocki.Ebb"  # GApplication and Wayland app ID, desktop file, app icon
SLUG = "ebb"  # command, process name, data directories, MPRIS bus name
VERSION = "0.1.0"
TAGLINE = "A TIDAL player for Linux, built for lossless and hi-res audio"
MAINTAINER = "HenryPrzygocki"

PROJECT_URL = "https://github.com/HenryPrzygocki/Ebb"
ISSUES_URL = PROJECT_URL + "/issues"
RELEASES_URL = PROJECT_URL + "/releases"
RELEASES_API_URL = "https://api.github.com/repos/HenryPrzygocki/Ebb/releases?per_page=20"

UPSTREAM_NAME = "hiresTI"
UPSTREAM_AUTHOR = "yelanxin"
UPSTREAM_URL = "https://github.com/yelanxin/hiresTI"
UPSTREAM_SPONSOR_URL = "https://github.com/sponsors/yelanxin"
LEGACY_SLUG = "hiresti"  # upstream's data directories; utils.paths moves them over once


def upstream_version() -> str:
    """The hiresTI release this build is based on (version.txt is upstream's, left as it ships)."""
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        try:
            with open(os.path.join(root, "version.txt"), encoding="utf-8") as fh:
                text = fh.read().strip()
        except OSError:
            continue
        if text:
            return text
    return ""
