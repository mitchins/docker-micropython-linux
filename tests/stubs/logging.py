"""Logging stub compatible with wifi_manager imports under MicroPython."""

import sys

CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20
DEBUG = 10
NOTSET = 0

_LEVEL_STR = {
    CRITICAL: "CRIT",
    ERROR: "ERROR",
    WARNING: "WARN",
    INFO: "INFO",
    DEBUG: "DEBUG",
}

_stream = sys.stderr
_level = INFO
_loggers = {}


class Logger:
    level = NOTSET

    def __init__(self, name):
        self.name = name

    def _level_str(self, level):
        return _LEVEL_STR.get(level, "LVL%s" % level)

    def set_level(self, level):
        self.level = level

    def is_enabled_for(self, level):
        return level >= (self.level or _level)

    def log(self, level, msg, *args):
        if level >= (self.level or _level):
            _stream.write("[%s][%s]: " % (self._level_str(level), self.name))
            if args:
                _stream.write((str(msg) % args) + "\n")
            else:
                _stream.write(str(msg) + "\n")

    def debug(self, msg, *args):
        self.log(DEBUG, msg, *args)

    def info(self, msg, *args):
        self.log(INFO, msg, *args)

    def warning(self, msg, *args):
        self.log(WARNING, msg, *args)

    def error(self, msg, *args):
        self.log(ERROR, msg, *args)

    def critical(self, msg, *args):
        self.log(CRITICAL, msg, *args)

    def exc(self, e, msg, *args):
        self.log(ERROR, msg, *args)

    def exception(self, msg, *args):
        self.exc(sys.exc_info()[1], msg, *args)


Logger.setLevel = Logger.set_level
Logger.isEnabledFor = Logger.is_enabled_for


def get_logger(name):
    if name in _loggers:
        return _loggers[name]
    logger = Logger(name)
    _loggers[name] = logger
    return logger


def getLogger(name=None):
    return get_logger(name or "root")


def info(msg, *args):
    get_logger("root").info(msg, *args)


def debug(msg, *args):
    get_logger("root").debug(msg, *args)


def warning(msg, *args):
    get_logger("root").warning(msg, *args)


warn = warning


def error(msg, *args):
    get_logger("root").error(msg, *args)


def critical(msg, *args):
    get_logger("root").critical(msg, *args)


def exception(msg, *args):
    get_logger("root").exception(msg, *args)


def basic_config(level=INFO, filename=None, stream=None, format=None):  # noqa: A002
    global _level, _stream
    _level = level
    if stream is not None:
        _stream = stream
    if filename is not None:
        pass
    if format is not None:
        pass


basicConfig = basic_config
