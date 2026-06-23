# docker-micropython-linux

A pinned **MicroPython runtime in Docker** plus a small **ESP32 test substrate**, for
running deterministic CI tests of MicroPython libraries — without a board, and without
the false confidence of testing under CPython.

![CI](https://github.com/mitchins/docker-micropython-linux/actions/workflows/ci.yml/badge.svg)

## Why this exists

MicroPython is **not** CPython. The standard library is a subset and behaves
differently: there is no `os.path`, no `types`, `base64` may be absent, `os.environ`
is `os.getenv`, and module surfaces differ. A library "tested" under `python3` can pass
its suite and still break on device. This repo runs your library's logic under the
**actual MicroPython interpreter** (the unix port), pinned to a known version, in a
throwaway container.

On top of that it ships a **scriptable fake of the ESP32 SDK** (`network`, `machine`)
so you can exercise Wi-Fi/state/pin logic deterministically — the fake provides the
*shape* (signatures, return types, exceptions, constants, identity captured from the
real firmware); your test provides the *behaviour*.

**Scope, honestly:** this targets **logic/framework correctness** (connection policy,
status handling, config parsing, callbacks, pin I/O sequencing) — not RF, timing, or
electrical behaviour. It is a high-signal, low-flake complement to on-device testing,
not a replacement.

## The image

Pulled from GitHub Container Registry (built and published by CI — see below):

    docker run -it ghcr.io/mitchins/docker-micropython-linux:latest
    MicroPython v1.28.0 on ...; linux version
    >>>

It builds the unix port of MicroPython from source on `debian:bookworm-slim`. Override
the version at build time:

    docker build --build-arg MICROPYTHON_VERSION=v1.28.0 -t micropython-linux .

The container's entrypoint is `micropython`, so arguments pass straight through:

    docker run --rm ghcr.io/mitchins/docker-micropython-linux:latest -c "import sys; print(sys.version)"
    docker run --rm -v "$PWD":/work -w /work ghcr.io/mitchins/docker-micropython-linux:latest /work/script.py

## The ESP32 substrate

In [`substrate/`](substrate/):

| File | Purpose |
|---|---|
| `CONTRACT-esp32-v1.28.md` | The SDK contract, captured from the esp32 port C source (MicroPython v1.28.0) + ESP-IDF v5.5.1 |
| `network.py` | `WLAN` fake — singleton-per-interface, `bytes` SSIDs, real `STAT_*` values, scriptable + spy |
| `machine.py` | `Pin` fake — `int` reads, readable `OUT`, scriptable inputs + spy |
| `aiotest.py` | `run_iterations()` — drives an async loop (e.g. `manage()`) deterministically, no wall-clock waits |

The fakes are *scriptable*, not emulated. A test programs outcomes and spies on calls;
it never authors a mock:

```python
import sys; sys.path.insert(0, "substrate")
import network

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.program_scan([{"ssid": "Home", "bssid": b"\x0a\x0b\x0c\x0d\x0e\x0f", "rssi": -50}])

# ... exercise your library against `network` ...

assert sta.call_count("connect") == 1
assert sta.last_call("connect").kwargs["bssid"] == b"\x0a\x0b\x0c\x0d\x0e\x0f"
```

See [`tests/`](tests/) for a full worked example: `wifimanager-status-regression.py`
tests [micropython-wifimanager](https://github.com/mitchins/micropython-wifimanager)
against the substrate (including driving its async `manage()` loop), and
`substrate-conformance.py` pins the fakes to the captured contract so they can't drift.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) on every push/PR:

1. Build the image
2. **Substrate conformance** — fakes vs `CONTRACT-esp32-v1.28.md`
3. **Library regression** — wifimanager suite in the MicroPython runtime (against a pinned library revision)
4. Smoke test
5. On push: **publish** the image to `ghcr.io/mitchins/docker-micropython-linux`

## Status / roadmap

- Pinned to MicroPython **v1.28.0**, ESP32 profile.
- Deferred: ESP8266 profile; broader `machine` (`irq`, ADC, I2C/SPI) — added when a real
  consumer needs them. The substrate establishes the pattern; it is single-target today.
