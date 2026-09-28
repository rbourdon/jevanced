import unittest

from jevanced.jev import choices, lumberjack
from jevanced.state import GameState, ItemState, JournalLine, PlayerState, TreeState

AXE = 0x0F43
LOGS = 0x1BDD


def state(trees=((101, 100),), in_hand=True, in_pack=False, logs=0, weight=50,
          max_weight=300, journal=(), timestamp=100.0, instructions="", wood_goal=0,
          boards=0):
    player = PlayerState(serial=1, name="Me", hits=100, hits_max=100,
                         position=(100, 100, 0), weight=weight, max_weight=max_weight)
    equipped = [ItemState(serial=0x40000001, item_id=AXE, name="hatchet")] if in_hand else []
    pack = []
    if in_pack:
        pack.append(ItemState(serial=0x40000002, item_id=AXE, name="hatchet"))
    if logs:
        pack.append(ItemState(serial=0x40000003, item_id=LOGS, name="log", amount=logs))
    if boards:
        pack.append(ItemState(serial=0x40000004, item_id=0x1BD7, name="board", amount=boards))
    s = GameState(player=player, backpack=pack, equipped=equipped,
                  trees=[TreeState((x, y, 0), 0x0CD0) for x, y in trees],
                  journal=list(journal), timestamp=timestamp).to_dict()
    s["task"] = {"name": "lumberjack", "instructions": instructions, "wood_goal": wood_goal}
    return s


def keys(s, memory=None):
    return [o.key for o in choices.build_options(s, lumber=memory)]


def option(s, key, memory=None):
    return [o for o in choices.build_options(s, lumber=memory) if o.key == key][0]


def said(text):
    # How Razor Enhanced reports the shard's own messages.
    return JournalLine(text, speaker="System", serial=-1)


class OptionsTest(unittest.TestCase):
    def test_chops_a_tree_in_reach(self):
        self.assertEqual(keys(state()), ["wait", "chop"])
        self.assertEqual(option(state(), "chop").action, {
            "type": "use_item", "serial": 0x40000001,
            "target": {"x": 101, "y": 100, "z": 0, "tile": 0x0CD0}})

    def test_walks_beside_the_next_tree_when_none_is_in_reach(self):
        s = state(trees=[(106, 103)])
        self.assertEqual(keys(s), ["wait", "go_to_tree"])
        self.assertEqual(option(s, "go_to_tree").action,
                         {"type": "move_to", "x": 105, "y": 102, "z": 0})

    def test_equips_an_axe_from_the_pack(self):
        s = state(in_hand=False, in_pack=True)
        self.assertEqual(keys(s), ["wait", "equip_axe"])
        self.assertEqual(option(s, "equip_axe").action, {"type": "equip", "serial": 0x40000002})

    def test_makes_boards_when_nearly_full(self):
        s = state(logs=100, weight=270)
        self.assertEqual(keys(s), ["wait", "chop", "make_boards"])
        self.assertEqual(option(s, "make_boards").action["target"], 0x40000003)
        full = state(logs=100, weight=300)
        self.assertNotIn("chop", keys(full))

    def test_no_new_chop_until_the_last_one_answers(self):
        memory = lumberjack.Memory()
        memory.chopped({"position": [101, 100, 0]}, 100.0)
        self.assertEqual(keys(state(timestamp=103.0), memory), ["wait"])
        memory.observe(state(timestamp=104.0, journal=[
            said("You chop some ordinary logs and put them into your backpack.")]))
        self.assertEqual(keys(state(timestamp=104.0), memory), ["wait", "chop"])
        self.assertEqual(memory.last_result, "got logs")

    def test_a_chop_that_never_answers_times_out(self):
        memory = lumberjack.Memory()
        memory.chopped({"position": [101, 100, 0]}, 100.0)
        memory.observe(state(timestamp=100.0 + lumberjack.CHOP_TIMEOUT_S))
        self.assertIn("chop", keys(state(timestamp=110.0), memory))

    def test_an_empty_tree_empties_its_whole_bank(self):
        memory = lumberjack.Memory()
        s = state(trees=[(101, 100), (102, 101), (110, 100)])
        memory.chopped(s["trees"][0], 100.0)
        memory.observe(state(journal=[said("There's not enough wood here to harvest.")]))
        # (101, 100) and (102, 101) share a bank; (110, 100) doesn't.
        self.assertEqual(keys(s, memory), ["wait", "go_to_tree"])
        self.assertEqual(option(s, "go_to_tree", memory).action["x"], 109)
        # The wood regrows.
        later = state(trees=[(101, 100)], timestamp=100.0 + lumberjack.EMPTY_BANK_S + 1)
        self.assertIn("chop", keys(later, memory))

    def test_gives_up_on_a_tree_it_cant_reach(self):
        memory = lumberjack.Memory()
        s = state(trees=[(106, 100), (100, 108)])
        for _ in range(lumberjack.MAX_WALKS_TO_TREE):
            memory.walked_to(s["trees"][0])
        self.assertEqual(option(s, "go_to_tree", memory).action["y"], 107)

    def test_player_chat_is_not_read_as_a_result(self):
        memory = lumberjack.Memory()
        memory.chopped({"position": [101, 100, 0]}, 100.0)
        memory.observe(state(journal=[
            JournalLine("not enough wood here lol", speaker="Troll", serial=77),
            JournalLine("into your backpack", speaker="System", serial=78)]))
        self.assertTrue(memory.chopping())

    def test_a_full_pack_is_not_read_as_wood(self):
        memory = lumberjack.Memory()
        memory.chopped({"position": [101, 100, 0]}, 100.0)
        memory.observe(state(journal=[said("You can't place any wood into your backpack!")]))
        self.assertEqual(memory.last_result, "backpack can't hold more wood")
        self.assertEqual(memory.logs_cut, 0)

    def test_stop_is_offered_only_with_instructions(self):
        self.assertNotIn("stop", keys(state()))
        s = state(instructions="Stop if a player shows up")
        self.assertEqual(keys(s), ["wait", "chop", "stop"])

    def test_stay_safe_has_no_lumberjacking(self):
        s = state()
        s["task"] = {"name": "stay_safe", "instructions": ""}
        self.assertEqual(keys(s), ["wait"])


class FinishedTest(unittest.TestCase):
    def finished(self, s, memory=None):
        return lumberjack.finished(s, memory or lumberjack.Memory())

    def test_keeps_going_while_there_is_work(self):
        self.assertIsNone(self.finished(state(logs=50, wood_goal=150)))

    def test_stops_at_the_wood_goal_counting_boards(self):
        reason = self.finished(state(logs=40, boards=110, wood_goal=150))
        self.assertEqual(reason, "Done: carrying 150 wood, and you asked for 150.")

    def test_stops_without_an_axe(self):
        self.assertEqual(self.finished(state(in_hand=False)), "No axe to chop with.")

    def test_stops_when_too_heavy_with_nothing_to_cut(self):
        self.assertIn("too heavy", self.finished(state(boards=270, weight=300)))
        self.assertIsNone(self.finished(state(logs=130, weight=300)))  # boards will help

    def test_stops_when_no_tree_has_wood(self):
        self.assertIn("No trees", self.finished(state(trees=[])))

    def test_never_mid_chop(self):
        memory = lumberjack.Memory()
        memory.chopped({"position": [101, 100, 0]}, 100.0)
        self.assertIsNone(self.finished(state(trees=[], timestamp=101.0), memory))


class DescribeTest(unittest.TestCase):
    def test_describes_the_job_and_the_instructions(self):
        s = state(logs=40, weight=150, instructions="Stop at 200 logs")
        seen = choices.describe_state(s, choices.build_options(s))
        self.assertIn("Chop wood", seen["goal"])
        self.assertEqual(seen["player's instructions"], "Stop at 200 logs")
        self.assertEqual(seen["lumberjacking"], {
            "axe": "in your hands", "logs carried": 40, "boards carried": 0,
            "wood carried in all (logs and boards)": 40,
            "load": "150 of 300 stones (half full)", "chopping now": "no",
            "last chop": "none yet", "tree in reach with wood": "yes",
            "next tree": "none found nearby"})

    def test_shows_the_wood_goal(self):
        s = state(wood_goal=150)
        self.assertEqual(choices.describe_state(s, choices.build_options(s))["lumberjacking"]["wood wanted"], 150)

    def test_no_instructions_no_key(self):
        s = state()
        self.assertNotIn("player's instructions", choices.describe_state(s, choices.build_options(s)))


if __name__ == "__main__":
    unittest.main()
