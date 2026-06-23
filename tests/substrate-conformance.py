#!/usr/bin/env micropython
"""Conformance test for the esp32 substrate fakes against CONTRACT-esp32-v1.28.md.

This guards the fakes from drifting away from the captured SDK contract. It tests the
substrate in isolation (no library under test), so it can run anywhere the image runs.
If a fake stops "quacking" like the real esp32 v1.28.0 surface, this fails.
"""

import os
import sys

_S_IFDIR = 0x4000


def _dirname(path):
    return path.rsplit(os.sep, 1)[0] if os.sep in path else ""


def _join(a, b):
    if not a:
        return b
    return a.rstrip(os.sep) + os.sep + b


def _isdir(path):
    try:
        return (os.stat(path)[0] & _S_IFDIR) != 0
    except OSError:
        return False


_SUBSTRATE_DIR = _join(_dirname(_dirname(__file__)), "substrate")
if _isdir(_SUBSTRATE_DIR):
    sys.path.insert(0, _SUBSTRATE_DIR)

import network
import machine


def _run_case(name, fn):
    try:
        fn()
        print("PASS:", name)
    except Exception:
        print("FAIL:", name)
        raise


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    except Exception as other:
        raise AssertionError("expected %s, got %r" % (exc, other))
    raise AssertionError("expected %s, nothing raised" % exc)


# --- network constants -------------------------------------------------------
def case_network_constants():
    assert network.STA_IF == 0
    assert network.AP_IF == 1
    # happy-path codes: micropython-owned, stable
    assert network.STAT_IDLE == 1000
    assert network.STAT_CONNECTING == 1001
    assert network.STAT_GOT_IP == 1010
    # failure codes: ESP-IDF v5.5.1 wifi_err_reason_t (the IDF version MP v1.28.0 uses)
    assert network.STAT_BEACON_TIMEOUT == 200
    assert network.STAT_NO_AP_FOUND == 201
    assert network.STAT_WRONG_PASSWORD == 202     # WIFI_REASON_AUTH_FAIL
    assert network.STAT_ASSOC_FAIL == 203
    assert network.STAT_HANDSHAKE_TIMEOUT == 204
    # esp32 quirk: CONNECT_FAIL aliases ASSOC_FAIL (same int)
    assert network.STAT_CONNECT_FAIL == network.STAT_ASSOC_FAIL == 203


# --- WLAN identity + lifecycle ----------------------------------------------
def case_wlan_singleton_identity():
    network.reset_all()
    assert network.WLAN(network.STA_IF) is network.WLAN(network.STA_IF)
    assert network.WLAN(network.AP_IF) is network.WLAN(network.AP_IF)
    assert network.WLAN(network.STA_IF) is not network.WLAN(network.AP_IF)
    assert _raises(ValueError, lambda: network.WLAN(99))


def case_scan_requires_active_and_shape():
    network.reset_all()
    sta = network.WLAN(network.STA_IF)
    assert _raises(OSError, sta.scan)        # inactive -> OSError("STA must be active")
    sta.active(True)
    assert sta.active() is True
    sta.program_scan([{"ssid": "Net", "bssid": b"\x01\x02\x03\x04\x05\x06", "rssi": -55}])
    results = sta.scan()
    assert isinstance(results, list)
    row = results[0]
    assert len(row) == 6
    assert isinstance(row[0], bytes) and row[0] == b"Net"     # ssid is bytes
    assert isinstance(row[1], bytes) and len(row[1]) == 6     # bssid is bytes
    assert isinstance(row[2], int) and isinstance(row[3], int) and isinstance(row[4], int)
    assert row[5] is False                                    # esp32 hidden is always False


def case_connect_contract_and_spy():
    network.reset_all()
    sta = network.WLAN(network.STA_IF)
    assert sta.connect("Net", "pw", bssid=b"\x01\x02\x03\x04\x05\x06") is None
    assert sta.isconnected() is True
    assert sta.status() == network.STAT_GOT_IP
    assert sta.call_count("connect") == 1
    assert sta.last_call("connect").kwargs["bssid"] == b"\x01\x02\x03\x04\x05\x06"
    # bssid must be exactly 6 bytes
    assert _raises(ValueError, lambda: sta.connect("Net", bssid=b"\x01\x02"))


def case_status_contract():
    network.reset_all()
    sta = network.WLAN(network.STA_IF)
    assert sta.status() == network.STAT_IDLE          # no-arg STA -> int
    assert isinstance(sta.status("rssi"), int)        # 'rssi' -> int
    assert isinstance(sta.status("stations"), list)   # 'stations' -> list
    assert _raises(ValueError, lambda: sta.status("bogus"))
    assert network.WLAN(network.AP_IF).status() is None  # AP no-arg -> None
    # scripted failure status
    sta.reset()
    sta.fail_connect(network.STAT_NO_AP_FOUND)
    sta.connect("X")
    assert sta.isconnected() is False
    assert sta.status() == network.STAT_NO_AP_FOUND
    # connect_after: CONNECTING then GOT_IP
    sta.reset()
    sta.connect_after(2)
    sta.connect("X")
    assert sta.status() == network.STAT_CONNECTING
    assert sta.status() == network.STAT_CONNECTING
    assert sta.status() == network.STAT_GOT_IP


def case_ifconfig_and_config():
    network.reset_all()
    sta = network.WLAN(network.STA_IF)
    disc = sta.ifconfig()
    assert isinstance(disc, tuple) and len(disc) == 4
    assert disc[0] == "0.0.0.0"
    for part in disc:
        assert isinstance(part, str)
    sta.connect("Office", "pw")
    assert sta.ifconfig()[0] != "0.0.0.0"
    assert sta.config("ssid") == "Office"
    sta.config(essid="ap-name")
    assert sta.config("essid") == "ap-name"


# --- machine.Pin -------------------------------------------------------------
def case_pin_constants_and_io():
    machine.reset_all()
    assert machine.Pin.IN == 1
    assert machine.Pin.OUT == 3            # GPIO_MODE_INPUT_OUTPUT (readable)
    assert machine.Pin.OPEN_DRAIN == 7

    p = machine.Pin(5, machine.Pin.OUT)
    assert p.value() == 0 and isinstance(p.value(), int)   # value() -> int
    assert p.value(1) is None                              # value(x) -> None
    assert p.value() == 1
    assert p(0) is None and p() == 0                       # call form == value
    p.on()
    assert machine.Pin(5).value() == 1                     # OUT readable via fresh handle (same GPIO)
    assert p.toggle() is None and p.value() == 0
    assert p.call_count("on") == 1


def case_pin_external_input_and_isolation():
    machine.reset_all()
    button = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
    assert button.value() == 0
    button.set_external(1)
    assert button.value() == 1
    machine.reset_all()
    assert machine.Pin(0).value() == 0                     # reset_all clears GPIO state


def main():
    cases = [
        ("network_constants", case_network_constants),
        ("wlan_singleton_identity", case_wlan_singleton_identity),
        ("scan_requires_active_and_shape", case_scan_requires_active_and_shape),
        ("connect_contract_and_spy", case_connect_contract_and_spy),
        ("status_contract", case_status_contract),
        ("ifconfig_and_config", case_ifconfig_and_config),
        ("pin_constants_and_io", case_pin_constants_and_io),
        ("pin_external_input_and_isolation", case_pin_external_input_and_isolation),
    ]
    for name, fn in cases:
        _run_case(name, fn)
    print("substrate conformance complete")


if __name__ == "__main__":
    main()
