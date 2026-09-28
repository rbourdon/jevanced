"""Windows smoke test: the real window and real DPAPI, without the game.

Run with IronPython on .NET Framework (the runtime Razor Enhanced uses):

    ipy.exe tools/windows_smoke.py [folder holding the jevanced package]

It builds the app the way run_jevanced.py does, with a stand-in for the game,
opens the jevanced window, saves a key through it, presses Start and STOP,
and checks the key is encrypted on disk and never written to the log.
Exits non-zero on the first failure.
"""

import os
import shutil
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE))

from jevanced.app import build_app  # noqa: E402
from jevanced.keystore import KEY_FILE_NAME, KeyStore  # noqa: E402
from jevanced.state import GameState, ItemState, PlayerState  # noqa: E402
from jevanced.ui.winforms import MethodInvoker, start_window  # noqa: E402

TEST_KEY = "smoke-test-key-0123456789abcdef"


class FakeGame(object):
    """A hurt character with bandages, so the stub has something to do."""

    def __init__(self):
        self.executed = []
        player = PlayerState(serial=1, name="Smoke", hits=30, hits_max=100,
                             position=(100, 100, 0))
        bandages = ItemState(serial=0x40000009, item_id=0x0E21, name="bandage", amount=10)
        self.state = GameState(player=player, backpack=[bandages])

    def is_connected(self):
        return True

    def read_state(self, scan_range=12):
        self.state.timestamp = time.time()
        return self.state

    def execute(self, action):
        self.executed.append(action)
        return "ok"

    def notify(self, text):
        pass


def check(condition, what):
    if not condition:
        print("FAIL: " + what)
        sys.exit(1)
    print("ok: " + what)


def wait_for(condition, timeout_s=10.0):
    end = time.time() + timeout_s
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.1)
    return False


def on_ui(form, fn):
    form.Invoke(MethodInvoker(fn))


def main():
    data_dir = tempfile.mkdtemp(prefix="jevanced-smoke-")
    try:
        run(data_dir)
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)
    print("Windows smoke test passed.")


def run(data_dir):
    app = build_app(FakeGame(), data_dir=data_dir)
    check(app.keystore.encrypted, "key storage uses Windows DPAPI")

    window = start_window(app)
    form = window.form
    check(form is not None and wait_for(lambda: form.Visible), "window opened")

    def enter_key():
        form.key_box.Text = TEST_KEY
        form.save_key_button.PerformClick()
    on_ui(form, enter_key)
    check(form.key_box.Text == "", "key box cleared after saving")
    check(TEST_KEY not in form.key_display.Text and form.key_display.Text.endswith("cdef"),
          "saved key shown masked")

    key_path = os.path.join(data_dir, KEY_FILE_NAME)
    with open(key_path, "rb") as f:
        raw = f.read()
    check(TEST_KEY.encode("ascii") not in raw, "key isn't on disk in the clear")
    check(KeyStore(key_path).load() == TEST_KEY, "a fresh key store decrypts the key")

    server = threading.Thread(target=app.serve)
    server.daemon = True
    server.start()

    on_ui(form, lambda: form.start_button.PerformClick())
    check(wait_for(lambda: app.view()["running"]), "Start runs a session")
    check(wait_for(lambda: any("would use item" in line for line in app.view()["log"])),
          "dry run logs the stub's choice instead of acting")
    check(app.game.executed == [], "dry run didn't act")

    on_ui(form, lambda: form.stop_button.PerformClick())
    check(wait_for(lambda: not app.view()["running"]), "STOP ends the session")
    check("Kill switch" in app.view()["detail"], "window says why it stopped")

    window.close()
    check(wait_for(lambda: not server.is_alive()), "closing the window shuts jevanced down")

    with open(os.path.join(data_dir, "jevanced.log")) as f:
        log_text = f.read()
    check(log_text.strip() != "", "log file written")
    check(TEST_KEY not in log_text, "key never written to the log")


if __name__ == "__main__":
    main()
