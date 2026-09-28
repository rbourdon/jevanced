"""Test doubles for the game adapter and Jev client."""

from jevanced.jev.client import JevClient, KeyCheck
from jevanced.state import GameState, ItemState, PlayerState


def make_state(hits=100, hits_max=100, is_ghost=False, backpack=None,
               timestamp=0.0):
    player = PlayerState(serial=1, name="Tester", hits=hits, hits_max=hits_max,
                         position=(100, 100, 0), is_ghost=is_ghost)
    return GameState(player=player, backpack=backpack or [], timestamp=timestamp)


class FakeGame(object):
    def __init__(self, state=None, connected=True):
        self.state = state or make_state()
        self.connected = connected
        self.executed = []
        self.notices = []
        self.read_error = None
        self.on_read = None

    def is_connected(self):
        return self.connected

    def read_state(self, scan_range=12):
        if self.on_read is not None:
            self.on_read()
        if self.read_error is not None:
            raise self.read_error
        return self.state

    def execute(self, action):
        self.executed.append(action)
        return "ok"

    def notify(self, text):
        self.notices.append(text)


class ScriptedClient(JevClient):
    """Returns queued actions in order, then waits; can raise instead."""
    display_name = "Scripted"

    def __init__(self, actions=None, check=None, check_error=None):
        self.actions = list(actions or [])
        self.check = check or KeyCheck(True, "ok")
        self.check_error = check_error
        self.decided = 0
        self.closed = False
        self.after_decide = None

    def check_key(self):
        if self.check_error is not None:
            raise self.check_error
        return self.check

    def decide(self, state):
        self.decided += 1
        result = self.actions.pop(0) if self.actions else {"type": "wait", "ms": 0}
        if self.after_decide is not None:
            self.after_decide()
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


def bandage(serial=0x40000001, amount=10):
    return ItemState(serial=serial, item_id=0x0E21, name="bandage", amount=amount)
