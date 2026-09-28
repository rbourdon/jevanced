import unittest

from jevanced import actions
from jevanced.actions import InvalidAction, validate


class ValidateTest(unittest.TestCase):
    def test_accepts_each_known_shape(self):
        cases = [
            {"type": "wait", "ms": 500},
            {"type": "walk", "direction": "North"},
            {"type": "move_to", "x": 1000, "y": 2000, "z": -5},
            {"type": "use_skill", "skill": "Hiding"},
            {"type": "cast", "spell": "Greater Heal", "target": "self"},
            {"type": "use_item", "serial": 5, "target": 6},
            {"type": "use_item", "serial": 5, "target": {"x": 1, "y": 2, "z": 0, "tile": 0x0CD0}},
            {"type": "equip", "serial": 5},
            {"type": "war_mode", "on": False},
            {"type": "stop", "reason": "done"},
        ]
        for case in cases:
            self.assertEqual(validate(case)["type"], case["type"])

    def test_drops_unknown_fields(self):
        clean = validate({"type": "walk", "direction": "North", "extra": "x"})
        self.assertEqual(clean, {"type": "walk", "direction": "North"})

    def test_rejects_unknown_type(self):
        with self.assertRaises(InvalidAction):
            validate({"type": "drop_everything"})

    def test_there_is_no_attack_action(self):
        with self.assertRaises(InvalidAction):
            validate({"type": "attack", "serial": 9}, set(actions.ALL_ACTION_TYPES))

    def test_rejects_non_dict(self):
        with self.assertRaises(InvalidAction):
            validate(["walk", "North"])

    def test_speech_is_off_by_default(self):
        with self.assertRaises(InvalidAction):
            validate({"type": "say", "text": "hi"})
        allowed = set(actions.DEFAULT_ALLOWED) | {"say"}
        self.assertEqual(validate({"type": "say", "text": " hi "}, allowed)["text"], "hi")

    def test_speech_limits(self):
        allowed = set(actions.ALL_ACTION_TYPES)
        for text in ["", "   ", "a\nb", "x" * 121, 5]:
            with self.assertRaises(InvalidAction):
                validate({"type": "say", "text": text}, allowed)

    def test_bad_values(self):
        bad = [
            {"type": "wait", "ms": -1},
            {"type": "wait", "ms": 60000},
            {"type": "wait", "ms": "10"},
            {"type": "use_item", "serial": 0},
            {"type": "use_item", "serial": True},
            {"type": "use_item", "serial": "0x1"},
            {"type": "walk", "direction": "north"},
            {"type": "move_to", "x": 1, "y": 2},
            {"type": "move_to", "x": 1, "y": 99999, "z": 0},
            {"type": "use_skill", "skill": "Hiding; drop"},
            {"type": "use_skill", "skill": ""},
            {"type": "cast", "spell": "Heal", "target": "everyone"},
            {"type": "use_item", "serial": 5, "target": {"x": 1, "y": 2, "z": 0}},
            {"type": "use_item", "serial": 5, "target": {"x": 1, "y": 2, "z": 0, "tile": 0}},
            {"type": "equip", "serial": -1},
            {"type": "use_item", "serial": 1, "target": -4},
            {"type": "war_mode", "on": "yes"},
        ]
        for case in bad:
            with self.assertRaises(InvalidAction, msg=repr(case)):
                validate(case)

    def test_wait_defaults(self):
        self.assertEqual(validate({"type": "wait"}), {"type": "wait", "ms": 1000})


class DescribeTest(unittest.TestCase):
    def test_describe(self):
        self.assertEqual(actions.describe(validate({"type": "walk", "direction": "East"})),
                         "walk East")
        self.assertEqual(actions.describe(validate({"type": "use_item", "serial": 1, "target": "self"})),
                         "use item 0x00000001 on self")
        self.assertEqual(actions.describe(validate(
            {"type": "use_item", "serial": 1, "target": {"x": 5, "y": 6, "z": 0, "tile": 3280}})),
            "use item 0x00000001 on tile (5, 6)")
        self.assertEqual(actions.describe(validate({"type": "equip", "serial": 2})),
                         "equip 0x00000002")
        self.assertEqual(actions.describe(validate({"type": "stop"})),
                         "stop (no reason given)")


if __name__ == "__main__":
    unittest.main()
