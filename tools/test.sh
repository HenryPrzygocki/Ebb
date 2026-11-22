#!/usr/bin/env bash
# Fork #14: run the tests headless, away from the desktop session (also `make test`).
#
# No display, no session bus (so no keyring, MPRIS or notifications), no PipeWire or Pulse
# socket, and a throwaway HOME with its own XDG dirs: no test reads or writes the real
# ~/.config/ebb, ~/.cache/ebb or ~/.local/share/ebb, and none can open a window or play a
# sound. The tests that need a display skip themselves.
#
# Python: $PYTHON, else .venv/bin/python, else python3. It needs pytest besides the system's
# PyGObject, GTK 4, libadwaita and tidalapi (Ebb's own dependencies), which a venv sees with
# --system-site-packages:
#   python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements-dev.txt
#
# Arguments go to pytest:   tools/test.sh -k credits   tools/test.sh tests/test_pager.py -v
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

py=${PYTHON:-}
if [[ -z $py ]]; then
    if [[ -x .venv/bin/python ]]; then py=.venv/bin/python; else py=python3; fi
fi
if ! "$py" -c "import pytest" 2>/dev/null; then
    echo "tools/test.sh: $py has no pytest. Set up a venv first:" >&2
    echo "  python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
    exit 2
fi

home=$(mktemp -d "${TMPDIR:-/tmp}/ebb-test.XXXXXX") || exit 2
trap 'rm -rf "$home"' EXIT
mkdir -p "$home/run" && chmod 700 "$home/run"

env -u WAYLAND_DISPLAY -u DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u NIRI_SOCKET \
    -u PIPEWIRE_REMOTE -u PULSE_SERVER \
    HOME="$home" XDG_RUNTIME_DIR="$home/run" \
    XDG_CONFIG_HOME="$home/.config" XDG_CACHE_HOME="$home/.cache" \
    XDG_DATA_HOME="$home/.local/share" XDG_STATE_HOME="$home/.local/state" \
    HIRESTI_LOG_FILE= EBB_LOG_FILE= \
    "$py" -m pytest -q -p no:cacheprovider "$@"
