"""Re-attach the PipeWire output when the user's sink node is re-created.

Fork patch. A USB DAC/headset that resets (drops off the bus and re-enumerates
a few seconds later; the Bose QC Ultra 2 over USB-C does this regularly) comes
back as a *new* PipeWire node under the same node name. HiresTI's pipewire-alsa
PCM does not follow it: the stream keeps "playing" and delivers silence until
the user re-picks the device by hand. Re-picking (a fresh ``set_output``) is the
recovery known to work, so this module automates exactly that and nothing else.

Mechanism: one long-lived ``pactl subscribe`` child (event-driven, no polling).
A burst of ``new``/``remove`` events on sinks is debounced, then
``pactl list short sinks`` gives node name -> index. pipewire-pulse indices are
PipeWire object serials, which are never reused, so "same name, different
index" means the node was re-created even when the absent phase was too short
to observe. When the preferred sink appears or is re-created, the callback runs
on the GTK main thread.
"""

from __future__ import annotations

import atexit
import logging
import re
import subprocess
import threading

from gi.repository import GLib

logger = logging.getLogger(__name__)

_SINK_EVENT_RE = re.compile(r"^Event '(?:new|remove)' on sink #\d+")
_DEBOUNCE_S = 0.4
_RESTART_BACKOFF_S = 5.0


def parse_short_sinks(text):
    """Parse ``pactl list short sinks`` output into {node name: index}."""
    sinks = {}
    for line in str(text or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0].strip().isdigit() and parts[1].strip():
            sinks[parts[1].strip()] = int(parts[0])
    return sinks


def list_sink_indices():
    """Current {node name: index}, or None when pactl is unavailable or fails."""
    try:
        out = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_short_sinks(out)


def sink_needs_rebind(name, before, after):
    """True if sink ``name`` appeared, or was re-created, between two snapshots."""
    if not name:
        return False
    new_index = after.get(name)
    return new_index is not None and new_index != before.get(name)


class PipeWireSinkWatch:
    """Watch PipeWire sinks; call ``on_sink_returned(name)`` when the preferred one comes back.

    ``preferred_sink()`` is evaluated at event time and returns the node name to keep
    bound, or None when there is nothing to watch (default sink, other driver).
    """

    def __init__(self, preferred_sink, on_sink_returned):
        self._preferred_sink = preferred_sink
        self._on_sink_returned = on_sink_returned
        self._lock = threading.Lock()
        self._snapshot = {}
        self._timer = None
        self._proc = None
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._run, name="hiresti-pw-sink-watch", daemon=True).start()
        atexit.register(self.stop)

    def stop(self):
        self._stop.set()
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _run(self):
        baseline = list_sink_indices()
        with self._lock:
            self._snapshot = baseline or {}
        while not self._stop.is_set():
            try:
                self._proc = subprocess.Popen(
                    ["pactl", "subscribe"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                logger.warning("PipeWire sink watch disabled: cannot run pactl (%s)", exc)
                return
            logger.info("PipeWire sink watch running (pactl pid %s)", self._proc.pid)
            for line in self._proc.stdout:
                if _SINK_EVENT_RE.match(line):
                    self._schedule_check()
            rc = self._proc.wait()
            if self._stop.wait(_RESTART_BACKOFF_S):
                return
            logger.info("pactl subscribe exited (rc=%s); restarting sink watch", rc)
            # The sink may have been re-created while we were not subscribed.
            self._check()

    def _schedule_check(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_S, self._check)
            self._timer.daemon = True
            self._timer.start()

    def _check(self):
        after = list_sink_indices()
        if after is None:
            return
        with self._lock:
            before, self._snapshot = self._snapshot, after
        name = self._preferred_sink()
        if not sink_needs_rebind(name, before, after):
            return
        logger.info(
            "PipeWire sink %s appeared/re-created (index %s -> %s); re-attaching output",
            name,
            before.get(name),
            after.get(name),
        )
        GLib.idle_add(self._fire, name)

    def _fire(self, name):
        try:
            self._on_sink_returned(name)
        except Exception:
            logger.exception("PipeWire sink re-attach failed")
        return False
