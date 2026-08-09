"""Log with a fallback: if the main file is busy, write to a log named with the PID."""
import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import data_dir, log_path

_ready = False
_crash_file = None      # crash-trap file: needed to mark a clean exit


def setup() -> logging.Logger:
    global _ready
    log = logging.getLogger("mas")
    if _ready:
        return log

    log.setLevel(logging.DEBUG)
    # Milliseconds are mandatory: the log regularly holds four events within one
    # second, and without them a race cannot be untangled.
    fmt = logging.Formatter("%(asctime)s.%(msecs)03d %(levelname)-7s %(name)s: %(message)s",
                            "%Y-%m-%d %H:%M:%S")

    try:
        fh = RotatingFileHandler(log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8")
    except OSError:
        import os
        fh = RotatingFileHandler(data_dir() / f"mas.{os.getpid()}.log",
                                 maxBytes=512_000, backupCount=1, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)

    if not getattr(sys, "frozen", False) and sys.stderr:
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        log.addHandler(sh)

    _install_crash_traps(log)
    _ready = True
    return log


def _install_crash_traps(log: logging.Logger) -> None:
    """A crash that leaves no trace in the log is the worst kind. We catch both
    what kills the interpreter natively and exceptions in background threads."""
    import faulthandler
    import threading

    global _crash_file
    try:
        path = data_dir() / "crash.log"
        fh = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 — lives to process end
        fh.write(f"\n--- start {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        faulthandler.enable(file=fh, all_threads=True)
        _crash_file = fh
    except OSError:
        log.warning("native crash trap not installed", exc_info=True)

    def on_thread_exc(args):
        log.error("unhandled exception in thread %s",
                  args.thread.name if args.thread else "?",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = on_thread_exc

    def on_exc(exc_type, exc, tb):
        log.error("unhandled exception", exc_info=(exc_type, exc, tb))

    sys.excepthook = on_exc


def note_clean_exit() -> None:
    """A "we made it to a clean exit" mark in the crash-trap file.

    The trap also records exceptions that Windows handles by itself: creating the
    overlay window and the tray window throws three of them per run, and the file
    kept for catching a real crash becomes unreadable. This mark shows how every
    run ended: if it is missing, the process died.
    """
    if _crash_file is None:
        return
    try:
        _crash_file.write(f"--- clean exit "
                          f"{__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
        _crash_file.flush()
    except (OSError, ValueError):
        pass


def get(name: str) -> logging.Logger:
    return setup().getChild(name)
