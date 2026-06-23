#!/usr/bin/env micropython
"""Deterministic, device-status focused regression checks for micropython-wifimanager.

These run against the canonical esp32 substrate fakes in ../substrate (network,
machine) plus small webrepl/logging stubs. The test never defines a mock: it programs
the substrate (program_scan / fail_connect / connect_after) and spies on it
(call_count / last_call), then exercises real WifiManager logic with no radios.
"""

import json
import os
import sys

try:
    import ubinascii as _b64
except ImportError:
    import binascii as _b64


_MISSING_CONFIG_PATH = "/tmp/wifimanager-missing.json"
_REGRESSION_CONFIG_PATH = "/tmp/wifimanager-regression.json"

_S_IFDIR = 0x4000


def _dirname(path):
    if os.sep in path:
        return path.rsplit(os.sep, 1)[0]
    return ""


def _join(*parts):
    out = ""
    for part in parts:
        if not part:
            continue
        if not out:
            out = part
        else:
            out = out.rstrip(os.sep) + os.sep + part.lstrip(os.sep)
    return out


def _stat_mode(path):
    try:
        return os.stat(path)[0]
    except OSError:
        return None


def _isdir(path):
    mode = _stat_mode(path)
    return mode is not None and (mode & _S_IFDIR) != 0


def _exists(path):
    return _stat_mode(path) is not None


_SCRIPT_DIR = _dirname(__file__)


def _request(method, path, password, body=""):
    auth_blob = _b64.b2a_base64(("admin:%s" % password).encode("utf-8")).decode("utf-8").strip()
    headers = [
        "%s %s HTTP/1.1" % (method, path),
        "Authorization: Basic %s" % auth_blob,
        "Content-Length: %d" % len(body),
        "",
        body,
    ]
    return "\r\n".join(headers)


def _run_case(name, fn):
    try:
        fn()
        print("PASS:", name)
    except Exception:
        print("FAIL:", name)
        raise


def _install_substrate():
    """Install the esp32 substrate (network, machine) + stubs (webrepl, logging) as
    importable modules, reset to defaults. Substrate dir is inserted last so it wins."""
    repo_root = _dirname(_SCRIPT_DIR)
    stubs_dir = _join(_SCRIPT_DIR, "stubs")
    substrate_dir = _join(repo_root, "substrate")
    for path in (stubs_dir, substrate_dir):
        if _isdir(path):
            sys.path.insert(0, path)

    import network
    import machine
    import webrepl  # noqa: F401
    import logging  # noqa: F401
    sys.modules["network"] = network
    sys.modules["machine"] = machine
    sys.modules["webrepl"] = webrepl
    sys.modules["logging"] = logging

    network.reset_all()
    machine.reset_all()
    return network, machine


def _load_wifi_manager():
    target = os.getenv("WIFIMANAGER_SRC")
    if not target:
        raise RuntimeError("Set WIFIMANAGER_SRC to a checked-out micropython-wifimanager path")
    if not _isdir(target):
        raise RuntimeError("WIFIMANAGER_SRC does not exist: %s" % target)

    sys.path.insert(0, target)
    network, _machine = _install_substrate()

    from wifi_manager.wifi_manager import WifiManager

    _reset_manager_state(WifiManager)
    return WifiManager, network


def _reset_manager_state(manager):
    manager._connection_callbacks = []
    manager._last_connection_state = None
    manager.webrepl_triggered = False
    manager._config_server_enabled = False
    manager._config_server_password = "micropython"
    manager.config_file = _REGRESSION_CONFIG_PATH
    manager._ap_start_policy = "never"


def _always_true(*_args, **_kwargs):
    return True


def _always_false(*_args, **_kwargs):
    return False


def case_connectivity_preference_and_scan_order():
    manager, network = _load_wifi_manager()
    manager.preferred_networks = [
        {"ssid": "Flat_AP", "password": "a"},
        {"ssid": "Strong_AP", "password": "b"},
    ]
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.program_scan([
        {"ssid": "Strong_AP", "bssid": b"\x01\x02\x03\x04\x05\x06", "rssi": -40},
        {"ssid": "Flat_AP", "bssid": b"\x01\x02\x03\x04\x05\x07", "rssi": -90},
        {"ssid": "Guest", "bssid": b"\x01\x02\x03\x04\x05\x08", "rssi": -20},
    ])

    ordered = manager._scan_available_networks()
    assert [item["ssid"] for item in ordered[:3]] == ["Guest", "Strong_AP", "Flat_AP"]

    candidates = manager._build_connection_candidates(ordered)
    assert len(candidates) == 2
    assert candidates[0]["ssid"] == "Flat_AP"
    assert candidates[1]["ssid"] == "Strong_AP"
    assert candidates[1]["bssid"] == b"\x01\x02\x03\x04\x05\x06"


def case_status_edge_callbacks_emit_only_on_state_changes():
    manager, network = _load_wifi_manager()
    sta = network.WLAN(network.STA_IF)
    events = []

    def callback(event, **kwargs):
        events.append((event, kwargs))

    manager.on_connection_change(callback)

    # Starts disconnected -> first poll emits a single "disconnected" transition.
    manager._check_and_notify_connection_state()
    assert len(events) == 1
    assert events[0][0] == "disconnected"
    assert events[0][1] == {}

    # Script a successful association to "Office".
    sta.active(True)
    sta.program_scan([{"ssid": "Office", "bssid": b"\x0a\x0b\x0c\x0d\x0e\x0f", "rssi": -45}])
    sta.connect("Office", "pw")
    manager._check_and_notify_connection_state()
    assert len(events) == 2
    assert events[1][0] == "connected"
    assert events[1][1]["ssid"] == "Office"

    # No state change -> no duplicate transition.
    manager._check_and_notify_connection_state()
    assert len(events) == 2, "should not emit duplicate connected transition"


def case_fallback_ap_relies_on_network_status():
    manager, network = _load_wifi_manager()
    sta = network.WLAN(network.STA_IF)
    manager._ap_start_policy = "fallback"

    # Connected (GOT_IP) -> no AP wanted.
    sta.connect("Home", "pw")
    assert manager.wants_accesspoint() is False

    # No AP found -> AP wanted.
    sta.reset()
    sta.fail_connect(network.STAT_NO_AP_FOUND)
    sta.connect("Home", "pw")
    assert manager.wants_accesspoint() is True

    # Still connecting -> AP wanted.
    sta.reset()
    sta.connect_after(3)
    sta.connect("Home", "pw")
    assert manager.wants_accesspoint() is True


def case_connect_candidates_uses_requested_bssid_and_notifies():
    manager, network = _load_wifi_manager()
    sta = network.WLAN(network.STA_IF)
    events = []
    manager.on_connection_change(lambda event, **kwargs: events.append((event, kwargs)))
    manager.preferred_networks = [{"ssid": "Flat_AP", "password": "alpha"}]

    sta.active(True)
    sta.program_scan([
        {"ssid": "Flat_AP", "bssid": b"\x10\x11\x12\x13\x14\x15", "rssi": -30},
        {"ssid": "Flat_AP", "bssid": b"\x01\x02\x03\x04\x05\x06", "rssi": -70},
    ])

    available = manager._scan_available_networks()
    candidates = manager._build_connection_candidates(available)
    assert candidates[0]["bssid"] == b"\x10\x11\x12\x13\x14\x15"
    assert candidates[1]["bssid"] == b"\x01\x02\x03\x04\x05\x06"

    connected = manager._connect_candidates(candidates)
    assert connected is True
    assert len(events) == 1
    assert events[0][0] == "connected"

    # Spy on the real connect() call: the strongest BSSID was requested.
    assert sta.call_count("connect") == 1
    assert sta.last_call("connect").kwargs["bssid"] == b"\x10\x11\x12\x13\x14\x15"


def case_pin_substrate_readback_and_spy():
    _network, machine = _install_substrate()

    led = machine.Pin(2, machine.Pin.OUT)
    led.on()
    assert machine.Pin(2).value() == 1     # OUT is readable on esp32; same GPIO via new handle
    assert isinstance(led.value(), int)
    led.off()
    assert led.value() == 0

    button = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
    button.set_external(1)
    assert button.value() == 1

    assert led.call_count("on") == 1
    assert led.call_count("off") == 1


def case_async_manage_connects_when_ap_available():
    manager, network = _load_wifi_manager()
    from wifi_manager import wifi_manager as wm_module
    import aiotest

    # manage() -> setup_network() reloads config each turn, so the networks must come
    # from the config file (not a poked attribute, which _load_config would overwrite).
    async_config = "/tmp/wifimanager-async.json"
    with open(async_config, "w") as handle:
        handle.write(json.dumps({
            "schema": 2,
            "known_networks": [{"ssid": "Home", "password": "pw"}],
            "access_point": {"config": {"essid": "AP"}, "start_policy": "never"},
            "config_server": {"enabled": False},
        }))
    manager.config_file = async_config

    events = []
    manager.on_connection_change(lambda event, **kwargs: events.append((event, kwargs)))

    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    sta.program_scan([{"ssid": "Home", "bssid": b"\x0a\x0b\x0c\x0d\x0e\x0f", "rssi": -50}])
    assert sta.isconnected() is False

    # Drive the real async manage() loop for a few turns with no wall-clock waiting.
    turns = aiotest.run_iterations(manager.manage, 4, wm_module.asyncio)
    assert turns == 4

    # The loop saw "not connected", ran setup_network(), and converged to connected.
    assert sta.isconnected() is True
    assert sta.call_count("connect") >= 1
    assert [e[0] for e in events][:2] == ["disconnected", "connected"]


def case_config_masking_is_stable_on_post():
    manager, _ = _load_wifi_manager()
    with open(_REGRESSION_CONFIG_PATH, "w") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": 2,
                    "known_networks": [
                        {"ssid": "Home", "password": "home-pass", "enables_webrepl": True},
                        {"ssid": "Office", "password": "office-pass", "enables_webrepl": False},
                    ],
                    "access_point": {
                        "config": {"essid": "Micropython-AP", "channel": 11, "password": "change-me"},
                        "enables_webrepl": False,
                        "start_policy": "always",
                    },
                    "config_server": {"enabled": False, "password": "secret"},
                }
            )
        )

    original_setup_network = manager.setup_network
    manager.config_file = _REGRESSION_CONFIG_PATH
    manager._config_server_password = "secret"
    manager.setup_network = _always_true

    try:
        payload = json.dumps(
            {
                "schema": 2,
                "known_networks": [
                    {"ssid": "Home", "password": "***", "enables_webrepl": True},
                    {"ssid": "Office", "password": "office-new"},
                ],
                "access_point": {
                    "config": {"essid": "Micropython-AP", "channel": 6, "password": "***"},
                    "enables_webrepl": False,
                    "start_policy": "always",
                },
            }
        )
        response = manager._handle_config_request(_request("POST", "/config", "secret", body=payload))
        assert "200 OK" in response

        with open(_REGRESSION_CONFIG_PATH, "r") as handle:
            written = json.load(handle)
        assert written["known_networks"][0]["password"] == "home-pass"
        assert written["known_networks"][1]["password"] == "office-new"
        assert written["access_point"]["config"]["password"] == "change-me"
    finally:
        manager.setup_network = original_setup_network


def case_missing_config_triggers_recovery_ap():
    manager, _ = _load_wifi_manager()
    manager.config_file = _MISSING_CONFIG_PATH
    if _exists(_MISSING_CONFIG_PATH):
        os.unlink(_MISSING_CONFIG_PATH)

    original_start_config_server = manager.start_config_server
    manager.start_config_server = _always_false

    try:
        loaded = manager._load_config()
        assert loaded is False
        assert manager.ap_config["config"]["essid"] == "MicroPython-AP"
        assert manager.ap_config["start_policy"] == "always"
    finally:
        manager.start_config_server = original_start_config_server


def main():
    cases = [
        ("connectivity_preference_and_scan_order", case_connectivity_preference_and_scan_order),
        ("status_edge_callbacks_emit_only_on_state_changes", case_status_edge_callbacks_emit_only_on_state_changes),
        ("fallback_ap_relies_on_network_status", case_fallback_ap_relies_on_network_status),
        ("connect_candidates_uses_requested_bssid", case_connect_candidates_uses_requested_bssid_and_notifies),
        ("pin_substrate_readback_and_spy", case_pin_substrate_readback_and_spy),
        ("async_manage_connects_when_ap_available", case_async_manage_connects_when_ap_available),
        ("config_masking_is_stable_on_post", case_config_masking_is_stable_on_post),
        ("missing_config_triggers_recovery_ap", case_missing_config_triggers_recovery_ap),
    ]

    for name, fn in cases:
        _run_case(name, fn)

    print("wifi-manager deterministic examples complete")


if __name__ == "__main__":
    main()
