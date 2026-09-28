"""The only module that calls the Razor Enhanced API.

Razor Enhanced injects its API objects (Player, Mobiles, Items, Target,
Spells, Journal, Misc) into the script that it runs, not into modules that
script imports. The launcher collects them into a ``RazorApi`` and hands
that to ``RazorAdapter``; everything else in jevanced talks to the game
through the adapter's two methods, ``read_state`` and ``execute``.

Checked against Razor Enhanced 1.0.0.14 running in ClassicUO. Two things
learned there:

- Razor Enhanced's ``Player`` object answers ``Player.Hits`` but raises
  AttributeError when the same property is looked up with the getattr
  builtin, so every read here is a plain attribute access in a lambda.
- ``Player.Walk(direction)`` only turns the character when it faces
  another way, and returns False if called again too soon, so a walk
  action turns first and retries the step once.
- Creature kinds (monster, animal...) come from the client's mobtypes.txt,
  found through the Ultima library Razor Enhanced has already loaded.
- Reads are defensive (a failing property reads as a default) so a version
  difference degrades one field rather than stopping the loop.
"""

import io
import time

from jevanced.bodykinds import parse_mobtypes
from jevanced.state import (
    GameState,
    ItemState,
    JournalLine,
    MobileState,
    PlayerState,
)

MAX_MOBILES = 25
MAX_GROUND_ITEMS = 25
MAX_BACKPACK_ITEMS = 60
MAX_JOURNAL_LINES = 20
TARGET_TIMEOUT_MS = 2000
WALK_RETRY_MS = 250


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

    def mobtypes_path(self):
        """Path to the client's mobtypes.txt, or None if it can't be found."""
        try:
            import clr
            from System import AppDomain

            for assembly in AppDomain.CurrentDomain.GetAssemblies():
                if assembly.GetName().Name == "Ultima":
                    clr.AddReference(assembly)
                    from Ultima import Files
                    return Files.GetFilePath("mobtypes.txt")
        except Exception:
            pass
        return None


def _read(fn, default=None):
    """Call ``fn`` (a lambda doing one attribute read); default on failure."""
    try:
        value = fn()
    except Exception:
        return default
    return default if value is None else value


def _int(fn, default=0):
    try:
        return int(_read(fn, default))
    except (TypeError, ValueError):
        return default


def _position(fn):
    pos = _read(fn)
    if pos is None:
        return (0, 0, 0)
    return (_int(lambda: pos.X), _int(lambda: pos.Y), _int(lambda: pos.Z))


class RazorAdapter(object):
    def __init__(self, api, clock=time.time):
        self.api = api
        self._clock = clock
        self._journal_after = None
        self._body_kinds = None

    # ---- reading -------------------------------------------------------

    def is_connected(self):
        player = self.api.Player
        return bool(_read(lambda: player.Connected, False))

    def read_state(self, scan_range=12):
        p = self.api.Player
        me = PlayerState(
            serial=_int(lambda: p.Serial),
            name=str(_read(lambda: p.Name, "")),
            hits=_int(lambda: p.Hits),
            hits_max=_int(lambda: p.HitsMax),
            mana=_int(lambda: p.Mana),
            mana_max=_int(lambda: p.ManaMax),
            stam=_int(lambda: p.Stam),
            stam_max=_int(lambda: p.StamMax),
            position=_position(lambda: p.Position),
            map_id=_int(lambda: p.Map),
            war_mode=bool(_read(lambda: p.WarMode, False)),
            is_ghost=bool(_read(lambda: p.IsGhost, False)),
            poisoned=bool(_read(lambda: p.Poisoned, False)),
            weight=_int(lambda: p.Weight),
            max_weight=_int(lambda: p.MaxWeight),
            gold=_int(lambda: p.Gold),
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
            serial = _int(lambda: mob.Serial)
            if not serial or serial == own_serial:
                continue
            found.append(MobileState(
                serial=serial,
                name=str(_read(lambda: mob.Name, "")),
                hits=_int(lambda: mob.Hits),
                hits_max=_int(lambda: mob.HitsMax),
                notoriety=_int(lambda: mob.Notoriety),
                position=_position(lambda: mob.Position),
                body=_int(lambda: mob.Body),
                kind=self._kind(_int(lambda: mob.Body)),
            ))
        return found[:MAX_MOBILES]

    def _kind(self, body):
        if self._body_kinds is None:
            self._body_kinds = self._load_body_kinds()
        return self._body_kinds.get(body, "unknown")

    def _load_body_kinds(self):
        path = self.api.mobtypes_path()
        if not path:
            return {}
        try:
            with io.open(path, encoding="latin-1") as handle:
                return parse_mobtypes(handle.read())
        except (IOError, OSError):
            return {}

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
        player = self.api.Player
        backpack = _read(lambda: player.Backpack)
        if backpack is None:
            return []
        contents = _read(lambda: backpack.Contains, []) or []
        return [self._item(i) for i in list(contents)[:MAX_BACKPACK_ITEMS]]

    def _item(self, item, with_position=False):
        return ItemState(
            serial=_int(lambda: item.Serial),
            item_id=_int(lambda: item.ItemID),
            name=str(_read(lambda: item.Name, "")),
            amount=_int(lambda: item.Amount, 1),
            position=_position(lambda: item.Position) if with_position else (0, 0, 0),
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
                text=str(_read(lambda: entry.Text, "")),
                speaker=str(_read(lambda: entry.Name, "")),
                serial=_int(lambda: entry.Serial),
            ))
        if entries:
            last = entries[-1]
            self._journal_after = float(_read(lambda: last.Timestamp, self._clock()))
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
        if kind == "walk":
            return self._walk(action["direction"])
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

    def _walk(self, direction):
        player = self.api.Player
        if _read(lambda: player.Direction) != direction:
            player.Walk(direction)  # turn to face it; this doesn't step
        before = _position(lambda: player.Position)
        if not player.Walk(direction):
            self.api.Misc.Pause(WALK_RETRY_MS)
            player.Walk(direction)
        if _position(lambda: player.Position) == before:
            return "blocked"
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
