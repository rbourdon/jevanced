import unittest

from jevanced import controller as ctl
from jevanced.config import Settings
from jevanced.eventlog import EventLog
from jevanced.jev.client import JevAuthError, JevUnavailableError
from jevanced.killswitch import KillSwitch
from tests.fakes import FakeGame, ScriptedClient, make_state


def fast(**kw):
    kw.setdefault("tick_interval_ms", 250)
    s = Settings(**kw)
    s.tick_interval_ms = 0  # tests don't sleep
    return s


class ControllerTest(unittest.TestCase):
    def setUp(self):
        self.game = FakeGame()
        self.ks = KillSwitch()
        self.log = EventLog(clock=lambda: 0)
        self.ctl = ctl.Controller(self.game, self.ks, self.log, clock=lambda: 0)

    def run_with(self, client, settings):
        self.ctl.run_session(client, lambda: settings)
        return self.ctl.snapshot()

    def test_executes_validated_actions_then_jev_stop(self):
        client = ScriptedClient([
            {"type": "attack", "serial": 42},
            {"type": "stop", "reason": "done"},
        ])
        snap = self.run_with(client, fast(dry_run=False))
        self.assertEqual(self.game.executed, [{"type": "attack", "serial": 42}])
        self.assertEqual(snap["status"], ctl.STOPPED)
        self.assertIn("Jev ended the session: done", snap["detail"])
        self.assertEqual(snap["ticks"], 2)

    def test_dry_run_executes_nothing(self):
        client = ScriptedClient([{"type": "attack", "serial": 42}, {"type": "stop"}])
        self.run_with(client, fast(dry_run=True))
        self.assertEqual(self.game.executed, [])
        self.assertTrue(any("Dry run, would attack" in line for line in self.log.lines()))

    def test_kill_switch_during_decide_blocks_the_action(self):
        client = ScriptedClient([{"type": "attack", "serial": 42}])
        client.after_decide = lambda: self.ks.trip("Kill switch pressed")
        snap = self.run_with(client, fast(dry_run=False))
        self.assertEqual(self.game.executed, [])
        self.assertEqual(snap["status"], ctl.STOPPED)
        self.assertEqual(snap["detail"], "Kill switch pressed")

    def test_tripped_before_start_does_nothing(self):
        self.ks.trip("pressed early")
        client = ScriptedClient([{"type": "attack", "serial": 42}])
        self.run_with(client, fast(dry_run=False))
        self.assertEqual(client.decided, 0)

    def test_rejected_key_is_fatal(self):
        client = ScriptedClient([JevAuthError("401")])
        snap = self.run_with(client, fast(dry_run=False))
        self.assertEqual(snap["status"], ctl.ERROR)
        self.assertIn("rejected the API key", snap["detail"])
        self.assertTrue(self.ks.tripped)

    def test_stops_after_repeated_errors(self):
        client = ScriptedClient([JevUnavailableError("timeout")] * 10)
        snap = self.run_with(client, fast(dry_run=False, max_consecutive_errors=3))
        self.assertEqual(client.decided, 3)
        self.assertEqual(snap["status"], ctl.ERROR)
        self.assertIn("3 failures in a row", snap["detail"])

    def test_error_streak_resets_after_success(self):
        client = ScriptedClient([
            JevUnavailableError("a"), JevUnavailableError("b"),
            {"type": "wait", "ms": 0},
            JevUnavailableError("c"), JevUnavailableError("d"),
            {"type": "stop"},
        ])
        snap = self.run_with(client, fast(max_consecutive_errors=3))
        self.assertEqual(snap["status"], ctl.STOPPED)

    def test_invalid_actions_are_ignored_and_counted(self):
        client = ScriptedClient([{"type": "rm -rf"}, {"type": "say", "text": "hi"}])
        snap = self.run_with(client, fast(dry_run=False, max_consecutive_errors=2))
        self.assertEqual(self.game.executed, [])
        self.assertEqual(snap["status"], ctl.ERROR)

    def test_speech_allowed_when_opted_in(self):
        client = ScriptedClient([{"type": "say", "text": "hail"}, {"type": "stop"}])
        self.run_with(client, fast(dry_run=False, allow_speech=True))
        self.assertEqual(self.game.executed, [{"type": "say", "text": "hail"}])

    def test_death_stops_the_loop(self):
        self.game.state = make_state(hits=0, is_ghost=True)
        client = ScriptedClient([{"type": "attack", "serial": 1}])
        snap = self.run_with(client, fast(dry_run=False))
        self.assertEqual(snap["status"], ctl.ERROR)
        self.assertIn("dead", snap["detail"])
        self.assertEqual(client.decided, 0)

    def test_disconnect_stops_the_loop(self):
        self.game.connected = False
        snap = self.run_with(ScriptedClient(), fast())
        self.assertEqual(snap["status"], ctl.ERROR)
        self.assertIn("Not connected", snap["detail"])

    def test_script_abort_trips_switch_and_propagates(self):
        def abort():
            raise KeyboardInterrupt()
        self.game.on_read = abort
        with self.assertRaises(KeyboardInterrupt):
            self.run_with(ScriptedClient(), fast())
        self.assertTrue(self.ks.tripped)
        self.assertEqual(self.ctl.snapshot()["status"], ctl.STOPPED)

    def test_wait_action_extends_pause(self):
        s = fast()
        pause = self.ctl.tick(ScriptedClient([{"type": "wait", "ms": 2500}]), s)
        self.assertEqual(pause, 2.5)

    def test_notifies_in_game_on_start_and_stop(self):
        self.run_with(ScriptedClient([{"type": "stop"}]), fast())
        self.assertTrue(self.game.notices[0].startswith("started"))
        self.assertTrue(self.game.notices[-1].startswith("stopped"))


if __name__ == "__main__":
    unittest.main()
