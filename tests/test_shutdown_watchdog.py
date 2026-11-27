"""Fork: quitting ends the process even when the audio output hangs its teardown.

A wedged headphone output held cleanup() for nearly two minutes after the window had closed;
the stale process kept Ebb's D-Bus name and every new launch timed out registering."""
import inspect
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

pytest.importorskip("gi")

from app import app_bootstrap  # noqa: E402


def test_the_watchdog_exits_once_the_grace_period_runs_out():
    fired = threading.Event()
    codes = []
    thread = app_bootstrap._arm_exit_watchdog(0.05, exit_fn=lambda code: (codes.append(code), fired.set()))
    assert thread.daemon  # never keeps the process alive by itself
    assert fired.wait(2)
    assert codes == [0]


def test_shutdown_arms_it_after_saving_settings_and_before_the_audio_teardown():
    src = inspect.getsource(app_bootstrap.do_shutdown)
    saved, armed, cleanup = (src.index(s) for s in ("self.save_settings()", "_arm_exit_watchdog()", "self.player.cleanup()"))
    assert saved < armed < cleanup
