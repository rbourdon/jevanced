import os
import shutil
import tempfile
import unittest

from jevanced.config import Settings, SettingsStore


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "settings.json")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_safe_defaults(self):
        s = Settings()
        self.assertTrue(s.dry_run)
        self.assertFalse(s.allow_speech)
        self.assertNotIn("say", s.allowed_actions())

    def test_speech_opt_in(self):
        self.assertIn("say", Settings(allow_speech=True).allowed_actions())

    def test_clamps_values(self):
        s = Settings(tick_interval_ms=1, scan_range=500, max_consecutive_errors=0,
                     backend="something-else")
        self.assertEqual(s.tick_interval_ms, Settings.MIN_TICK_MS)
        self.assertEqual(s.scan_range, 24)
        self.assertEqual(s.max_consecutive_errors, 1)
        self.assertEqual(s.backend, "jev")

    def test_round_trip_and_bad_file(self):
        store = SettingsStore(self.path)
        self.assertTrue(store.load().dry_run)
        store.save(Settings(dry_run=False, tick_interval_ms=2000))
        loaded = store.load()
        self.assertFalse(loaded.dry_run)
        self.assertEqual(loaded.tick_interval_ms, 2000)
        with open(self.path, "w") as handle:
            handle.write("{not json")
        self.assertTrue(store.load().dry_run)

    def test_task_and_instructions(self):
        self.assertEqual(Settings().task, "stay_safe")
        self.assertEqual(Settings(task="lumberjack").task, "lumberjack")
        self.assertEqual(Settings(task="mine gold").task, "stay_safe")
        s = Settings(instructions="  Chop near\nYew  " + "x" * 300)
        self.assertTrue(s.instructions.startswith("Chop near Yew x"))
        self.assertEqual(len(s.instructions), 200)
        self.assertEqual(Settings(instructions=None).instructions, "")
        self.assertEqual(Settings().wood_goal, 0)
        self.assertEqual(Settings(wood_goal="150").wood_goal, 150)
        self.assertEqual(Settings(wood_goal=-5).wood_goal, 0)
        self.assertEqual(Settings(wood_goal="lots").wood_goal, 0)

    def test_ignores_unknown_keys(self):
        with open(self.path, "w") as handle:
            handle.write('{"api_key": "sk-nope", "dry_run": false}')
        loaded = SettingsStore(self.path).load()
        self.assertFalse(loaded.dry_run)
        self.assertFalse(hasattr(loaded, "api_key"))


if __name__ == "__main__":
    unittest.main()
