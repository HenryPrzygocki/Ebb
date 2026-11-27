import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from actions import audio_settings_actions
from actions import pipewire_sink_watch as psw

BOSE = "alsa_output.usb-Bose_Corporation_Bose_QC_Ultra_2_HP-00.analog-stereo"
SPEAKERS = "alsa_output.pci-0000_04_00.6.analog-stereo"
SHORT = (
    f"65\t{BOSE}\tPipeWire\ts24le 2ch 48000Hz\tRUNNING\n"
    "70\tsilence-sink\tPipeWire\tfloat32le 2ch 48000Hz\tSUSPENDED\n"
)


def _driver_dd(label):
    return SimpleNamespace(get_selected_item=lambda: SimpleNamespace(get_string=lambda: label))


def test_parse_short_sinks_maps_node_name_to_index():
    assert psw.parse_short_sinks(SHORT) == {BOSE: 65, "silence-sink": 70}
    assert psw.parse_short_sinks("") == {}
    assert psw.parse_short_sinks("garbage line\n") == {}


def test_sink_needs_rebind_on_recreation_and_on_return():
    # Same node name, new serial: re-created even though it was never seen absent.
    assert psw.sink_needs_rebind(BOSE, {BOSE: 65}, {BOSE: 81})
    # Came back after being absent.
    assert psw.sink_needs_rebind(BOSE, {}, {BOSE: 81})


def test_sink_needs_rebind_ignores_unchanged_absent_and_unset():
    assert not psw.sink_needs_rebind(BOSE, {BOSE: 65}, {BOSE: 65})
    assert not psw.sink_needs_rebind(BOSE, {BOSE: 65}, {})
    assert not psw.sink_needs_rebind(None, {}, {BOSE: 65})


def test_watch_check_fires_once_per_recreation(monkeypatch):
    snapshots = iter([{BOSE: 81, "silence-sink": 70}, {BOSE: 81, "silence-sink": 70}])
    monkeypatch.setattr(psw, "list_sink_indices", lambda: next(snapshots))
    monkeypatch.setattr(psw, "GLib", SimpleNamespace(idle_add=lambda fn, *a: fn(*a)))
    fired = []
    watch = psw.PipeWireSinkWatch(lambda: BOSE, fired.append)
    watch._snapshot = {BOSE: 65, "silence-sink": 70}
    watch._check()  # 65 -> 81: re-created
    watch._check()  # unchanged
    assert fired == [BOSE]


def test_watch_check_ignores_other_sinks(monkeypatch):
    monkeypatch.setattr(psw, "list_sink_indices", lambda: {BOSE: 65, "silence-sink": 99})
    monkeypatch.setattr(psw, "GLib", SimpleNamespace(idle_add=lambda fn, *a: fn(*a)))
    fired = []
    watch = psw.PipeWireSinkWatch(lambda: BOSE, fired.append)
    watch._snapshot = {BOSE: 65, "silence-sink": 70}
    watch._check()
    assert fired == []


def test_preferred_sink_only_for_a_pinned_pipewire_node():
    pref = audio_settings_actions._pipewire_preferred_sink
    assert pref(SimpleNamespace(settings={"driver": "PipeWire", "device_id": BOSE})) == BOSE
    assert pref(SimpleNamespace(settings={"driver": "PipeWire", "device_id": "pipewire"})) is None
    assert pref(SimpleNamespace(settings={"driver": "PipeWire", "device_id": ""})) is None
    assert pref(SimpleNamespace(settings={"driver": "ALSA（mmap）", "device_id": "hw:2,0"})) is None


def test_reattach_rebinds_saved_sink_and_clears_disconnect_memory(monkeypatch):
    calls = []
    for fn in (
        "_refresh_devices_for_current_driver_ui_only",
        "update_output_status_ui",
        "_stop_output_hotplug_watch",
    ):
        monkeypatch.setattr(audio_settings_actions, fn, lambda *a, _fn=fn, **k: calls.append(_fn))
    player = SimpleNamespace(
        output_state="active",
        set_output=lambda drv, dev: calls.append(("set_output", drv, dev)) or True,
    )
    app = SimpleNamespace(
        settings={"driver": "PipeWire", "device_id": BOSE, "device": "Bose QC Ultra 2 HP (USB) Analog Stereo"},
        player=player,
        driver_dd=_driver_dd("PipeWire"),
        current_device_list=[{"name": "Bose QC Ultra 2 (USB)", "device_id": BOSE}],
        _last_disconnected_device_name="Bose QC Ultra 2 (USB)",
        _last_disconnected_driver="PipeWire",
        show_output_notice=lambda *a: calls.append(("notice",) + a),
    )
    audio_settings_actions._reattach_pipewire_sink(app, BOSE)
    assert ("set_output", "PipeWire", BOSE) in calls
    assert "_stop_output_hotplug_watch" in calls
    assert app._last_disconnected_device_name == ""
    assert ("notice", "Output re-attached: Bose QC Ultra 2 (USB)", "ok", 2600) in calls


def test_reattach_ignores_stale_event_after_user_switched_device():
    def _boom(*_a):
        raise AssertionError("must not rebind")

    app = SimpleNamespace(
        settings={"driver": "PipeWire", "device_id": SPEAKERS},
        player=SimpleNamespace(output_state="active", set_output=_boom),
        driver_dd=_driver_dd("PipeWire"),
    )
    audio_settings_actions._reattach_pipewire_sink(app, BOSE)


def test_hotplug_name_path_defers_to_sink_watch_only_when_it_runs():
    owns = audio_settings_actions._pw_sink_watch_owns
    app = SimpleNamespace(settings={"driver": "PipeWire", "device_id": BOSE})
    assert not owns(app, "PipeWire")  # watch not started: legacy path stays in charge
    app._pw_sink_watch = object()
    assert owns(app, "PipeWire")
    assert not owns(app, "ALSA（mmap）")


# Fork #5, 2026-11-27: on "Default PipeWire Sink" the watch did nothing. The Bose reset twice
# while Ebb was paused; resuming played into the dead node, silently.

def test_on_the_default_sink_the_watch_follows_whatever_node_is_default(monkeypatch):
    monkeypatch.setattr(audio_settings_actions, "_pipewire_default_sink_name", lambda: BOSE)
    watched = audio_settings_actions._pipewire_watched_sink
    assert watched(SimpleNamespace(settings={"driver": "PipeWire", "device_id": "pipewire"})) == BOSE
    assert watched(SimpleNamespace(settings={"driver": "PipeWire", "device_id": ""})) == BOSE
    assert watched(SimpleNamespace(settings={"driver": "PipeWire", "device_id": SPEAKERS})) == SPEAKERS
    assert watched(SimpleNamespace(settings={"driver": "ALSA（mmap）", "device_id": "hw:2,0"})) is None


def test_a_default_sink_that_drops_and_returns_fires_the_re_attach(monkeypatch):
    monkeypatch.setattr(psw, "GLib", SimpleNamespace(idle_add=lambda fn, *a: fn(*a)))
    fired = []
    default = {"now": SPEAKERS}  # during the drop WirePlumber falls back to the speakers
    watch = psw.PipeWireSinkWatch(lambda: default["now"], fired.append)
    watch._snapshot = {BOSE: 65, SPEAKERS: 40}
    monkeypatch.setattr(psw, "list_sink_indices", lambda: {SPEAKERS: 40})
    watch._check()
    assert fired == []
    default["now"] = BOSE
    monkeypatch.setattr(psw, "list_sink_indices", lambda: {BOSE: 81, SPEAKERS: 40})
    watch._check()
    assert fired == [BOSE]


def test_re_attach_on_the_default_sink_re_applies_default_and_names_the_device(monkeypatch):
    calls = []
    for fn in ("_refresh_devices_for_current_driver_ui_only", "update_output_status_ui", "_stop_output_hotplug_watch"):
        monkeypatch.setattr(audio_settings_actions, fn, lambda *a, _fn=fn, **k: calls.append(_fn))
    app = SimpleNamespace(
        settings={"driver": "PipeWire", "device_id": "pipewire", "device": "Default PipeWire Sink"},
        player=SimpleNamespace(output_state="active",
                               set_output=lambda drv, dev: calls.append(("set_output", drv, dev)) or True),
        driver_dd=_driver_dd("PipeWire"),
        current_device_list=[{"name": "Default PipeWire Sink", "device_id": "pipewire"},
                             {"name": "Bose QC Ultra 2 (USB)", "device_id": BOSE}],
        show_output_notice=lambda *a: calls.append(("notice",) + a),
    )
    audio_settings_actions._reattach_pipewire_sink(app, BOSE)
    assert ("set_output", "PipeWire", "pipewire") in calls
    assert ("notice", "Output re-attached: Bose QC Ultra 2 (USB)", "ok", 2600) in calls
