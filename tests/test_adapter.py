"""Adapter tests against hand-made fakes of the Razor Enhanced API.

These check jevanced's own translation logic. They can't prove the real
Razor Enhanced API behaves the way the fakes do; that needs the client.
"""

import unittest

from jevanced.razor.adapter import RazorAdapter, RazorApi


class Obj(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


def pos(x, y, z=0):
    return Obj(X=x, Y=y, Z=z)


class Recorder(object):
    def __init__(self, **returns):
        self.calls = []
        self.returns = returns

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*args):
            self.calls.append((name,) + args)
            return self.returns.get(name)
        return call


STEPS = {"North": (0, -1), "South": (0, 1), "East": (1, 0), "West": (-1, 0)}


class FakePlayer(Recorder):
    """Walks like Razor Enhanced's Player: a new direction only turns."""

    def __init__(self):
        Recorder.__init__(self)
        self.Direction = "North"
        self.blocked = False
        self.busy = 0  # how many Walk calls fail as "too soon"
        self.Serial = 1
        self.Name = "Tester"
        self.Hits, self.HitsMax = 40, 80
        self.Mana, self.ManaMax, self.Stam, self.StamMax = 1, 2, 3, 4
        self.Position = pos(100, 100, 5)
        self.Map = 1
        self.WarMode = False
        self.IsGhost = False
        self.Poisoned = True
        self.Weight, self.MaxWeight, self.Gold = 50, 400, 12
        self.Connected = True
        self.Backpack = Obj(Contains=[Obj(Serial=9, ItemID=0x0E21, Name="bandage", Amount=30)])

    def Walk(self, direction):
        self.calls.append(("Walk", direction))
        if self.busy:
            self.busy -= 1
            return False
        if direction != self.Direction:
            self.Direction = direction
            return True
        if self.blocked:
            return False
        dx, dy = STEPS[direction]
        p = self.Position
        self.Position = pos(p.X + dx, p.Y + dy, p.Z)
        return True


class FakeFinder(object):
    def __init__(self, results):
        self.results = results
        self.last_filter = None

    def Filter(self):
        return Obj()

    def ApplyFilter(self, flt):
        self.last_filter = flt
        return self.results


class FakeJournal(object):
    def __init__(self):
        self.entries = []
        self.asked = []

    def GetJournalEntry(self, after):
        self.asked.append(after)
        return [e for e in self.entries if e.Timestamp > after]


class FakeTarget(Recorder):
    def __init__(self, cursor=True):
        Recorder.__init__(self, WaitForTarget=cursor)


def make_adapter(cursor=True):
    player = FakePlayer()
    mobiles = FakeFinder([
        Obj(Serial=1, Name="Tester", Position=pos(100, 100)),  # ourselves
        Obj(Serial=2, Name="Orc", Hits=20, HitsMax=25, Notoriety=5,
            Position=pos(103, 101), Body=17),
    ])
    items = FakeFinder([Obj(Serial=3, ItemID=0xEED, Name="gold", Amount=7,
                            Position=pos(101, 99))])
    journal = FakeJournal()
    api = RazorApi(Player=player, Mobiles=mobiles, Items=Recorder(), Target=FakeTarget(cursor),
                   Spells=Recorder(), Journal=journal, Misc=Recorder())
    api.Items.Filter = items.Filter
    api.Items.ApplyFilter = items.ApplyFilter
    clock = [10.0]
    adapter = RazorAdapter(api, clock=lambda: clock[0])
    return adapter, api, clock


class ReadStateTest(unittest.TestCase):
    def test_reads_player_mobiles_items_backpack(self):
        adapter, api, _ = make_adapter()
        state = adapter.read_state(scan_range=8)
        self.assertEqual(state.player.hits, 40)
        self.assertEqual(state.player.position, (100, 100, 5))
        self.assertTrue(state.player.poisoned)
        self.assertEqual([m.name for m in state.mobiles], ["Orc"])
        self.assertEqual(api.Mobiles.last_filter.RangeMax, 8)
        self.assertEqual(state.ground_items[0].amount, 7)
        self.assertEqual(state.backpack[0].item_id, 0x0E21)
        data = state.to_dict()
        self.assertEqual(data["mobiles"][0]["notoriety"], "enemy")
        self.assertEqual(data["mobiles"][0]["distance"], 3)

    def test_creature_kind_comes_from_mobtypes(self):
        import os
        import tempfile
        adapter, api, _ = make_adapter()
        handle, path = tempfile.mkstemp()
        os.write(handle, b"17\tMONSTER\t0\n")
        os.close(handle)
        try:
            api.mobtypes_path = lambda: path
            self.assertEqual(adapter.read_state().mobiles[0].kind, "monster")
        finally:
            os.remove(path)

    def test_creature_kind_unknown_without_mobtypes(self):
        adapter, api, _ = make_adapter()
        api.mobtypes_path = lambda: None
        self.assertEqual(adapter.read_state().mobiles[0].kind, "unknown")

    def test_missing_properties_read_as_defaults(self):
        adapter, api, _ = make_adapter()
        api.Player = Obj(Serial=1, Name=None, Position=pos(5, 6))
        state = adapter.read_state()
        self.assertEqual(state.player.name, "")
        self.assertEqual(state.player.hits, 0)
        self.assertFalse(state.player.poisoned)
        self.assertFalse(state.connected)
        self.assertEqual(state.backpack, [])

    def test_journal_only_reports_new_lines(self):
        adapter, api, clock = make_adapter()
        api.Journal.entries = [Obj(Text="old", Name="x", Serial=0, Timestamp=5.0)]
        self.assertEqual(adapter.read_state().journal, [])
        api.Journal.entries.append(Obj(Text="You see an orc", Name="", Serial=0, Timestamp=11.0))
        lines = adapter.read_state().journal
        self.assertEqual([line.text for line in lines], ["You see an orc"])
        self.assertEqual(adapter.read_state().journal, [])

    def test_journal_errors_are_ignored(self):
        adapter, api, _ = make_adapter()
        api.Journal = None
        adapter.read_state()
        self.assertEqual(adapter.read_state().journal, [])


class ExecuteTest(unittest.TestCase):
    def test_actions_map_to_razor_calls(self):
        adapter, api, _ = make_adapter()
        adapter.execute({"type": "walk", "direction": "North"})
        adapter.execute({"type": "move_to", "x": 1, "y": 2, "z": 3})
        adapter.execute({"type": "war_mode", "on": True})
        adapter.execute({"type": "say", "text": "hail"})
        self.assertEqual([c for c in api.Player.calls], [
            ("Walk", "North"), ("PathFindTo", 1, 2, 3),
            ("SetWarMode", True), ("ChatSay", "hail"),
        ])

    def test_targeted_actions(self):
        adapter, api, _ = make_adapter()
        self.assertEqual(adapter.execute({"type": "use_item", "serial": 9, "target": "self"}), "ok")
        adapter.execute({"type": "cast", "spell": "Heal", "target": 2})
        adapter.execute({"type": "use_skill", "skill": "Hiding", "target": None})
        self.assertEqual(api.Items.calls, [("UseItem", 9)])
        self.assertEqual(api.Spells.calls, [("Cast", "Heal")])
        self.assertEqual(api.Player.calls, [("UseSkill", "Hiding")])
        names = [c[0] for c in api.Target.calls]
        self.assertEqual(names, ["WaitForTarget", "Self", "WaitForTarget", "TargetExecute"])

    def test_no_cursor_is_reported(self):
        adapter, api, _ = make_adapter(cursor=False)
        self.assertEqual(adapter.execute({"type": "use_item", "serial": 9, "target": "self"}),
                         "no target cursor")

    def test_walk_turns_then_steps(self):
        adapter, api, _ = make_adapter()
        self.assertEqual(adapter.execute({"type": "walk", "direction": "East"}), "ok")
        self.assertEqual(api.Player.calls, [("Walk", "East"), ("Walk", "East")])
        self.assertEqual(api.Player.Position.X, 101)

    def test_walk_retries_once_when_too_soon(self):
        adapter, api, _ = make_adapter()
        api.Player.busy = 1
        self.assertEqual(adapter.execute({"type": "walk", "direction": "North"}), "ok")
        self.assertEqual(api.Player.Position.Y, 99)
        self.assertEqual(api.Misc.calls[0][0], "Pause")

    def test_blocked_walk(self):
        adapter, api, _ = make_adapter()
        api.Player.blocked = True
        self.assertEqual(adapter.execute({"type": "walk", "direction": "East"}), "blocked")

    def test_unknown_action_raises(self):
        adapter, _, _ = make_adapter()
        with self.assertRaises(ValueError):
            adapter.execute({"type": "wait", "ms": 1})

    def test_notify_uses_misc(self):
        adapter, api, _ = make_adapter()
        adapter.notify("hi")
        self.assertEqual(api.Misc.calls[0][0], "SendMessage")


if __name__ == "__main__":
    unittest.main()
