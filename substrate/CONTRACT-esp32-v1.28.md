# ESP32 SDK fake — conformance contract

**Pinned to:** MicroPython **v1.28.0**, **esp32** port.
**Source of truth:** captured from the esp32 port C bindings at the `v1.28.0` tag
(`ports/esp32/network_wlan.c`, `ports/esp32/modnetwork.h`,
`ports/esp32/modnetwork_globals.h`, `ports/esp32/machine_pin.c`) — **not** docs,
not the unix port (which exposes neither `network.WLAN` nor esp `machine.Pin`).

The fakes in this directory must "walk and quack" like these surfaces: the library
under test must not be able to tell the difference at the call boundary. The fake
supplies *shape* (signatures, return types, exceptions, constants, identity); the
**test supplies behaviour** via the control surface.

---

## `network` module constants

| Symbol | Value | Provenance / stability |
|---|---|---|
| `STA_IF` | `0` | micropython-owned, stable |
| `AP_IF` | `1` | micropython-owned, stable |
| `STAT_IDLE` | `1000` | `modnetwork.h` enum — **stable** |
| `STAT_CONNECTING` | `1001` | **stable** |
| `STAT_GOT_IP` | `1010` | **stable** |
| `STAT_BEACON_TIMEOUT` | `200` | `WIFI_REASON_BEACON_TIMEOUT` (ESP-IDF v5.5.1) |
| `STAT_NO_AP_FOUND` | `201` | `WIFI_REASON_NO_AP_FOUND` (ESP-IDF v5.5.1) |
| `STAT_WRONG_PASSWORD` | `202` | `WIFI_REASON_AUTH_FAIL` (ESP-IDF v5.5.1) |
| `STAT_ASSOC_FAIL` | `203` | `WIFI_REASON_ASSOC_FAIL` (ESP-IDF v5.5.1) |
| `STAT_CONNECT_FAIL` | `203` | **aliases `STAT_ASSOC_FAIL`** on esp32 (same int, per micropython source) |
| `STAT_HANDSHAKE_TIMEOUT` | `204` | `WIFI_REASON_HANDSHAKE_TIMEOUT` (ESP-IDF v5.5.1) |

Failure-code source: `wifi_err_reason_t` in
`components/esp_wifi/include/esp_wifi_types_generic.h` at the **esp-idf `v5.5.1`** tag —
the IDF version MicroPython v1.28.0 recommends (`ports/esp32/README.md`). For reference,
`WIFI_REASON_CONNECTION_FAIL = 205` (which MicroPython's `status()` also reports as
wrong-password → `202`).

**Two-zone confidence.** The happy-path codes (`1000/1001/1010`) are MicroPython's
own and stable across versions. The failure codes above are ESP-IDF enum values pinned
to v5.5.1; they are version-sensitive, so re-capture from the matching IDF header if the
image's MicroPython/IDF pairing changes. On the rp2/cyw43 port these constants have
entirely different values (`CYW43_LINK_*`) — which is why this fake is esp-only and
version-pinned.

## `network.WLAN`

- `WLAN(interface=STA_IF)` returns the **same singleton per interface**
  (esp32 `make_new` returns static `wlan_sta_obj` / `wlan_ap_obj`). Bad id → `ValueError`.

| Method | Signature | Returns | Raises |
|---|---|---|---|
| `active([bool])` | optional arg | `bool` | `OSError` on driver error |
| `connect(ssid=None, key=None, *, bssid=None)` | `ssid`/`key` positional; `bssid` **kw-only**, 6 bytes | `None` | `ValueError` (bad bssid len), `OSError` |
| `disconnect()` | — | `None` | `OSError` |
| `status([param])` | no-arg, or `'rssi'` / `'stations'` | no-arg → **int** (STA only; AP → `None`); `'rssi'` → int; `'stations'` → list of 1-tuples of `bytes` | `ValueError` (unknown param), `OSError` |
| `scan()` | — | **list of 6-tuples** | `OSError("STA must be active")` if STA inactive |
| `isconnected()` | — | `bool` | — |
| `ifconfig([tuple])` | get/set | 4-tuple `(ip, mask, gw, dns)` of `str` | — |
| `config(key)` / `config(**kw)` | get/set | get → value; set → `None` | — |

**`scan()` tuple shape (load-bearing):**
`(ssid: bytes, bssid: bytes, channel: int, RSSI: int, security: int, hidden)`
- `ssid` and `bssid` are **`bytes`**, never `str`.
- on esp32 `hidden` is **always `False`** (never populated; `// XXX hidden?` in source).

## `machine.Pin`

- `Pin(id, mode=None, pull=-1, *, value=None, drive=None, hold=None)`.
  Bad id → `ValueError("invalid pin")`.

| Member | Behaviour |
|---|---|
| `value([x])` | no-arg → **int `0`/`1`** (`gpio_get_level`); with arg → `None` (sets) |
| `pin(x)` | call form ≡ `value(x)` |
| `on()` / `off()` / `toggle()` | return `None` |
| `init(...)` / `irq(...)` | exist (`irq` deferred for day-zero) |

**Mode constants:** `IN`=`GPIO_MODE_INPUT` (`1`), **`OUT`=`GPIO_MODE_INPUT_OUTPUT` (`3`)**,
`OPEN_DRAIN`=`..._OD` (`7`). Because `OUT` is *input-output* on esp32, **reading an
output pin returns the last written level** — the fake replicates this. Pulls:
`PULL_UP`, `PULL_DOWN`.

---

## Confirmed quack-leaks the fake must honour

1. `scan()`/`status('stations')` return **`bytes`**, not `str`.
2. `WLAN(iface)` is a **singleton per interface** (identity is observable).
3. `scan()` `hidden` element is **always `False`** on esp32.
4. `Pin.value()` returns **`int`**, not `bool`.
5. `Pin.OUT` is **readable** (read-back of written level).
6. `STAT_*` failure codes are **esp/IDF-specific** and `CONNECT_FAIL == ASSOC_FAIL`.

## Provenance summary

- `network`/`machine` shapes, constants, return types, exceptions: MicroPython esp32
  port at the **v1.28.0** tag.
- Failure `STAT_*` integers: ESP-IDF **v5.5.1** `wifi_err_reason_t`.

Re-capture both if the image bumps its MicroPython version (and with it the
recommended IDF version).
