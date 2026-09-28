"""In-memory activity log shown in the UI, with secret redaction.

Every line goes through ``redact`` before it is stored or written, so the
Jev API key can't leak into the UI, the log file, or a bug report even if
an error message happens to include it.
"""

import collections
import threading
import time

REDACTED = "[redacted]"


class EventLog(object):
    def __init__(self, capacity=300, clock=time.time, sink=None):
        self._lines = collections.deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._secrets = set()
        self._clock = clock
        self._sink = sink

    def add_secret(self, value):
        if value and len(value) >= 4:
            with self._lock:
                self._secrets.add(value)

    def forget_secrets(self):
        with self._lock:
            self._secrets.clear()

    def redact(self, text):
        text = str(text)
        with self._lock:
            secrets = sorted(self._secrets, key=len, reverse=True)
        for secret in secrets:
            text = text.replace(secret, REDACTED)
        return text

    def _add(self, level, message):
        stamp = time.strftime("%H:%M:%S", time.localtime(self._clock()))
        line = "{0} {1:<5} {2}".format(stamp, level, self.redact(message))
        with self._lock:
            self._lines.append(line)
        if self._sink is not None:
            try:
                self._sink(line)
            except Exception:
                pass
        return line

    def info(self, message):
        return self._add("INFO", message)

    def warn(self, message):
        return self._add("WARN", message)

    def error(self, message):
        return self._add("ERROR", message)

    def lines(self, limit=None):
        with self._lock:
            lines = list(self._lines)
        if limit is not None:
            lines = lines[-limit:]
        return lines


def file_sink(path):
    """Append log lines to ``path``; lines are already redacted."""
    def write(line):
        with open(path, "a") as handle:
            handle.write(line + "\n")
    return write
