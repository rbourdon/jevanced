import os
import shutil
import tempfile
import threading
import unittest

from jevanced import app as appmod
from jevanced.config import SettingsStore
from jevanced.eventlog import EventLog
from jevanced.jev.client import JevAuthError, JevUnavailableError, KeyCheck
from jevanced.keystore import KeyStore
from tests.fakes import FakeGame, ScriptedClient
from tests.test_keystore import XorProtector

KEY = "sk-live-0123456789abcdef"


class AppTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.game = FakeGame()
        self.log = EventLog(clock=lambda: 0)
        self.keystore = KeyStore(os.path.join(self.dir, "key.bin"), XorProtector())
        self.settings_store = SettingsStore(os.path.join(self.dir, "settings.json"))
        self.clients = []
        self.next_client = lambda: ScriptedClient([{"type": "stop", "reason": "test"}])

    def tearDown(self):
        shutil.rmtree(self.dir)

    def factory(self, backend, key):
        self.assertEqual(key, KEY)
        client = self.next_client()
        self.clients.append(client)
        return client

    def make_app(self):
        app = appmod.JevancedApp(self.game, self.keystore, self.settings_store,
                                 self.log, client_factory=self.factory)
        app.update_settings(tick_interval_ms=250)
        return app

    def test_missing_key_blocks_start_with_clear_message(self):
        app = self.make_app()
        view = app.view()
        self.assertEqual(view["key_state"], appmod.KEY_MISSING)
        self.assertFalse(view["can_start"])
        ok, message = app.request_start()
        self.assertFalse(ok)
        self.assertIn("API key", message)
        self.assertIn("API key", app.view()["detail"])
        self.assertFalse(app.serve_once(0))

    def test_save_key_masks_and_redacts(self):
        app = self.make_app()
        ok, _ = app.save_key(KEY)
        self.assertTrue(ok)
        view = app.view()
        self.assertEqual(view["key_state"], appmod.KEY_SAVED)
        self.assertNotIn(KEY, view["key_display"])
        self.assertTrue(view["key_display"].endswith(KEY[-4:]))
        self.log.info("oops " + KEY)
        self.assertTrue(all(KEY not in line for line in app.view()["log"]))
        self.assertTrue(all(KEY not in str(v) for v in view.values()))

    def test_bad_key_input_is_reported(self):
        app = self.make_app()
        ok, message = app.save_key("two words")
        self.assertFalse(ok)
        view = app.view()
        self.assertTrue(view["key_error"])
        self.assertEqual(view["key_message"], message)
        self.assertEqual(view["key_state"], appmod.KEY_MISSING)

    def test_key_loaded_from_disk_is_redacted(self):
        self.keystore.save(KEY)
        app = self.make_app()
        self.assertEqual(app.view()["key_state"], appmod.KEY_SAVED)
        self.log.error("echo " + KEY)
        self.assertNotIn(KEY, self.log.lines()[-1])

    def test_start_runs_a_session_on_serve_thread(self):
        self.keystore.save(KEY)
        app = self.make_app()
        self.assertTrue(app.request_start()[0])
        self.assertTrue(app.serve_once(0))
        view = app.view()
        self.assertEqual(view["status"], "stopped")
        self.assertIn("Jev ended the session: test", view["detail"])
        self.assertEqual(view["backend"], "Scripted")
        self.assertEqual(view["key_state"], appmod.KEY_VERIFIED)
        self.assertTrue(self.clients[0].closed)

    def test_rejected_key_shows_error_and_blocks_restart(self):
        self.keystore.save(KEY)
        self.next_client = lambda: ScriptedClient(check_error=JevAuthError("401"))
        app = self.make_app()
        app.request_start()
        app.serve_once(0)
        view = app.view()
        self.assertEqual(view["key_state"], appmod.KEY_REJECTED)
        self.assertTrue(view["key_error"])
        self.assertIn("rejected", view["detail"])
        self.assertFalse(view["can_start"])
        self.assertFalse(app.request_start()[0])
        app.save_key(KEY)
        self.assertTrue(app.request_start()[0])

    def test_unreachable_jev_is_reported(self):
        self.keystore.save(KEY)
        self.next_client = lambda: ScriptedClient(check_error=JevUnavailableError("timed out"))
        app = self.make_app()
        app.request_start()
        app.serve_once(0)
        self.assertIn("Couldn't reach Jev", app.view()["detail"])
        self.assertEqual(self.game.executed, [])

    def test_unverified_key_check_keeps_saved_state(self):
        self.keystore.save(KEY)
        self.next_client = lambda: ScriptedClient([{"type": "stop"}], check=KeyCheck(False, "stub"))
        app = self.make_app()
        app.request_start()
        app.serve_once(0)
        self.assertEqual(app.view()["key_state"], appmod.KEY_SAVED)
        self.assertEqual(app.view()["key_message"], "stub")

    def test_stop_before_serve_picks_up_cancels_start(self):
        self.keystore.save(KEY)
        app = self.make_app()
        app.request_start()
        app.stop()
        self.assertFalse(app.serve_once(0))
        self.assertEqual(self.clients, [])

    def test_kill_switch_stops_a_running_session(self):
        self.keystore.save(KEY)
        started = threading.Event()

        def endless():
            client = ScriptedClient([{"type": "walk", "direction": "North"}] * 100000)
            client.after_decide = started.set
            return client
        self.next_client = endless
        app = self.make_app()
        app.update_settings(dry_run=False)
        app.request_start()
        worker = threading.Thread(target=app.serve_once, args=(0,))
        worker.start()
        self.assertTrue(started.wait(5))
        self.assertTrue(app.view()["running"])
        self.assertTrue(app.view()["can_stop"])
        app.stop("Kill switch pressed")
        worker.join(5)
        self.assertFalse(worker.is_alive())
        view = app.view()
        self.assertFalse(view["running"])
        self.assertEqual(view["detail"], "Kill switch pressed")
        self.assertTrue(self.clients[0].closed)

    def test_shutdown_ends_serve(self):
        app = self.make_app()
        worker = threading.Thread(target=app.serve, args=(0.01,))
        worker.start()
        app.request_shutdown()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertTrue(app.killswitch.tripped)

    def test_clear_key(self):
        self.keystore.save(KEY)
        app = self.make_app()
        app.clear_key()
        self.assertIsNone(self.keystore.load())
        self.assertEqual(app.view()["key_state"], appmod.KEY_MISSING)

    def test_settings_persist(self):
        app = self.make_app()
        app.update_settings(dry_run=False, allow_speech=True, bogus=1)
        loaded = self.settings_store.load()
        self.assertFalse(loaded.dry_run)
        self.assertTrue(loaded.allow_speech)

    def test_status_text(self):
        self.keystore.save(KEY)
        app = self.make_app()
        self.assertEqual(app.view()["status_text"], "Idle")


class BuildAppTest(unittest.TestCase):
    def test_build_app_uses_data_dir(self):
        folder = tempfile.mkdtemp()
        try:
            app = appmod.build_app(FakeGame(), data_dir=os.path.join(folder, "jv"))
            app.log.info("hello")
            self.assertTrue(os.path.exists(os.path.join(folder, "jv", "jevanced.log")))
        finally:
            shutil.rmtree(folder)


if __name__ == "__main__":
    unittest.main()
