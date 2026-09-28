"""Ties the pieces together and gives the UI a small surface to call.

Threading: the UI runs on its own thread and only calls the ``save_key``,
``clear_key``, ``request_start``, ``stop``, ``update_settings``,
``request_shutdown`` and ``view`` methods. The game loop runs on Razor
Enhanced's script thread inside ``serve``.
"""

import os
import threading
import time

from jevanced import controller as ctl
from jevanced.config import SettingsStore, default_data_dir
from jevanced.eventlog import EventLog, file_sink
from jevanced.jev import JevAuthError, JevError, make_client
from jevanced.keystore import KEY_FILE_NAME, KeyFormatError, KeyStore, mask_key
from jevanced.killswitch import KillSwitch

KEY_MISSING = "missing"
KEY_SAVED = "saved"
KEY_VERIFIED = "verified"
KEY_REJECTED = "rejected"


class JevancedApp(object):
    def __init__(self, game, keystore, settings_store, log,
                 client_factory=make_client, clock=time.time):
        self.game = game
        self.keystore = keystore
        self.settings_store = settings_store
        self.log = log
        self.client_factory = client_factory
        self.settings = settings_store.load()
        self.killswitch = KillSwitch()
        self.controller = ctl.Controller(game, self.killswitch, log, clock)
        self._lock = threading.Lock()
        self._start_requested = threading.Event()
        self._shutdown = threading.Event()
        self._notice = ""
        self._backend_name = ""
        stored = keystore.load()
        if stored:
            log.add_secret(stored)
            self._key_state = KEY_SAVED
            self._key_message = "Key saved on this computer."
        else:
            self._key_state = KEY_MISSING
            self._key_message = "No Jev API key saved yet."
        self._key_display = mask_key(stored)
        self._key_error = False

    # ---- called from the UI thread ------------------------------------

    def save_key(self, raw):
        try:
            key = self.keystore.save(raw)
        except KeyFormatError as exc:
            return self._key_problem(str(exc))
        except Exception as exc:
            # Only the exception type: the message could echo the key.
            self.log.error("Couldn't save the key: {0}".format(type(exc).__name__))
            return self._key_problem("Couldn't save the key on this computer.")
        self.log.add_secret(key)
        where = "encrypted for your Windows account" if self.keystore.encrypted \
            else "NOT encrypted (Windows DPAPI isn't available here)"
        with self._lock:
            self._key_state = KEY_SAVED
            self._key_display = mask_key(key)
            self._key_error = False
            self._key_message = "Key saved, {0}. It's checked with Jev when you press Start.".format(where)
        self.log.info("API key saved.")
        return True, self._key_message

    def _key_problem(self, message):
        with self._lock:
            self._key_message = message
            self._key_error = True
        return False, message

    def clear_key(self):
        self.stop("API key removed")
        self.keystore.clear()
        with self._lock:
            self._key_state = KEY_MISSING
            self._key_display = ""
            self._key_error = False
            self._key_message = "Key removed from this computer."
        self.log.info("API key removed.")

    def request_start(self):
        if self.is_running():
            return self._refuse("Already running.")
        if not self.keystore.has_key():
            with self._lock:
                self._key_state = KEY_MISSING
            return self._refuse("Enter and save your Jev API key before starting.")
        if self._key_state == KEY_REJECTED:
            return self._refuse("Jev rejected the saved key. Save a new key first.")
        with self._lock:
            self._notice = ""
            self._start_requested.set()
        return True, "Starting."

    def _refuse(self, message):
        with self._lock:
            self._notice = message
        return False, message

    def stop(self, reason="Kill switch pressed"):
        with self._lock:
            self._start_requested.clear()
            self.killswitch.trip(reason)

    def update_settings(self, **changes):
        with self._lock:
            for key, value in changes.items():
                if key in self.settings.FIELDS:
                    setattr(self.settings, key, value)
            self.settings.normalise()
            settings = self.settings
        try:
            self.settings_store.save(settings)
        except Exception as exc:
            self.log.warn("Couldn't save settings: {0}".format(exc))

    def request_shutdown(self):
        self.stop("jevanced window closed")
        self._shutdown.set()
        self._start_requested.set()  # wake serve() so it can exit

    def is_running(self):
        return self.controller.snapshot()["status"] == ctl.RUNNING

    def view(self):
        snap = self.controller.snapshot()
        running = snap["status"] == ctl.RUNNING
        with self._lock:
            key_state = self._key_state
            view = {
                "running": running,
                "status": snap["status"],
                "detail": snap["detail"] if running else (self._notice or snap["detail"]),
                "key_state": key_state,
                "key_display": self._key_display or "No key saved",
                "key_message": self._key_message,
                "key_error": self._key_error,
                "key_encrypted": self.keystore.encrypted,
                "backend": self._backend_name,
                "dry_run": self.settings.dry_run,
                "allow_speech": self.settings.allow_speech,
                "tick_interval_ms": self.settings.tick_interval_ms,
                "last_action": snap["last_action"],
                "ticks": snap["ticks"],
                "error_streak": snap["error_streak"],
            }
        view["status_text"] = _status_text(view)
        view["can_start"] = (not running) and key_state != KEY_MISSING \
            and key_state != KEY_REJECTED
        view["can_stop"] = running or self._start_requested.is_set()
        view["log"] = self.log.lines(200)
        return view

    # ---- called on Razor Enhanced's script thread ---------------------

    def serve(self, poll_s=0.25):
        """Wait for Start presses and run sessions until shutdown."""
        try:
            while not self._shutdown.is_set():
                self.serve_once(poll_s)
        finally:
            self.killswitch.trip("jevanced exited")

    def serve_once(self, poll_s=0.25):
        self._start_requested.wait(poll_s)
        with self._lock:
            if self._shutdown.is_set() or not self._start_requested.is_set():
                return False
            self._start_requested.clear()
            # Reset under the lock so a Stop pressed from here on is kept.
            self.killswitch.reset()
        self._run_session()
        return True

    def _run_session(self):
        key = self.keystore.load()
        if not key:
            with self._lock:
                self._key_state = KEY_MISSING
                self._notice = "Enter and save your Jev API key before starting."
            return
        self.log.add_secret(key)
        client = self.client_factory(self.settings.backend, key)
        with self._lock:
            self._backend_name = client.display_name
        try:
            try:
                check = client.check_key()
            except JevAuthError as exc:
                with self._lock:
                    self._key_state = KEY_REJECTED
                    self._key_error = True
                    self._key_message = "Jev rejected this key. Check it and save it again."
                    self._notice = self._key_message
                self.log.error("Jev rejected the API key: {0}".format(exc))
                return
            except JevError as exc:
                with self._lock:
                    self._notice = "Couldn't reach Jev to check the key: {0}".format(exc)
                self.log.error(self._notice)
                return
            with self._lock:
                self._key_state = KEY_VERIFIED if check.verified else KEY_SAVED
                self._key_error = False
                self._key_message = check.message
            if self.killswitch.tripped:
                return
            self.controller.run_session(client, lambda: self.settings)
        finally:
            client.close()


def _status_text(view):
    status = view["status"]
    if status == ctl.RUNNING:
        return "RUNNING (dry run: logging only)" if view["dry_run"] else "RUNNING: controlling your character"
    if status == ctl.ERROR:
        return "STOPPED WITH AN ERROR"
    if status == ctl.STOPPED:
        return "Stopped"
    return "Idle"


def build_app(game, data_dir=None):
    """Production wiring: files under %APPDATA%\\jevanced."""
    data_dir = data_dir or default_data_dir()
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir)
    log = EventLog(sink=file_sink(os.path.join(data_dir, "jevanced.log")))
    keystore = KeyStore(os.path.join(data_dir, KEY_FILE_NAME))
    settings_store = SettingsStore(os.path.join(data_dir, "settings.json"))
    app = JevancedApp(game, keystore, settings_store, log)
    if not keystore.encrypted:
        log.warn("Windows DPAPI isn't available, so the API key will be stored unencrypted.")
    return app
