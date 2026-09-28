"""The decision loop: read the game, ask Jev, check the answer, act.

``Controller.run_session`` blocks until the kill switch trips, so the
launcher runs it on Razor Enhanced's own script thread. That means Razor
Enhanced's Stop button ends the loop too, as a second kill switch.
"""

import threading
import time

from jevanced import actions, tasks
from jevanced.jev.client import JevAuthError, JevError

IDLE = "idle"
RUNNING = "running"
STOPPED = "stopped"
ERROR = "error"


class _Fatal(Exception):
    """Stop the session with this message; retrying won't help."""


class Controller(object):
    def __init__(self, game, killswitch, log, clock=time.time):
        self.game = game
        self.killswitch = killswitch
        self.log = log
        self._clock = clock
        self._lock = threading.Lock()
        self._status = IDLE
        self._detail = ""
        self._ticks = 0
        self._error_streak = 0
        self._last_action = ""
        self._dry_run = True
        self._last_note = ""

    # ---- status for the UI --------------------------------------------

    def snapshot(self):
        with self._lock:
            return {
                "status": self._status,
                "detail": self._detail,
                "ticks": self._ticks,
                "error_streak": self._error_streak,
                "last_action": self._last_action,
                "dry_run": self._dry_run,
            }

    def _set(self, **values):
        with self._lock:
            for key, value in values.items():
                setattr(self, "_" + key, value)

    # ---- the loop -------------------------------------------------------

    def run_session(self, client, get_settings):
        """Run until the kill switch trips. ``get_settings`` is called every
        tick so changes made in the UI apply straight away."""
        self._set(status=RUNNING, detail="", ticks=0, error_streak=0,
                  last_action="")
        settings = get_settings()
        self.log.info("Started: {0}. {1} is deciding.".format(
            tasks.label(settings.task), client.display_name))
        if settings.task == tasks.LUMBERJACK and settings.wood_goal:
            self.log.info("Stopping at {0} wood.".format(settings.wood_goal))
        if settings.instructions:
            self.log.info("Your instructions: " + settings.instructions)
        self.game.notify("started; use the jevanced window's STOP button to stop")
        fatal = None
        try:
            while not self.killswitch.tripped:
                settings = get_settings()
                pause_s = settings.tick_interval_ms / 1000.0
                try:
                    pause_s = max(pause_s, self.tick(client, settings))
                    self._set(error_streak=0)
                except _Fatal as exc:
                    fatal = str(exc)
                    self.killswitch.trip(fatal)
                    break
                except Exception as exc:
                    streak = self.snapshot()["error_streak"] + 1
                    self._set(error_streak=streak)
                    self.log.error("Tick failed ({0} in a row): {1}".format(streak, exc))
                    if streak >= settings.max_consecutive_errors:
                        fatal = ("Stopped after {0} failures in a row. "
                                 "Last one: {1}".format(streak, exc))
                        self.killswitch.trip(fatal)
                        break
                if self.killswitch.wait(pause_s):
                    break
        except BaseException as exc:
            # Razor Enhanced stopping the script lands here. Trip the switch
            # so nothing else acts, then let it propagate.
            self.killswitch.trip("Script stopped: {0}".format(type(exc).__name__))
            raise
        finally:
            reason = fatal or self.killswitch.reason or "Stopped"
            self._set(status=ERROR if fatal else STOPPED, detail=reason)
            if fatal:
                self.log.error(reason)
            else:
                self.log.info("Stopped: " + reason)
            self.game.notify("stopped: " + reason)

    def tick(self, client, settings):
        """One decision. Returns extra seconds to wait before the next."""
        self._dry_run = settings.dry_run
        if not self.game.is_connected():
            raise _Fatal("Not connected to a shard.")
        state = self.game.read_state(settings.scan_range,
                                     trees=settings.task == tasks.LUMBERJACK)
        if state.player.is_ghost:
            raise _Fatal("Your character is dead, so jevanced stopped.")

        seen = state.to_dict()
        seen["task"] = {"name": settings.task, "instructions": settings.instructions,
                        "wood_goal": settings.wood_goal}
        try:
            proposed = client.decide(seen)
        except JevAuthError as exc:
            raise _Fatal("Jev rejected the API key: {0}".format(exc))
        except JevError as exc:
            raise RuntimeError("Jev: {0}".format(exc))
        note = getattr(client, "last_note", "")
        if note and note != self._last_note:
            self.log.info("Jev: " + note)
        self._last_note = note

        try:
            action = actions.validate(proposed, settings.allowed_actions())
        except actions.InvalidAction as exc:
            raise RuntimeError("Ignored an action Jev asked for: {0}".format(exc))

        # Jev may have taken a while; re-check before touching the game.
        if self.killswitch.tripped:
            self.log.info("Kill switch tripped; did not " + actions.describe(action))
            return 0.0

        summary = actions.describe(action)
        self._set(ticks=self.snapshot()["ticks"] + 1, last_action=summary)
        kind = action["type"]
        if kind == "stop":
            self.killswitch.trip("Finished: " + (action["reason"] or "no reason given"))
            return 0.0
        if kind == "wait":
            return action["ms"] / 1000.0
        if settings.dry_run:
            self.log.info("Dry run, would " + summary)
            return 0.0
        result = self.game.execute(action)
        if result == "ok":
            self.log.info(summary)
        else:
            self.log.warn("{0}: {1}".format(summary, result))
        return 0.0
