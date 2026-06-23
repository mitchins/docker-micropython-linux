"""Contract-accurate fake of the esp32 ``machine`` module (MicroPython v1.28.0).

Day-zero subset: ``Pin``. See CONTRACT-esp32-v1.28.md. Scriptable fake: GPIO level
is shared per pin id (survives reconstruction, like real hardware), reads return
``int``, and ``OUT`` pins are readable. Use ``set_external()`` to script an input
level and ``call_count()`` to spy on writes.
"""


class Pin:
    # Mode constants — esp32 values (note OUT is INPUT_OUTPUT, i.e. readable).
    IN = 1
    OUT = 3
    OPEN_DRAIN = 7
    PULL_UP = 1
    PULL_DOWN = 2
    IRQ_RISING = 1
    IRQ_FALLING = 2

    _levels = {}      # id -> level (shared GPIO state, like the real chip)
    _instances = {}   # id -> Pin (a given GPIO maps to one logical pin)

    def __new__(cls, pin_id, *args, **kwargs):
        if not isinstance(pin_id, int) or pin_id < 0:
            raise ValueError("invalid pin")
        inst = cls._instances.get(pin_id)
        if inst is None:
            inst = object.__new__(cls)
            inst.id = pin_id
            inst.mode = None
            inst.pull = -1
            inst.calls = []
            cls._instances[pin_id] = inst
            cls._levels.setdefault(pin_id, 0)
        if args or kwargs:
            inst._configure(args, kwargs)
        return inst

    def __init__(self, pin_id=None, *args, **kwargs):
        pass

    def _configure(self, args, kwargs):
        mode = args[0] if len(args) >= 1 else kwargs.get("mode")
        if mode is not None:
            self.mode = mode
        if len(args) >= 2:
            self.pull = args[1]
        elif "pull" in kwargs:
            self.pull = kwargs["pull"]
        v = kwargs.get("value")
        if v is not None:
            Pin._levels[self.id] = 1 if v else 0

    # ---- device-facing API --------------------------------------------------
    def value(self, *args):
        self.calls.append(("value", args))
        if args:
            Pin._levels[self.id] = 1 if args[0] else 0
            return None
        return Pin._levels[self.id]

    def __call__(self, *args):
        return self.value(*args)

    def on(self):
        self.calls.append(("on", ()))
        Pin._levels[self.id] = 1
        return None

    def off(self):
        self.calls.append(("off", ()))
        Pin._levels[self.id] = 0
        return None

    def toggle(self):
        self.calls.append(("toggle", ()))
        Pin._levels[self.id] = 0 if Pin._levels[self.id] else 1
        return None

    def init(self, *args, **kwargs):
        self._configure(args, kwargs)
        return None

    def irq(self, *args, **kwargs):
        self.calls.append(("irq", args, kwargs))
        return None

    # ---- test control surface (NOT present on real hardware) ----------------
    def set_external(self, level):
        """Script the level this pin reads, as if driven externally."""
        Pin._levels[self.id] = 1 if level else 0

    def call_count(self, name):
        return sum(1 for c in self.calls if c[0] == name)


def reset_all():
    """Clear all pin state — call between tests for zero-effort isolation."""
    Pin._instances = {}
    Pin._levels = {}
