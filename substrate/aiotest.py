"""Deterministic async driving for substrate-based tests.

``run_iterations`` runs an infinite-loop coroutine (e.g. ``WifiManager.manage``) for
a bounded number of its ``await sleep`` points, with **no wall-clock delay**, then
returns. It temporarily replaces the supplied asyncio module's ``sleep`` / ``sleep_ms``
with a fast, counting stop so the loop advances a known number of times and unwinds
cleanly. This lets tests exercise real async control flow without 10-second waits or
flaky timing.
"""


class _StopLoop(Exception):
    pass


def run_iterations(coro_factory, iterations, asyncio_module):
    """Run ``coro_factory()`` until its sleep points have fired ``iterations`` times.

    coro_factory:   zero-arg callable returning a fresh coroutine (e.g. ``mgr.manage``).
    iterations:     number of loop turns (sleep points) to allow before stopping.
    asyncio_module: the asyncio module the code-under-test actually uses (patched/restored).

    Returns the number of loop turns executed.
    """
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    counter = {"n": 0}
    saved = {}
    for name in ("sleep", "sleep_ms"):
        if hasattr(asyncio_module, name):
            saved[name] = getattr(asyncio_module, name)

    async def fast_sleep(*_args, **_kwargs):
        counter["n"] += 1
        if counter["n"] >= iterations:
            raise _StopLoop()

    for name in saved:
        setattr(asyncio_module, name, fast_sleep)

    try:
        runner = getattr(asyncio_module, "run", None)
        try:
            if runner is not None:
                runner(coro_factory())
            else:
                loop = asyncio_module.get_event_loop()
                loop.run_until_complete(coro_factory())
        except _StopLoop:
            pass
    finally:
        for name, fn in saved.items():
            setattr(asyncio_module, name, fn)

    return counter["n"]
