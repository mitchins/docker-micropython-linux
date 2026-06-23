"""Contract-accurate fake of the esp32 ``network`` module (MicroPython v1.28.0).

See CONTRACT-esp32-v1.28.md for the captured contract. This is a *scriptable fake*,
not an emulator: it guarantees the device-facing shape (signatures, return types,
exceptions, constants, singleton identity) and lets the test drive behaviour through
the control surface (``program_scan`` / ``fail_connect`` / ``connect_after`` / spy).
The library under test imports this as ``network`` and cannot tell the difference.
"""

# --- contract constants (esp32 v1.28.0) -------------------------------------
STA_IF = 0
AP_IF = 1

# happy-path: micropython-owned, stable across versions
STAT_IDLE = 1000
STAT_CONNECTING = 1001
STAT_GOT_IP = 1010

# failure codes: ESP-IDF wifi_err_reason_t, captured from esp-idf v5.5.1 (the IDF
# version MicroPython v1.28.0 recommends). CONNECT_FAIL aliases ASSOC_FAIL on esp32.
STAT_BEACON_TIMEOUT = 200
STAT_NO_AP_FOUND = 201
STAT_WRONG_PASSWORD = 202
STAT_ASSOC_FAIL = 203
STAT_CONNECT_FAIL = 203
STAT_HANDSHAKE_TIMEOUT = 204

_DISCONNECTED_IFCONFIG = ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")
_CONNECTED_IFCONFIG = ("192.168.4.2", "255.255.255.0", "192.168.4.1", "8.8.8.8")
_NO_BSSID = b"\x00\x00\x00\x00\x00\x00"


def _as_bytes(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


class _Call:
    def __init__(self, name, args, kwargs):
        self.name = name
        self.args = args
        self.kwargs = kwargs

    def __repr__(self):
        return "Call(%s, %r, %r)" % (self.name, self.args, self.kwargs)


class WLAN:
    """Singleton per interface, matching esp32 ``make_new``."""

    _instances = {}

    def __new__(cls, interface=STA_IF):
        if interface not in (STA_IF, AP_IF):
            raise ValueError("invalid WLAN interface identifier")
        inst = cls._instances.get(interface)
        if inst is None:
            inst = object.__new__(cls)
            inst.interface = interface
            inst.reset()
            cls._instances[interface] = inst
        return inst

    def __init__(self, interface=STA_IF):
        pass

    # ---- test control surface (NOT present on real hardware) ----------------
    def reset(self):
        self._active = False
        self._connected = False
        self._scan = []
        self._config = {}
        self._connect_after = 0       # status() polls to remain CONNECTING before GOT_IP
        self._fail_status = None      # if set, connect "fails" and status() returns this
        self._connect_ssid = None
        self._connect_bssid = None
        self.calls = []

    def program_scan(self, entries):
        """Set scan results. Accepts dicts or tuples; normalises to the contract
        6-tuple with ``bytes`` ssid/bssid and ``hidden`` always ``False``."""
        norm = []
        for e in entries:
            if isinstance(e, dict):
                ssid = _as_bytes(e["ssid"])
                bssid = _as_bytes(e.get("bssid")) or _NO_BSSID
                channel = e.get("channel", 0)
                rssi = e.get("rssi", -50)
                security = e.get("security", 0)
            else:
                ssid, bssid = _as_bytes(e[0]), _as_bytes(e[1])
                channel, rssi, security = e[2], e[3], e[4]
            norm.append((ssid, bssid, channel, rssi, security, False))
        self._scan = norm

    def fail_connect(self, status=STAT_NO_AP_FOUND):
        """Make subsequent ``connect()`` calls fail; ``status()`` returns ``status``."""
        self._fail_status = status

    def connect_after(self, polls):
        """Stay CONNECTING for ``polls`` ``status()`` reads, then report GOT_IP."""
        self._connect_after = polls

    def call_count(self, name):
        return sum(1 for c in self.calls if c.name == name)

    def last_call(self, name):
        for c in reversed(self.calls):
            if c.name == name:
                return c
        return None

    def _record(self, name, args, kwargs):
        self.calls.append(_Call(name, args, kwargs))

    # ---- device-facing API (contract-accurate) ------------------------------
    def active(self, *args):
        self._record("active", args, {})
        if args:
            self._active = bool(args[0])
        return self._active

    def scan(self):
        self._record("scan", (), {})
        if not self._active:
            raise OSError("STA must be active")
        return list(self._scan)

    def connect(self, ssid=None, key=None, *, bssid=None):
        if bssid is not None and not isinstance(bssid, (bytes, bytearray)):
            raise ValueError("bad bssid type")
        if bssid is not None and len(bssid) != 6:
            raise ValueError("bad bssid len")
        self._record("connect", (ssid, key), {"bssid": bssid})
        self._connect_ssid = ssid
        self._connect_bssid = bssid
        if self._fail_status is not None or self._connect_after > 0:
            self._connected = False
        else:
            self._connected = True   # default: connect succeeds unless scripted otherwise
        return None

    def disconnect(self):
        self._record("disconnect", (), {})
        self._connected = False
        return None

    def isconnected(self):
        self._record("isconnected", (), {})
        return self._connected

    def status(self, *args):
        self._record("status", args, {})
        if args:
            param = args[0]
            if param == "rssi":
                return self._scan[0][3] if self._scan else -50
            if param == "stations":
                return []
            raise ValueError("unknown status param")
        if self.interface == AP_IF:
            return None
        if self._fail_status is not None:
            return self._fail_status
        if self._connect_after > 0:
            self._connect_after -= 1
            if self._connect_after == 0:
                self._connected = True
            return STAT_CONNECTING
        return STAT_GOT_IP if self._connected else STAT_IDLE

    def ifconfig(self, *args):
        self._record("ifconfig", args, {})
        if args:
            self._config["ifconfig"] = args[0]
            return None
        if "ifconfig" in self._config:
            return self._config["ifconfig"]
        return _CONNECTED_IFCONFIG if self._connected else _DISCONNECTED_IFCONFIG

    def config(self, *args, **kwargs):
        self._record("config", args, kwargs)
        if kwargs:
            self._config.update(kwargs)
            return None
        if len(args) == 1:
            if args[0] == "ssid":
                if self._connect_ssid is not None:
                    return self._connect_ssid
                return self._config.get("ssid")
            return self._config.get(args[0])
        return None


def reset_all():
    """Reset every interface to defaults — call between tests for zero-effort isolation."""
    for inst in WLAN._instances.values():
        inst.reset()
