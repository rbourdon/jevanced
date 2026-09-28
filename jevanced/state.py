"""Plain-data snapshot of the game world, as read through the adapter.

This is what jevanced sends to Jev each tick. It holds no references to
Razor Enhanced objects, so it can be built in tests and serialised to JSON.
"""

NOTORIETY = {
    1: "innocent",
    2: "ally",
    3: "attackable",
    4: "criminal",
    5: "enemy",
    6: "murderer",
    7: "invulnerable",
}


def notoriety_name(value):
    return NOTORIETY.get(value, "unknown")


def distance(a, b):
    """UO tile distance: the larger of the x and y offsets."""
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class PlayerState(object):
    def __init__(self, serial=0, name="", hits=0, hits_max=0, mana=0,
                 mana_max=0, stam=0, stam_max=0, position=(0, 0, 0), map_id=0,
                 war_mode=False, is_ghost=False, poisoned=False, weight=0,
                 max_weight=0, gold=0):
        self.serial = serial
        self.name = name
        self.hits = hits
        self.hits_max = hits_max
        self.mana = mana
        self.mana_max = mana_max
        self.stam = stam
        self.stam_max = stam_max
        self.position = tuple(position)
        self.map_id = map_id
        self.war_mode = war_mode
        self.is_ghost = is_ghost
        self.poisoned = poisoned
        self.weight = weight
        self.max_weight = max_weight
        self.gold = gold

    def hits_fraction(self):
        if not self.hits_max:
            return 1.0
        return float(self.hits) / float(self.hits_max)

    def to_dict(self):
        return {
            "serial": self.serial,
            "name": self.name,
            "hits": self.hits,
            "hits_max": self.hits_max,
            "mana": self.mana,
            "mana_max": self.mana_max,
            "stam": self.stam,
            "stam_max": self.stam_max,
            "position": list(self.position),
            "map": self.map_id,
            "war_mode": self.war_mode,
            "is_ghost": self.is_ghost,
            "poisoned": self.poisoned,
            "weight": self.weight,
            "max_weight": self.max_weight,
            "gold": self.gold,
        }


class MobileState(object):
    def __init__(self, serial, name="", hits=0, hits_max=0, notoriety=0,
                 position=(0, 0, 0), body=0):
        self.serial = serial
        self.name = name
        self.hits = hits
        self.hits_max = hits_max
        self.notoriety = notoriety
        self.position = tuple(position)
        self.body = body

    def to_dict(self, origin=None):
        d = {
            "serial": self.serial,
            "name": self.name,
            "hits": self.hits,
            "hits_max": self.hits_max,
            "notoriety": notoriety_name(self.notoriety),
            "position": list(self.position),
            "body": self.body,
        }
        if origin is not None:
            d["distance"] = distance(origin, self.position)
        return d


class ItemState(object):
    def __init__(self, serial, item_id=0, name="", amount=1,
                 position=(0, 0, 0)):
        self.serial = serial
        self.item_id = item_id
        self.name = name
        self.amount = amount
        self.position = tuple(position)

    def to_dict(self, origin=None):
        d = {
            "serial": self.serial,
            "item_id": self.item_id,
            "name": self.name,
            "amount": self.amount,
        }
        if origin is not None:
            d["position"] = list(self.position)
            d["distance"] = distance(origin, self.position)
        return d


class JournalLine(object):
    def __init__(self, text, speaker="", serial=0):
        self.text = text
        self.speaker = speaker
        self.serial = serial

    def to_dict(self):
        return {"text": self.text, "speaker": self.speaker, "serial": self.serial}


class GameState(object):
    """Everything jevanced knows about the world at one tick."""

    def __init__(self, player, mobiles=None, ground_items=None, backpack=None,
                 journal=None, connected=True, timestamp=0.0):
        self.player = player
        self.mobiles = list(mobiles or [])
        self.ground_items = list(ground_items or [])
        self.backpack = list(backpack or [])
        self.journal = list(journal or [])
        self.connected = connected
        self.timestamp = timestamp

    def find_backpack_item(self, item_id):
        for item in self.backpack:
            if item.item_id == item_id:
                return item
        return None

    def to_dict(self):
        origin = self.player.position
        mobiles = sorted(self.mobiles,
                         key=lambda m: distance(origin, m.position))
        items = sorted(self.ground_items,
                       key=lambda i: distance(origin, i.position))
        return {
            "timestamp": self.timestamp,
            "connected": self.connected,
            "player": self.player.to_dict(),
            "mobiles": [m.to_dict(origin) for m in mobiles],
            "ground_items": [i.to_dict(origin) for i in items],
            "backpack": [i.to_dict() for i in self.backpack],
            "journal": [line.to_dict() for line in self.journal],
        }
