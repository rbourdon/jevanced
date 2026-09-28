"""The only module that calls the Razor Enhanced API.

Razor Enhanced injects its API objects (Player, Mobiles, Items, Target,
Spells, Journal, Misc) into the script that it runs, not into modules that
script imports. The launcher collects them into a ``RazorApi`` and hands
that to ``RazorAdapter``; everything else in jevanced talks to the game
through the adapter's two methods, ``read_state`` and ``execute``.

NOT YET VERIFIED IN THE CLIENT. The calls below follow Razor Enhanced's
published API, but nothing here has been run against a live UO client yet.
Reads are defensive (a missing property reads as a default) so a version
difference degrades one field rather than stopping the loop.
"""

import time

from jevanced.state import GameState, ItemState, JournalLine, MobileState, PlayerState

MAX_MOBILES = 25
MAX_GROUND_ITEMS = 25
MAX_BACKPACK_ITEMS = 60
MAX_JOURNAL_LINES = 20
TARGET_TIMEOUT_MS = 2000


class RazorApi(object):
    """Holder for the Razor Enhanced API objects the launcher passes in."""

    def __init__(self, Player, Mobiles, Items, Target, Spells, Journal, Misc):
        self.Player = Player
        self.Mobiles = Mobiles
        self.Items = Items
        self.Target = Target
        self.Spells = Spells
        self.Journal = Journal
        self.Misc = Misc


def _get(obj, name, default=None):
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    return default if value is None else value


def _position(obj):
    pos = _get(obj, "Position")
    if pos is None:
        return (0, 0, 0)
    return (int(_get(pos, "X", 0)), int(_get(pos, "Y", 0)), int(_get(pos, "Z", 0)))


class RazorAdapter(object):
    def __init__(self, api, clock=time.time):
        self.api = api
        self._clock = clock
        self._journal_after = None

    # ---- reading -------------------------------------------------------

    def is_connected(self):
        return bool(_get(self.api.Player, "Connected", False))

    def read_state(self, scan_range=12):
        player = self.api.Player
        me = PlayerState(
            serial=int(_get(player, "Serial", 0)),
            name=str(_get(player, "Name", "")),
            hits=int(_get(player, "Hits", 0)),
            hits_max=int(_get(player, "HitsMax", 0)),
            mana=int(_get(player, "Mana", 0)),
            mana_max=int(_get(player, "ManaMax", 0)),
            stam=int(_get(player, "Stam", 0)),
            stam_max=int(_get(player, "StamMax", 0)),
            position=_position(player),
            map_id=int(_get(player, "Map", 0)),
            war_mode=bool(_get(player, "WarMode", False)),
            is_ghost=bool(_get(player, "IsGhost", False)),
            poisoned=bool(_get(player, "Poisoned", False)),
            weight=int(_get(player, "Weight", 0)),
            max_weight=int(_get(player, "MaxWeight", 0)),
            gold=int(_get(player, "Gold", 0)),
        )
        return GameState(
            player=me,
            mobiles=self._read_mobiles(scan_range, me.serial),
            ground_items=self._read_ground_items(scan_range),
            backpack=self._read_backpack(),
            journal=self._read_journal(),
            connected=self.is_connected(),
            timestamp=self._clock(),
        )

    def _read_mobiles(self, scan_range, own_serial):
        mobiles = self.api.Mobiles
        flt = mobiles.Filter()
        flt.Enabled = True
        flt.RangeMax = scan_range
        found = []
        for mob in list(mobiles.ApplyFilter(flt) or [])[:MAX_MOBILES + 1]:
            serial = int(_get(mob, "Serial", 0))
            if not serial or serial == own_serial:
                continue
            found.append(MobileState(
                serial=serial,
                name=str(_get(mob, "Name", "")),
                hits=int(_get(mob, "Hits", 0)),
                hits_max=int(_get(mob, "HitsMax", 0)),
                notoriety=int(_get(mob, "Notoriety", 0)),
                position=_position(mob),
                body=int(_get(mob, "Body", _get(mob, "MobileID", 0))),
            ))
        return found[:MAX_MOBILES]

    def _read_ground_items(self, scan_range):
        items = self.api.Items
        flt = items.Filter()
        flt.Enabled = True
        flt.OnGround = 1
        flt.RangeMax = scan_range
        found = []
        for item in list(items.ApplyFilter(flt) or [])[:MAX_GROUND_ITEMS]:
            found.append(self._item(item, with_position=True))
        return found

    def _read_backpack(self):
        backpack = _get(self.api.Player, "Backpack")
        if backpack is None:
            return []
        contents = _get(backpack, "Contains", []) or []
        return [self._item(i) for i in list(contents)[:MAX_BACKPACK_ITEMS]]

    def _item(self, item, with_position=False):
        return ItemState(
            serial=int(_get(item, "Serial", 0)),
            item_id=int(_get(item, "ItemID", 0)),
            name=str(_get(item, "Name", "")),
            amount=int(_get(item, "Amount", 1)),
            position=_position(item) if with_position else (0, 0, 0),
        )

    def _read_journal(self):
        journal = self.api.Journal
        try:
            if self._journal_after is None:
                # First read: skip history, only report what's new from here.
                self._journal_after = float(self._clock())
                return []
            entries = list(journal.GetJournalEntry(self._journal_after) or [])
        except Exception:
            return []
        lines = []
        for entry in entries[-MAX_JOURNAL_LINES:]:
            lines.append(JournalLine(
                text=str(_get(entry, "Text", "")),
                speaker=str(_get(entry, "Name", "")),
                serial=int(_get(entry, "Serial", 0)),
            ))
        if entries:
            self._journal_after = float(_get(entries[-1], "Timestamp", self._clock()))
        return lines

    # ---- acting --------------------------------------------------------

    def notify(self, text):
        """Show a message in the UO client's system area (only you see it)."""
        try:
            self.api.Misc.SendMessage("[jevanced] " + text, 68)
        except Exception:
            pass

    def execute(self, action):
        """Carry out one validated action. Returns a short result string."""
        api = self.api
        kind = action["type"]
        if kind == "attack":
            api.Player.Attack(action["serial"])
        elif kind == "walk":
            if not api.Player.Walk(action["direction"]):
                return "blocked"
        elif kind == "move_to":
            api.Player.PathFindTo(action["x"], action["y"], action["z"])
        elif kind == "use_skill":
            api.Player.UseSkill(action["skill"])
            return self._apply_target(action.get("target"))
        elif kind == "cast":
            api.Spells.Cast(action["spell"])
            return self._apply_target(action.get("target"))
        elif kind == "use_item":
            api.Items.UseItem(action["serial"])
            return self._apply_target(action.get("target"))
        elif kind == "war_mode":
            api.Player.SetWarMode(action["on"])
        elif kind == "say":
            api.Player.ChatSay(action["text"])
        else:
            raise ValueError("adapter can't execute {0!r}".format(kind))
        return "ok"

    def _apply_target(self, target):
        if target is None:
            return "ok"
        tgt = self.api.Target
        if not tgt.WaitForTarget(TARGET_TIMEOUT_MS, True):
            return "no target cursor"
        if target == "self":
            tgt.Self()
        else:
            tgt.TargetExecute(target)
        return "ok"
