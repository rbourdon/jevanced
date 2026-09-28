"""The kill switch: one flag every part of the loop checks before acting."""

import threading


class KillSwitch(object):
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason = ""

    @property
    def tripped(self):
        return self._event.is_set()

    @property
    def reason(self):
        return self._reason

    def trip(self, reason="Stopped"):
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
                self._event.set()

    def reset(self):
        with self._lock:
            self._reason = ""
            self._event.clear()

    def wait(self, seconds):
        """Sleep up to ``seconds``; return True early if the switch trips."""
        if seconds <= 0:
            return self._event.is_set()
        return self._event.wait(seconds)
