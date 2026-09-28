import json
import unittest

from jevanced.state import GameState, ItemState, MobileState, PlayerState, distance


class StateTest(unittest.TestCase):
    def test_distance_is_chebyshev(self):
        self.assertEqual(distance((0, 0, 0), (3, -7, 20)), 7)

    def test_to_dict_sorts_by_distance_and_is_json(self):
        player = PlayerState(serial=1, name="Me", hits=50, hits_max=100,
                             position=(10, 10, 0))
        far = MobileState(serial=2, name="Far", notoriety=6, position=(20, 10, 0))
        near = MobileState(serial=3, name="Near", notoriety=1, position=(11, 10, 0))
        item = ItemState(serial=4, item_id=0xEED, name="gold", amount=5,
                         position=(12, 12, 0))
        state = GameState(player, mobiles=[far, near], ground_items=[item],
                          backpack=[ItemState(serial=5, item_id=0xE21)])
        data = state.to_dict()
        self.assertEqual([m["name"] for m in data["mobiles"]], ["Near", "Far"])
        self.assertEqual(data["mobiles"][0]["notoriety"], "innocent")
        self.assertEqual(data["mobiles"][1]["notoriety"], "murderer")
        self.assertEqual(data["mobiles"][1]["distance"], 10)
        self.assertEqual(data["ground_items"][0]["distance"], 2)
        self.assertNotIn("position", data["backpack"][0])
        json.dumps(data)

    def test_hits_fraction(self):
        self.assertEqual(PlayerState(hits=25, hits_max=100).hits_fraction(), 0.25)
        self.assertEqual(PlayerState().hits_fraction(), 1.0)


if __name__ == "__main__":
    unittest.main()
