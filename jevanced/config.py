"""User settings, kept as JSON next to the stored key (never the key itself)."""

import json
import os

from jevanced import actions

APP_DIR_NAME = "jevanced"


def default_data_dir():
    """%APPDATA%\\jevanced on Windows, ~/.jevanced elsewhere."""
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, APP_DIR_NAME)
    return os.path.join(os.path.expanduser("~"), "." + APP_DIR_NAME)


class Settings(object):
    FIELDS = {
        # Pause between decisions. Also the floor on how fast jevanced acts.
        "tick_interval_ms": 1500,
        # Log what Jev chose without doing it. On until the user turns it off.
        "dry_run": True,
        # How far to look for mobiles and ground items, in tiles.
        "scan_range": 12,
        # Stop after this many failed ticks in a row.
        "max_consecutive_errors": 5,
        # Let Jev speak in game chat.
        "allow_speech": False,
        # Which Jev client to use. Only "stub" exists until Typesafe's API
        # docs are in hand.
        "backend": "stub",
    }
    MIN_TICK_MS = 250
    MAX_TICK_MS = 60000

    def __init__(self, **values):
        for key, default in self.FIELDS.items():
            setattr(self, key, values.get(key, default))
        self.normalise()

    def normalise(self):
        try:
            tick = int(self.tick_interval_ms)
        except (TypeError, ValueError):
            tick = self.FIELDS["tick_interval_ms"]
        self.tick_interval_ms = min(max(tick, self.MIN_TICK_MS), self.MAX_TICK_MS)
        try:
            scan = int(self.scan_range)
        except (TypeError, ValueError):
            scan = self.FIELDS["scan_range"]
        self.scan_range = min(max(scan, 1), 24)
        try:
            errors = int(self.max_consecutive_errors)
        except (TypeError, ValueError):
            errors = self.FIELDS["max_consecutive_errors"]
        self.max_consecutive_errors = max(errors, 1)
        self.dry_run = bool(self.dry_run)
        self.allow_speech = bool(self.allow_speech)
        if self.backend not in ("stub",):
            self.backend = "stub"

    def allowed_actions(self):
        allowed = set(actions.DEFAULT_ALLOWED)
        if self.allow_speech:
            allowed.add("say")
        return allowed

    def to_dict(self):
        return dict((key, getattr(self, key)) for key in self.FIELDS)


class SettingsStore(object):
    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, "r") as handle:
                data = json.load(handle)
        except (IOError, OSError, ValueError):
            return Settings()
        if not isinstance(data, dict):
            return Settings()
        known = dict((k, v) for k, v in data.items() if k in Settings.FIELDS)
        return Settings(**known)

    def save(self, settings):
        folder = os.path.dirname(self.path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as handle:
            json.dump(settings.to_dict(), handle, indent=2, sort_keys=True)
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rename(tmp, self.path)
