"""Offline stand-in for Jev, used until Typesafe's API docs are available.

It never touches the network. It exists so the Razor Enhanced plumbing
(state reading, action execution, kill switch, UI) can be exercised in the
client before the real Jev is wired up. Its behaviour is deliberately
harmless: it bandages the character when hurt and otherwise waits. It
never attacks, moves, or speaks.
"""

from jevanced.jev.client import JevClient, KeyCheck

BANDAGE_ITEM_ID = 0x0E21
HEAL_BELOW = 0.6
BANDAGE_COOLDOWN_S = 10.0


class StubJevClient(JevClient):
    display_name = "Offline stub (not Jev)"

    def __init__(self, api_key):
        self._has_key = bool(api_key)
        self._last_bandage_at = None

    def check_key(self):
        return KeyCheck(False, "Key saved. It can't be verified until jevanced "
                               "is connected to Jev's API; the offline stub is "
                               "making decisions for now.")

    def decide(self, state):
        player = state.get("player", {})
        hits = player.get("hits", 0)
        hits_max = player.get("hits_max", 0)
        now = state.get("timestamp", 0.0)
        hurt = hits_max > 0 and float(hits) / hits_max < HEAL_BELOW
        cooled = (self._last_bandage_at is None
                  or now - self._last_bandage_at >= BANDAGE_COOLDOWN_S)
        if hurt and cooled and not player.get("is_ghost"):
            for item in state.get("backpack", []):
                if item.get("item_id") == BANDAGE_ITEM_ID:
                    self._last_bandage_at = now
                    return {"type": "use_item", "serial": item["serial"],
                            "target": "self"}
        return {"type": "wait", "ms": 1000}
